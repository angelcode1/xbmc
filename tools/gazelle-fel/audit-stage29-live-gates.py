#!/usr/bin/env python3
"""Gazelle Stage 29: inspect an owner-supplied Stage 28 comparison OFFLINE.

This is a read-only HOST parser. No ADB, vendor binaries, kernel calls, codecs,
firmware changes or video captures. The output is NOT FEL residual proof.
"""
import argparse
import datetime
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

PHASES = ("idle", "P8", "P7")
PROBES = ("ports", "vdec", "vfm", "dv_source", "dv_instances",
          "dv_provider", "dv_mode")
P7_FORMAT = "HDR10 FORMAT_HDR10"
P8_FORMAT = "DV FORMAT_DOVI"
WATCH_PORTS = ("amstream_dves_hevc", "amstream_dves_hevc_frame")
WATCH_PROVIDERS = ("dvbldec", "dveldec", "dvbldec2", "dveldec2")
MAX_ZIP = 250_000
MAX_JSON = 180_000

def refuse(why):
    raise ValueError(why)

def read_archive(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_ZIP:
        refuse("missing, symlink or oversized capture")
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) != 2 or len({m.filename for m in members}) != 2:
            refuse("expect exactly original Stage28 JSON and text files")
        for m in members:
            if m.is_dir() or "/" in m.filename or "\\" in m.filename:
                refuse("unexpected archive path")
            if m.file_size > MAX_JSON:
                refuse("oversized archive member")
        json_names = [m.filename for m in members if re.fullmatch(
            r"stage28-active-comparison-[0-9]{8}-[0-9]{6}\.json",m.filename)]
        txt_names = [m.filename for m in members if m.filename.endswith(".txt")]
        if len(json_names) != 1 or len(txt_names) != 1 or (
            txt_names[0] != json_names[0][:-5]+".txt"):
            refuse("unexpected member names")
        raw = archive.read(json_names[0])
        evidence = json.loads(raw)
    return evidence, hashlib.sha256(path.read_bytes()).hexdigest()

def only_keys(obj, expected, where):
    if not isinstance(obj, dict) or set(obj) != set(expected):
        refuse("unexpected keys in "+where)

def integer_count(value, label):
    if not isinstance(value, list) or len(value) != 1 or (
        type(value[0]) is not int or value[0] < 0):
        refuse(label+" expected single nonnegative count")
    return value[0]

def extract(sample):
    only_keys(sample, ("phase", "sample", "start_utc", "end_utc", "probes"), "sample")
    name = sample["phase"]
    if name not in PHASES or type(sample["sample"]) is not int or not 1 <= sample["sample"] <= 3:
        refuse("unexpected phase/ordinal")
    start = datetime.datetime.fromisoformat(sample["start_utc"])
    end = datetime.datetime.fromisoformat(sample["end_utc"])
    if start.tzinfo is None or end.tzinfo is None or not start <= end:
        refuse("invalid sample timestamps")
    if (end-start).total_seconds() > 90:
        refuse("sample exceeds bounded timing")
    probes = sample["probes"]
    only_keys(probes, PROBES, "probes")
    for key, probe in probes.items():
        only_keys(probe, ("status", "value"), key)
        if probe["status"] != "ok" or probe["value"] is None:
            refuse(key+" unavailable; cannot make a complete phase claim")
    ports, vdec, vfm = (probes[k]["value"] for k in ("ports","vdec","vfm"))
    source, instance = (probes[k]["value"] for k in ("dv_source","dv_instances"))
    if not all(isinstance(d, dict) for d in (ports,vdec,vfm,source,instance)):
        refuse("malformed observation payload")
    p = {}
    for port in WATCH_PORTS:
        a = ports.get(port)
        if not isinstance(a, dict):
            refuse("missing port "+port)
        for field in ("type","flag","Vformat"):
            if type(a.get(field)) is not int:
                refuse("missing numeric port field "+port+"."+field)
        p[port] = {"type":a["type"],"flag":a["flag"],"Vformat":a["Vformat"]}
    el = {name:integer_count(vfm.get(name),name) for name in WATCH_PROVIDERS}
    fmt = source.get("inst1")
    if not isinstance(fmt,str):
        refuse("missing instance source format")
    for field in ("inst1_valid","core1a_on"):
        if type(instance.get(field)) is not int:
            refuse("missing Dolby instance field "+field)
    kind = vdec.get("classification")
    if kind not in ("no_vdec","nonempty_unclassified","unknown"):
        refuse("unknown decoder classification")
    return {
        "phase":name,"sample":sample["sample"],"start":start,"end":end,
        "vdec":kind,"has_hevc":vdec.get("has_hevc"),
        "source_format":fmt,"dv_inst1_valid":instance["inst1_valid"],
        "core1a_on":instance["core1a_on"],"vfm":el,"ports":p,
    }

