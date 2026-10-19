#!/usr/bin/env python3
"""Gazelle FEL Stage 28: manually staged, read-only P8/P7 decoder snapshots.

No settings changes, playback automation, log reads, APK changes or device
writes. Provider counts/port flags alone do NOT prove FEL residual pixels.
"""
import argparse
import datetime as datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import zipfile

PROBES = {
    "ports": "/sys/class/amstream/ports",
    "vdec": "/sys/class/vdec/vdec_status",
    "vfm": "/sys/class/vfm/map",
    "dv_source": "/sys/class/amdolby_vision/src_format",
    "dv_instances": "/sys/class/amdolby_vision/dv_inst_status",
    "dv_provider": "/sys/class/amdolby_vision/dv_provider",
    "dv_mode": "/sys/class/amdolby_vision/dv_mode",
}
PHASES = ("idle", "P8", "P7")
SAMPLES = 3
INTERVAL_SECONDS = 2
TIMEOUT_SECONDS = 12
MAX_CAPTURE = 16000
WATCH_PORTS = ("amstream_hevc", "amstream_hevc_frame",
               "amstream_dves_hevc", "amstream_dves_hevc_frame")
WATCH_PROVIDERS = ("dvbldec", "dveldec", "dvbldec2", "dveldec2")

def adb_path():
    given = os.environ.get("ADB")
    if given:
        path = shutil.which(given)
        if not path:
            raise RuntimeError("ADB override not executable")
        return path
    return (shutil.which("adb") or
            next((p for p in ("/Applications/adblink.app/Contents/MacOS/adbfiles/adb",)
                  if Path(p).is_file()), None) or
            (_ for _ in ()).throw(RuntimeError("adb not found")))

def local_adb(adb, args):
    result = subprocess.run([adb, *args], text=True, capture_output=True,
                            timeout=TIMEOUT_SECONDS, check=False)
    return result.returncode, result.stdout.replace("\r", "")[:MAX_CAPTURE]

def remote_read(adb, node):
    if node not in PROBES.values():
        raise ValueError("non-allowlisted remote read")
    try:
        ret, text = local_adb(adb, ["shell", "su -c 'cat " + node + "'"])
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "text": ""}
    return {"status": "ok" if ret == 0 else "unavailable", "text": text if ret == 0 else ""}

def port_status(text):
    result = {}
    groups = re.split(r"(?=^amstream_[A-Za-z0-9_]+\s*:\s*$)", text, flags=re.M)
    for group in groups:
        header = re.match(r"^\s*(amstream_[A-Za-z0-9_]+)\s*:\s*\n", group)
        if not header or header[1] not in WATCH_PORTS:
            continue
        values = {}
        for key in ("type", "flag", "Vformat"):
            match = re.search(r"^\s*" + key + r":(-?\d+)(?:\(([^\n]*)\))?", group, re.M)
            if match:
                values[key] = int(match[1])
                if key == "flag":
                    values["flag_used_label"] = "Used" in (match[2] or "")
        result[header[1]] = values
    return result

def vfm_status(text):
    return {name: [int(v) for v in re.findall(r"\b" + re.escape(name) + r"\((\d+)\)", text)]
            for name in WATCH_PROVIDERS}

def vdec_status(text):
    if re.search(r"\bNo vdec\s*\.", text, re.I):
        return {"classification": "no_vdec"}
    if not text.strip():
        return {"classification": "unknown"}
    return {"classification": "nonempty_unclassified",
            "has_hevc": bool(re.search(r"hevc|h265", text, re.I)),
            "has_slave": bool(re.search(r"\bslave\b", text, re.I))}

def dv_status(key, text):
    if key == "dv_source":
        return {n: (m.group(1).strip() if (m := re.search(r"^" + n + r":\s*([^\n]+)", text, re.M)) else None)
                for n in ("inst1", "inst2")}
    if key == "dv_instances":
        result = {}
        for name, pattern in {
            "valid_num": r"\bvalid num\s+(\d+)",
            "core1a_on": r"\[core1a\].*?core on\s+(\d+)",
            "core1b_on": r"\[core1b\].*?core on\s+(\d+)",
            "inst1_valid": r"\[inst1\]:[^\n]*?valid\s+(\d+)",
            "inst2_valid": r"\[inst2\]:[^\n]*?valid\s+(\d+)",
        }.items():
            m = re.search(pattern, text)
            result[name] = int(m[1]) if m else None
        return result
    if key == "dv_provider":
        return {"providers": [word for word in text.split()
                              if word in WATCH_PROVIDERS]}
    if key == "dv_mode":
        m = re.search(r"current dv_mode\s*=\s*(\S+)", text)
        return {"current": m[1] if m else None}
    raise ValueError("unrecognized probe")

def parse_probe(key, payload):
    if payload["status"] != "ok":
        return {"status": payload["status"], "value": None}
    text = payload["text"]
    if key == "ports": value = port_status(text)
    elif key == "vfm": value = vfm_status(text)
    elif key == "vdec": value = vdec_status(text)
    else: value = dv_status(key, text)
    return {"status": "ok", "value": value}

def one_sample(adb, phase, number):
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    probes = {name: parse_probe(name, remote_read(adb, path))
              for name, path in PROBES.items()}
    ended = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return {"phase": phase, "sample": number, "start_utc": started,
            "end_utc": ended, "probes": probes}

