#!/usr/bin/env python3
"""Gazelle Stage32: bounded, passive P8/P7 logcat comparison. No device writes.

Saves only semantic event labels, timestamps, counts and Dolby source format.
Never stores a raw logcat line, message, filename, PID or device serial.
Absence of an error log never proves an ioctl succeeded or FEL was decoded.
"""
import argparse,collections,datetime as dt,json,os,re,select,shutil,subprocess,sys,threading,time,zipfile
from pathlib import Path

PATTERNS=(
 ("CONFIG_301_UNSUPPORTED",r"kernel not support AMSTREAM_SET_PTR_CONFIGS"),
 ("CONFIG_301_IOCTL_FAILURE",r"(?:codec_h_ioctl(?:_set)? failed|ioctl failed).{0,150}\b(?:subcmd|cmd)\s*=\s*(?:0x)?301\b"),
 ("CONFIG_IOCTL_FAILURE_UNSPECIFIED",r"codec_h_ioctl(?:_set)? failed"),
 ("DOLBY_METADATA_PARSER_FAILURE",r"(?:meta(?:data)?\s+parser|parse_sei_and_meta|rpu(?:\s+parse)?)\b.{0,90}(?:fail|error)"),
 ("CONFIG_NEGATIVE_DV_PRESENT",r"negative_dv:1;"),
 ("CONFIG_DUALLAYER_PRESENT",r"dv_duallayer:1;"),
 ("CONFIG_HEVC_TEXT_PRESENT",r"(?:mAmlCodecParam->config|CodecParam->config|hevc_buf_width:)"),
 ("DVHE_COMPONENT",r"OMX\.amlogic\.dolby-vision\.dvhe\.decoder"),
 ("DOLBY_EL_MENTION",r"\bdveldec\b|\bdv dual layer\b"),
 ("FRAME_MODE_MENTION",r"\bVDEC_TYPE_FRAME_BLOCK\b|\buse_frame_mode\b"),
 ("KODI_FEL_MARKER",r"GAZELLE_(?:FEL|DOVI|DVHE)"),
)
RX=tuple((name,re.compile(pattern,re.I)) for name,pattern in PATTERNS)
EPOCH=re.compile(r"^\s*(\d{10}(?:\.\d+)?)\s+\d+\s+\d+\s+[VDIWEFS]\s+([^:]{1,90}):\s*(.*)$")
MAX_WINDOW=75
FOLLOWUP=8
MAX_LINES=200000
MAX_EVENTS=120

def utc():
 return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")

def classify(line,start):
 if len(line)>3000:return None
 m=EPOCH.match(line)
 if not m:return None
 stamp=float(m[1])
 if stamp<start-2 or stamp>time.time()+90:return None
 for label,pattern in RX:
  if pattern.search(m[3]):
   return {"category":label,"device_epoch":round(stamp,3),"host_utc":utc()}
 return None

def sysfs_class(adb):
 try:
  p=subprocess.run([adb,"shell","su -c 'cat /sys/class/amdolby_vision/src_format'"],
       capture_output=True,text=True,timeout=12,check=False)
 except subprocess.TimeoutExpired:return "UNAVAILABLE"
 if p.returncode:return "UNAVAILABLE"
 if "FORMAT_DOVI" in p.stdout:return "DOVI"
 if "FORMAT_HDR10" in p.stdout:return "HDR10"
 return "UNKNOWN"

def get_adb():
 val=os.environ.get("ADB")
 options=[val] if val else ["adb","/Applications/adblink.app/Contents/MacOS/adbfiles/adb"]
 for opt in options:
  if opt and shutil.which(opt):return shutil.which(opt)
 raise RuntimeError("adb missing (brew install android-platform-tools, or set ADB=...)")

def connected(adb):
 p=subprocess.run([adb,"devices"],capture_output=True,text=True,timeout=12,check=False)
 found=[l for l in p.stdout.splitlines()[1:] if len(l.split())==2 and l.split()[1]=="device"]
 if p.returncode or len(found)!=1:raise RuntimeError("exactly one authorised ADB target required")

def one_phase(adb,phase):
 print("\nStop playback, then press Enter to begin %s log capture."%phase,flush=True)
 input()
 start=time.time()
 rec={"phase":phase,"start_utc":utc(),"events":[],"lines":0,"unparsed":0,
      "overflow":0,"truncated":False,"source_format":"UNKNOWN"}
 proc=subprocess.Popen([adb,"logcat","-b","main","-b","system","-T","1","-v","epoch"],
    stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
    text=True,errors="replace",bufsize=1)
 stop=threading.Event()
 def read():
  try:
   for line in proc.stdout:
    if stop.is_set() or time.time()-start>MAX_WINDOW or rec["lines"]>=MAX_LINES:
     rec["truncated"]=True
     break
    rec["lines"]+=1
    event=classify(line,start)
    if event:
     if len(rec["events"])<MAX_EVENTS:rec["events"].append(event)
     else:rec["overflow"]+=1
    elif not EPOCH.match(line):rec["unparsed"]+=1
  except (OSError,UnicodeError):
   rec["truncated"]=True
 t=threading.Thread(target=read,daemon=True)
 t.start()
 try:
  print("Start %s playback NOW; press Enter while video is moving."%phase,flush=True)
  ready,_,_=select.select([sys.stdin],[],[],MAX_WINDOW-FOLLOWUP)
  if not ready:raise RuntimeError("%s window expired before confirmation"%phase)
  sys.stdin.readline()
  rec["source_format"]=sysfs_class(adb)
  time.sleep(FOLLOWUP)
 finally:
  stop.set()
  if proc.poll() is None:proc.terminate() # local adb client, not device
  try:proc.wait(timeout=4)
  except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=3)
  t.join(timeout=3)
  proc.stdout.close()
 rec["end_utc"]=utc()
 rec["reader_ok"]=proc.returncode in (-15,-2,0)
 print("%s: events=%d source=%s"%(phase,len(rec["events"]),rec["source_format"]))
 return rec