def audit(evidence, archive_sha):
    only_keys(evidence,("schema","device_writes","playback_user_controlled",
                        "non_atomic_reads","samples"),"capture root")
    if evidence["schema"] != "gazelle-fel-stage28-v1":
        refuse("unexpected Stage28 schema")
    if evidence["device_writes"] is not False or evidence["playback_user_controlled"] is not True:
        refuse("capture safety/user phase assertions missing")
    if evidence["non_atomic_reads"] is not True:
        refuse("missing non-atomic-reads disclaimer")
    samples = evidence["samples"]
    if not isinstance(samples,list) or len(samples) != 9:
        refuse("expected three samples per idle/P8/P7 phase")
    rows = [extract(x) for x in samples]
    if [(x["phase"], x["sample"]) for x in rows] != [
        (phase,n) for phase in PHASES for n in (1,2,3)]:
        refuse("capture is not ordered idle, P8, P7 x three")
    if any(x["start"] < prev["end"] for prev,x in zip(rows,rows[1:])):
        refuse("sample time order overlaps")
    conclusions = {}
    for phase in PHASES:
        subset=[x for x in rows if x["phase"]==phase]
        def unanimous(predicate):return all(predicate(x) for x in subset)
        conclusions[phase] = {
            "all_report_active_vdec":unanimous(lambda x:x["vdec"]=="nonempty_unclassified"
                                                and x["has_hevc"] is True),
            "all_report_no_vdec":unanimous(lambda x:x["vdec"]=="no_vdec"),
            "all_dovi":unanimous(lambda x:x["source_format"]==P8_FORMAT),
            "all_hdr10":unanimous(lambda x:x["source_format"]==P7_FORMAT),
            "all_dolby_valid":unanimous(lambda x:x["dv_inst1_valid"]==1 and x["core1a_on"]==1),
            "all_dolby_inactive":unanimous(lambda x:x["dv_inst1_valid"]==0 and x["core1a_on"]==0),
            "all_bl_provider_one":unanimous(lambda x:x["vfm"]["dvbldec"]==1),
            "all_el_providers_zero":unanimous(lambda x:x["vfm"]["dveldec"]==0
                                               and x["vfm"]["dveldec2"]==0),
            "all_stream_port_unused":unanimous(lambda x:x["ports"]["amstream_dves_hevc"]["flag"]==0),
            "all_frame_port_267":unanimous(lambda x:x["ports"]["amstream_dves_hevc_frame"]["flag"]==267),
            "source_values":dict(Counter(x["source_format"] for x in subset))
        }
    c=conclusions
    path_match=all(
        row["ports"]==rows[0]["ports"] for row in rows
    )
    result={
       "capture_sha256":archive_sha,
       "capture_samples":9,
       "observed":conclusions,
       "port_state_invariant_across_all_nine":path_match,
       "baseline_frame_flag_stale":c["idle"]["all_report_no_vdec"] and c["idle"]["all_frame_port_267"],
       "working_p8_control":all((
           c["P8"]["all_report_active_vdec"],c["P8"]["all_dovi"],
           c["P8"]["all_dolby_valid"],c["P8"]["all_bl_provider_one"]
       )),
       "p7_hdr10_without_observed_el":all((
           c["P7"]["all_report_active_vdec"],c["P7"]["all_hdr10"],
           c["P7"]["all_dolby_valid"],c["P7"]["all_bl_provider_one"],
           c["P7"]["all_el_providers_zero"]
       )),
       "metadata_parser_invoked":None,
       "direct_slave_vdec_link_proven":None,
       "p7_fel_pixel_reconstruction_proven":False
    }
    return result