def summarise(samples):
    parts = ["GAZELLE_FEL_STAGE28_READONLY_CAPTURE", "DEVICE_WRITES=NONE",
             "USER_CONTROLLED_PLAYBACK=true", "P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN",
             "COUNTS_ARE_NOT_EL_FRAME_PROOF=true", ""]
    for phase in PHASES:
        rows = [x for x in samples if x["phase"] == phase]
        parts.append("=== " + phase + " ===")
        for row in rows:
            probes = row["probes"]
            ports = probes["ports"]["value"] or {}
            fr = ports.get("amstream_dves_hevc_frame", {})
            stream = ports.get("amstream_dves_hevc", {})
            vf = probes["vfm"]["value"] or {}
            vd = probes["vdec"]["value"] or {}
            dv = probes["dv_source"]["value"] or {}
            inst = probes["dv_instances"]["value"] or {}
            fmt = dv.get("inst1") or "unknown"
            parts.append(
                "sample={sample} frame_flag={frame} stream_flag={stream} "
                "vdec={vdec} dveldec={el} dveldec2={el2} "
                "dv_inst1={fmt} dv_inst1_valid={valid} core1a={core}".format(
                    sample=row["sample"], frame=fr.get("flag", "unknown"),
                    stream=stream.get("flag", "unknown"),
                    vdec=vd.get("classification", "unknown"),
                    el=vf.get("dveldec") or "unknown", el2=vf.get("dveldec2") or "unknown",
                    fmt=fmt,valid=inst.get("inst1_valid", "unknown"),
                    core=inst.get("core1a_on", "unknown")))
        parts.append("")
    parts.extend(["Note: ports, vdec and vfm reads are sequential, not atomic.",
                  "No visual evidence of BL+EL residual contribution collected.",
                  "GAZELLE_FEL_STAGE28_CAPTURE_COMPLETE"])
    return "\n".join(parts) + "\n"

def selftest():
    assert len(PROBES) == 7 and len(PHASES) == 3 and SAMPLES == 3
    assert all(path.startswith("/sys/class/") and "'" not in path
               for path in PROBES.values())
    p = port_status("amstream_dves_hevc_frame\t:\n\ttype:7441( Video ES )\n\tflag:267( Used )\n\tVformat:11\n\n"
                    "amstream_dves_hevc\t:\n\ttype:6417( Video ES )\n\tflag:0( Unused )\n")
    assert p["amstream_dves_hevc_frame"]["flag"] == 267
    assert p["amstream_dves_hevc"]["flag"] == 0
    assert vfm_status("dvblpath { dvbldec(0) } dvelpath { dveldec(0) }")["dveldec"] == [0]
    assert vdec_status("No vdec.")["classification"] == "no_vdec"
    assert dv_status("dv_source", "inst1: DV FORMAT_DOVI\ninst2: NONE FORMAT_INVALID")["inst1"] == "DV FORMAT_DOVI"
    assert dv_status("dv_instances", "[core1a]: video flag 0, core on 0\n[inst1]:mapped 0,valid 0,fmt DV")["inst1_valid"] == 0
    print("GAZELLE_FEL_STAGE28_SOURCE_SELFTEST_PASS")

def capture(out_root):
    adb = adb_path()
    ret, devices_text = local_adb(adb, ["devices"])
    devices = [line for line in devices_text.splitlines()[1:]
               if len(line.split()) == 2 and line.split()[1] == "device"]
    if ret != 0 or len(devices) != 1:
        raise RuntimeError("expected exactly one authorized ADB device")
    ret, identity = local_adb(adb, ["shell", "su -c 'id'"])
    if ret or "uid=0(" not in identity:
        raise RuntimeError("read-only root access is required; no changes attempted")
    instructions = {
        "idle": "Stop Kodi video playback; press Enter after playback has stopped.",
        "P8": "Start your KNOWN-WORKING Profile 8 video; while visibly playing press Enter.",
        "P7": "Stop P8. Start the Profile 7 FEL test video; while visibly playing press Enter.",
    }
    rows = []
    for phase in PHASES:
        print("\n" + phase + ": " + instructions[phase],flush=True)
        input()
        for number in range(1, SAMPLES + 1):
            sample = one_sample(adb, phase, number)
            rows.append(sample)
            print("  snapshot %d/%d complete" % (number, SAMPLES),flush=True)
            if number < SAMPLES: time.sleep(INTERVAL_SECONDS)
    out_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    prefix = "stage28-active-comparison-" + stamp
    text_path, json_path, zip_path = (out_root / (prefix + suffix) for suffix in (".txt", ".json", ".zip"))
    text_path.write_text(summarise(rows),encoding="utf-8")
    json_path.write_text(json.dumps({"schema":"gazelle-fel-stage28-v1",
        "device_writes":False,"playback_user_controlled":True,
        "non_atomic_reads":True,"samples":rows},indent=2)+"\n",encoding="utf-8")
    with zipfile.ZipFile(zip_path,"w",zipfile.ZIP_DEFLATED) as archive:
        archive.write(text_path,arcname=text_path.name)
        archive.write(json_path,arcname=json_path.name)
    print("UPLOAD_FILE="+str(zip_path))
    print("GAZELLE_FEL_STAGE28_CAPTURE_COMPLETE")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--selftest",action="store_true")
    group.add_argument("--capture",action="store_true")
    parser.add_argument("--output-root",type=Path,
                        default=Path.home()/"Downloads"/"gazelle-fel-stage28-results")
    args = parser.parse_args()
    selftest()
    if args.capture: capture(args.output_root.expanduser())

if __name__ == "__main__":
    try: main()
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, EOFError, KeyboardInterrupt) as exc:
        print("GAZELLE_FEL_STAGE28_FAIL",str(exc),file=sys.stderr)
        sys.exit(1)
