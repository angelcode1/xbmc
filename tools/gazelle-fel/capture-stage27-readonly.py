#!/usr/bin/env python3
"""Gazelle FEL Stage 27: explicitly opt-in, read-only installed-kernel snapshot.

Does not alter codecs, playback, properties, devices, logs, modules or kernel
state. No writes on the Cube. Only compact, sanitised host reports are saved.
Observed symbols/providers are not proof of a connected FEL decoder or pixels.
"""
import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

SYMBOL_NAMES = (
    "register_dv_functions", "unregister_dv_functions",
    "dolby_vision_parse_metadata", "is_dovi_frame",
    "is_dovi_dual_layer_frame", "parse_sei_and_meta_ext",
    "dolby_vision_set_provider", "vh265_event_cb",
    "vdec_set_dv_metawithel", "dvel_vf_get", "dvel_vf_peek",
    "decoder_do_aux_data_check",
)
SYMBOL_QUERY = (
    "grep -E ' ("
    + "|".join(SYMBOL_NAMES)
    + r")([[:space:]]|$)' /proc/kallsyms"
)
PROBES = (
    ("kernel_release", "uname -r", False),
    ("build_incremental", "getprop ro.build.version.incremental", False),
    ("loaded_modules", "cat /proc/modules", True),
    ("kernel_symbols", SYMBOL_QUERY, True),
    ("dolby_source_format", "cat /sys/class/amdolby_vision/src_format", True),
    ("dolby_instance_status", "cat /sys/class/amdolby_vision/dv_inst_status", True),
    ("dolby_provider", "cat /sys/class/amdolby_vision/dv_provider", True),
    ("dolby_mode", "cat /sys/class/amdolby_vision/dv_mode", True),
    ("video_frame_map", "cat /sys/class/vfm/map", True),
    ("vdec_status", "cat /sys/class/vdec/vdec_status", True),
    ("amstream_ports", "cat /sys/class/amstream/ports", True),
)
ALLOWED_NODES = tuple(
    command[4:] for _, command, root in PROBES if command.startswith("cat /")
)
MAX_TEXT = 12000
TIMEOUT = 15
MODULE_RE = re.compile(r"^(?:dovi|amvdec|decoder_common|stream_input|amstream|amdolby|amlvideo)", re.I)
ADDR_RE = re.compile(r"\b(?:0x)?f{4}[a-f0-9]{8,}\b", re.I)

def scrub(data):
    data = data.replace("\r", "")
    data = ADDR_RE.sub("<masked-address>", data)
    return data[:MAX_TEXT]

def adb_binary():
    found = shutil.which("adb")
    if found:
        return found
    legacy = "/Applications/adblink.app/Contents/MacOS/adbfiles/adb"
    if Path(legacy).is_file():
        return legacy
    raise RuntimeError("adb not found. Install Android platform-tools or set ADB.")

def run(adb, remote, root=False):
    # No user-supplied remote command strings; PROBES is the fixed allowlist.
    if root:
        remote = 'su -c "' + remote + '"'
    try:
        proc = subprocess.run(
            [adb, "shell", remote], capture_output=True, text=True,
            errors="replace", timeout=TIMEOUT, check=False
        )
    except subprocess.TimeoutExpired:
        return {"status":"timeout", "text":""}
    return {
        "status": "ok" if proc.returncode == 0 else "unavailable",
        "text": scrub(proc.stdout),
        "error": scrub(proc.stderr)[:300],
    }

def parse_symbols(data):
    found = set()
    for line in data.splitlines():
        match = re.match(r"^\s*[0-9a-fA-F]+\s+([A-Za-z])\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+\[([A-Za-z0-9_.-]+)\])?\s*$", line)
        if match and match[2] in SYMBOL_NAMES:
            found.add((match[2], match[1], match[3] or "built-in/unspecified"))
    return [{"name":name,"type":kind,"source":module} for name,kind,module in sorted(found)]

def parse_modules(data):
    return sorted({
        line.split()[0] for line in data.splitlines()
        if line.split() and MODULE_RE.search(line.split()[0])
    })

def summarise(raw):
    modules = parse_modules(raw.get("loaded_modules",{}).get("text",""))
    symbols = parse_symbols(raw.get("kernel_symbols",{}).get("text",""))
    values = {}
    for name, _, _ in PROBES:
        p = raw.get(name, {"status":"unavailable","text":""})
        if name=="loaded_modules":
            values[name]={"status":p["status"],"names":modules}
        elif name=="kernel_symbols":
            values[name]={"status":p["status"],"matches":symbols,
                          "note":"absence is inconclusive: kallsyms may be restricted or symbols omitted"}
        else:
            text = p.get("text","")
            values[name]={"status":p["status"],"text":text,
                          "note":"read-only snapshot; may be idle" if name in
                          ("dolby_provider","dolby_instance_status","amstream_ports","vdec_status","video_frame_map") else ""}
    return values