def format_report(r):
    c=r["observed"]
    summary=[
        "GAZELLE_FEL_STAGE29_CAPTURE_SCHEMA_PASS samples=9 phases=idle,P8,P7",
        "INPUT_SHA256="+r["capture_sha256"],
        "CAPTURE_DEVICE_WRITES=NONE",
        "P8_WORKING_DOVI_CONTROL="+str(r["working_p8_control"]).lower(),
        "P7_HDR10_WITHOUT_OBSERVED_EL="+str(r["p7_hdr10_without_observed_el"]).lower(),
        "ALL_NINE_PORT_RECORDS_EQUAL="+str(r["port_state_invariant_across_all_nine"]).lower(),
        "FRAME_FLAG_USED_WHEN_NO_VDEC="+str(r["baseline_frame_flag_stale"]).lower(),
    ]
    for phase in PHASES:
        x=c[phase]
        summary.append(
            "PHASE_%s source=%s vdec=%s core_valid=%s BL_count1=%s EL_zero=%s stream_flag0=%s frame_flag267=%s"%(
                phase,",".join(x["source_values"]), 
                "active" if x["all_report_active_vdec"] else ("none" if x["all_report_no_vdec"] else "mixed"),
                x["all_dolby_valid"],x["all_bl_provider_one"],x["all_el_providers_zero"],
                x["all_stream_port_unused"],x["all_frame_port_267"]))
    summary.extend([
        "PORT_FLAGS_DO_NOT_ESTABLISH_ACTIVE_FD=true",
        "NONATOMIC_SAMPLE_LIMITATION=true",
        "CODEC_EL_INSTANCE_PTR=NOT_OBSERVED",
        "DOLBY_RPU_PARSER_DURING_P7=NOT_OBSERVED",
        "P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN",
        "NEXT_BOUNDARY=original_vendor_decoder_profile_and_EL_handshake_OFFLINE",
        "GAZELLE_FEL_STAGE29_OFFLINE_CAPTURE_AUDIT_PASS"
    ])
    return "\n".join(summary)+"\n"

def selftest():
    example = {"phase":"idle","sample":1,"start_utc":"2026-10-19T00:00:00+00:00",
      "end_utc":"2026-10-19T00:00:01+00:00",
      "probes":{k:{"status":"ok","value":{}} for k in PROBES}}
    example["probes"]["ports"]["value"]={p:{"type":1,"flag":0,"Vformat":0}
                                            for p in WATCH_PORTS}
    example["probes"]["vdec"]["value"]={"classification":"no_vdec"}
    example["probes"]["vfm"]["value"]={p:[0] for p in WATCH_PROVIDERS}
    example["probes"]["dv_source"]["value"]={"inst1":"DV FORMAT_DOVI"}
    example["probes"]["dv_instances"]["value"]={"inst1_valid":0,"core1a_on":0}
    assert extract(example)["vfm"]["dveldec"] == 0
    for malformed in ([],[0,1],["0"],[-1]):
        bad=json.loads(json.dumps(example))
        bad["probes"]["vfm"]["value"]["dveldec"]=malformed
        try:
            extract(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid EL provider count accepted")
    print("GAZELLE_FEL_STAGE29_SOURCE_SELFTEST_PASS")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("capture_zip",nargs="?",type=Path)
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    selftest()
    if a.selftest:return
    if not a.capture_zip:p.error("supply original stage28-active-comparison ZIP or --selftest")
    data,sha=read_archive(a.capture_zip.expanduser())
    report=format_report(audit(data,sha))
    print(report,end="")
    if a.output:
        a.output.expanduser().write_text(report,encoding="utf-8")

if __name__=="__main__":
    try: main()
    except (ValueError,TypeError,KeyError,OSError,zipfile.BadZipFile,
            json.JSONDecodeError,AssertionError) as error:
        print("GAZELLE_FEL_STAGE29_CAPTURE_AUDIT_FAIL",error,file=sys.stderr)
        sys.exit(1)
