#!/usr/bin/env python3
"""Stage 26: fail-closed audit of a pinned PUBLIC Amlogic DV receiver source.

This is NOT the installed Amazon kernel. It proves a compatible source-level
API route only, not the Cube's runtime route, EL slave creation or FEL pixels.
No ADB, root, live hardware, modifications or vendor-binary redistribution.
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

UPSTREAM="TCLOpenSource/a311d2"
COMMIT="24a1e36b68d5319f7c4e94a2d6d1badf9f92ba7f"
ROOT="drivers/amlogic/media/enhancement/amdolby_vision/"
PINS={
 ROOT+"amdolby_vision.c":"ee5e4f6b4c90926321daf167c7559e6e0f259f1c",
 ROOT+"amdolby_vision.h":"97751b206ec7cbd93f1ff0d19615040bfa2d3820",
 "include/linux/amlogic/media/amdolbyvision/dolby_vision.h":"8afd173cf769443301c76efa5c48d7dfb04d111e",
}
def gitblob(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()

def requires(body,needles,scope):
    for needle in needles:
        if needle not in body:
            raise ValueError(scope+" missing "+needle)

def function(text,name):
    """Find one named C function, balancing braces (source is SHA pinned)."""
    hits=list(re.finditer(r"\b"+re.escape(name)+r"\s*\(",text))
    for hit in hits:
        left=text.rfind(";",max(0,hit.start()-300),hit.start())
        brace=text.find("{",hit.end())
        if brace<0 or brace-hit.end()>800:
            continue
        if ";" in text[hit.end():brace]:
            continue
        depth=0
        for index in range(brace,len(text)):
            if text[index]=="{":depth+=1
            elif text[index]=="}":
                depth-=1
                if not depth:
                    return text[brace:index+1]
    raise ValueError("function definition absent "+name)

def audit(root):
    sources={}
    for rel,expected in PINS.items():
        f=root/rel
        if not f.is_file() or f.is_symlink():
            raise ValueError("missing or symlink source "+str(f))
        b=f.read_bytes()
        if gitblob(b)!=expected:
            raise ValueError("public Git blob SHA mismatch "+rel)
        sources[rel]=b.decode("utf-8")
        print("PINNED_PUBLIC_SOURCE_PASS",rel)
    c=sources[ROOT+"amdolby_vision.c"]
    h=sources[ROOT+"amdolby_vision.h"]
    interface=sources["include/linux/amlogic/media/amdolbyvision/dolby_vision.h"]
    requires(interface,["#define DV_SEI 0x01000000",
        "#define DV_AV1_SEI 0x14000000"],"public DV tag header")
    requires(h,["struct dolby_vision_func_s",
        "metadata_parser_process","register_dv_functions"],"public callback ABI")
    requires(c,['static char dv_provider[32] = "dvbldec";',
        "EXPORT_SYMBOL(register_dv_functions);"],"public receiver")
    functions={
        "register_dv_functions":[
            "dolby_vision_probe_ok == 0","p_funcs_stb = func;",
            "p_funcs_tv = func;"],
        "is_dovi_frame":[
            "VFRAME_EVENT_RECEIVER_GET_AUX_DATA",
            "req.dv_enhance_exist", "type == DV_SEI"],
        "is_dovi_dual_layer_frame":[
            "!enable_fel", "VFRAME_EVENT_RECEIVER_GET_AUX_DATA",
            "req.dv_enhance_exist"],
        "parse_sei_and_meta":[
            "req->aux_buf","req->aux_size", "parse_sei_and_meta_ext"],
        "parse_sei_and_meta_ext":[
            "p_funcs_stb->metadata_parser_process",
            "p_funcs_tv->metadata_parser_process"],
        "dolby_vision_parse_metadata":[
            "VFRAME_EVENT_RECEIVER_GET_AUX_DATA",
            '"dveldec"', "req.dv_enhance_exist",
            "parse_sei_and_meta"],
    }
    for name,needles in functions.items():
        body=function(c,name)
        requires(body,needles,name)
        print("PUBLIC_RECEIVER_FUNCTION_PASS",name)
    print("PUBLIC_SOURCE_GATES_PASS files=3 functions=6")
    print("PUBLIC_DV_SEI_TAG=0x01000000")
    print("SOURCE_AUX_REQUEST_PROVIDER=dvbldec")
    print("SOURCE_EL_PROVIDER=dveldec")
    print("SOURCE_METADATA_PARSER_CALL=REGISTERED_CALLBACK")
    print("INSTALLED_FIREOS_RECEIVER=NOT_VERIFIED")
    print("P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN")
    print("GAZELLE_FEL_STAGE26_PUBLIC_SOURCE_PASS")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("public_source_dir",nargs="?",type=Path)
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    assert len(PINS)==3 and COMMIT.startswith("24a1e36") and len(COMMIT)==40
    assert gitblob(b"")=="e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    assert function("int sample(void) { if (1) { return 1; } return 0; }","sample").count("return")==2
    print("GAZELLE_FEL_STAGE26_SOURCE_SELFTEST_PASS")
    if args.selftest: return
    if not args.public_source_dir:p.error("pass pinned public source checkout or --selftest")
    audit(args.public_source_dir.expanduser().resolve())

if __name__=="__main__":
    try:main()
    except (OSError,ValueError,UnicodeError,AssertionError) as error:
        print("GAZELLE_FEL_STAGE26_AUDIT_FAIL",error,file=sys.stderr)
        sys.exit(1)