def verdict(rec):
 counts=collections.Counter(e["category"] for e in rec["events"])
 if (not rec["reader_ok"] or rec["truncated"] or rec["overflow"] or
     rec["lines"]==0 or rec["unparsed"]>=rec["lines"]):
  return "INCOMPLETE",counts
 if counts["CONFIG_301_UNSUPPORTED"] or counts["CONFIG_301_IOCTL_FAILURE"]:
  return "CONFIG_301_ERROR_LOGGED_NOT_CAUSAL_PROOF",counts
 if counts["DOLBY_METADATA_PARSER_FAILURE"]:
  return "DOLBY_PARSER_ERROR_LOGGED_NOT_CAUSAL_PROOF",counts
 return "NO_DIRECT_ERROR_SEEN_SUCCESS_UNKNOWN",counts

def report(phases):
 lines=["GAZELLE_FEL_STAGE32_READONLY_LOG_CAPTURE","DEVICE_WRITES=NONE",
        "RAW_LOG_MESSAGES_STORED=NO","CONFIG_IOCTL_0x301_ACTUAL_RETURN=NOT_MEASURED"]
 for r in phases:
  v,c=verdict(r)
  lines.append("PHASE=%s SOURCE=%s VERDICT=%s EVENTS=%d LINES=%d"%(r["phase"],r["source_format"],v,len(r["events"]),r["lines"]))
  lines.extend("  %s=%d"%(k,n) for k,n in sorted(c.items()))
 lines+=["LOG_ABSENCE=INCONCLUSIVE","P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN",
         "GAZELLE_FEL_STAGE32_CAPTURE_COMPLETE"]
 return "\n".join(lines)+"\n"

def selftest():
 assert len(RX)==11 and MAX_EVENTS==120
 sample="1729400000.500 2341 2341 E OMX: kernel not support AMSTREAM_SET_PTR_CONFIGS"
 assert classify(sample,1729400000)["category"]=="CONFIG_301_UNSUPPORTED"
 assert classify(sample,1729400004) is None
 assert classify("1729400000.600 1 2 W OMX: codec_h_ioctl_set failed,handle=1,subcmd=301",1729400000)["category"]=="CONFIG_301_IOCTL_FAILURE"
 assert classify("1729400000.600 1 2 W OMX: codec_h_ioctl_set failed,handle=1,subcmd=302",1729400000)["category"]=="CONFIG_IOCTL_FAILURE_UNSPECIFIED"
 assert classify("1729400000.500 1 2 I Kodi: /sdcard/secret/movie.mkv",1729400000) is None
 r={"phase":"P7","source_format":"HDR10","events":[],"lines":10,"unparsed":0,
    "reader_ok":True,"truncated":False,"overflow":0}
 assert verdict(r)[0]=="NO_DIRECT_ERROR_SEEN_SUCCESS_UNKNOWN"
 assert "RAW_LOG_MESSAGES_STORED=NO" in report([r])
 print("GAZELLE_FEL_STAGE32_SOURCE_SELFTEST_PASS")

def capture(output):
 adb=get_adb()
 connected(adb)
 print("Only reads logcat main/system and one source-format status file per phase.")
 print("Controls remain untouched; no raw Android logs are saved.")
 phases=[one_phase(adb,p) for p in ("P8","P7")]
 output.mkdir(parents=True,exist_ok=True)
 stem="stage32-log-compare-"+dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
 j=output/(stem+".json")
 t=output/(stem+".txt")
 z=output/(stem+".zip")
 j.write_text(json.dumps({"schema":"gazelle-fel-stage32-v1","device_writes":False,
    "log_payloads_retained":False,"phases":phases},indent=2)+"\n")
 t.write_text(report(phases))
 with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as archive:
  archive.write(j,arcname=j.name)
  archive.write(t,arcname=t.name)
 print(report(phases),end="")
 print("UPLOAD_FILE="+str(z))

def main():
 p=argparse.ArgumentParser(description=__doc__)
 g=p.add_mutually_exclusive_group(required=True)
 g.add_argument("--selftest",action="store_true")
 g.add_argument("--capture",action="store_true")
 p.add_argument("--output-dir",type=Path,
  default=Path.home()/"Downloads"/"gazelle-fel-stage32-results")
 a=p.parse_args()
 selftest()
 if a.capture:capture(a.output_dir.expanduser())

if __name__=="__main__":
 try:main()
 except (OSError,RuntimeError,ValueError,KeyboardInterrupt,EOFError,subprocess.TimeoutExpired) as e:
  print("GAZELLE_FEL_STAGE32_CAPTURE_FAIL",str(e),file=sys.stderr)
  sys.exit(1)