def make_report(state, root_ok):
    lines = [
        "GAZELLE_FEL_STAGE27_READONLY_SNAPSHOT",
        "DEVICE_WRITES=NONE",
        "ROOT_READ_ACCESS=" + ("YES" if root_ok else "NO"),
        "ACTIVE_P7_DECODING=NOT_TESTED",
        "AMAZON_DV_RECEIVER_IMPLEMENTATION=NOT_PROVEN",
        "P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN",
        "",
    ]
    for name, _, _ in PROBES:
        item=state[name]
        lines.append("=== "+name+" | "+item["status"]+" ===")
        if name=="loaded_modules":
            lines.extend(item["names"] or ["NONE_OBSERVED"])
        elif name=="kernel_symbols":
            lines.extend(
                row["name"]+" "+row["type"]+" ["+row["source"]+"]"
                for row in item["matches"]
            )
            if not item["matches"]:lines.append("NONE_OBSERVED_NOT_PROOF_OF_ABSENCE")
        else:
            lines.append(item["text"].strip() or "(empty or unavailable)")
        lines.append("")
    lines.append("GAZELLE_FEL_STAGE27_CAPTURE_COMPLETE")
    return "\n".join(lines)+"\n"

def selftest():
    assert len(PROBES)==11 and len(SYMBOL_NAMES)==12
    assert all(
        command.startswith(("cat /", "uname -r", "getprop ro.", "grep -E "))
        for _, command, _ in PROBES
    )
    assert all(path.startswith(("/proc/","/sys/")) for path in ALLOWED_NODES)
    assert parse_modules("dovi 1 0 - Live 0\namvdec_h265 2 1 - Live 0\nother 8 0 - Live 0")==[
        "amvdec_h265","dovi"]
    sample = "0000000000000000 T register_dv_functions\nffff000012345678 t vh265_event_cb [amvdec_h265]\n"
    rows = parse_symbols(sample)
    assert len(rows)==2 and rows[0]["name"]=="register_dv_functions"
    assert "<masked-address>" in scrub(sample)
    output=make_report(summarise({}),False)
    assert "P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN" in output
    assert "NONE_OBSERVED_NOT_PROOF_OF_ABSENCE" in output
    print("GAZELLE_FEL_STAGE27_SOURCE_SELFTEST_PASS")

def capture(output_root):
    adb = adb_binary()
    # Exactly one connected device; do not accidentally inspect another ADB target.
    connected = subprocess.run(
        [adb,"devices"], capture_output=True,text=True,timeout=TIMEOUT,check=False
    )
    devices = [line.split()[0] for line in connected.stdout.splitlines()[1:]
               if len(line.split())==2 and line.split()[1]=="device"]
    if len(devices)!=1:
        raise RuntimeError("expected exactly one authorized ADB device; found "+str(len(devices)))
    root = run(adb,"id",root=True)
    root_ok=root["status"]=="ok" and "uid=0(" in root["text"]
    print("DEVICE_ROOT_READ_ACCESS="+("YES" if root_ok else "NO"))
    print("DEVICE_MODIFICATIONS=NONE")
    data={}
    for name,remote,need_root in PROBES:
        if need_root and not root_ok:
            data[name]={"status":"unavailable_no_root","text":""}
        else:
            data[name]=run(adb,remote,root=need_root)
        print(name+"="+data[name]["status"])
    summary=summarise(data)
    stamp=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_root.mkdir(parents=True,exist_ok=True)
    text_file=output_root/("stage27-readonly-"+stamp+".txt")
    json_file=output_root/("stage27-readonly-"+stamp+".json")
    zip_file=output_root/("stage27-readonly-"+stamp+".zip")
    report=make_report(summary,root_ok)
    text_file.write_text(report,encoding="utf-8")
    json_file.write_text(json.dumps({
       "schema":"gazelle-fel-stage27-readonly-v1",
       "host_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
       "root_read_access":root_ok,
       "device_writes":False,
       "results":summary,
       "note":"No raw kernel addresses, serial numbers or original proprietary binaries included.",
    },indent=2)+"\n",encoding="utf-8")
    with zipfile.ZipFile(zip_file,"w",zipfile.ZIP_DEFLATED) as archive:
        archive.write(text_file,arcname=text_file.name)
        archive.write(json_file,arcname=json_file.name)
    print("UPLOAD_FILE="+str(zip_file))
    print("GAZELLE_FEL_STAGE27_CAPTURE_COMPLETE")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    actions=parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--selftest",action="store_true")
    actions.add_argument("--capture",action="store_true")
    parser.add_argument("--output-root",type=Path,
                        default=Path.home()/"Downloads"/"gazelle-fel-stage27-results")
    a=parser.parse_args()
    selftest()
    if a.capture:capture(a.output_root.expanduser())

if __name__=="__main__":
    try:main()
    except (OSError,RuntimeError,ValueError,subprocess.TimeoutExpired) as exc:
        print("GAZELLE_FEL_STAGE27_CAPTURE_FAIL",str(exc),file=sys.stderr)
        sys.exit(1)
