#!/usr/bin/env python3
"""Stage-only, SHA-gated libbluray AACS stage markers; never deploys or rebuilds.

Only patches an explicitly supplied source file into a NEW output path.
No media bytes, key material, callback paths or pointer values are logged.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import sys

# libbluray 1.5.x API-level anchor. Refuse unless the exact call order exists.
OLD = """    if (init && open_device) {
        p->aacs = init();
        DL_CALL(p->h_libaacs, aacs_set_fopen, p->aacs, file_open_handle, file_open_fp);
        error_code = open_device(p->aacs, device, keyfile_path);
    } else if (open2) {"""

NEW = r"""    if (init && open_device) {
#if defined(__ANDROID__) && defined(GAZELLE_AACS_GATE_TRACE)
        BD_DEBUG(DBG_BLURAY, "GAZELLE_AACS_GATE_V1 phase=context_begin\n");
#endif
        p->aacs = init();
#if defined(__ANDROID__) && defined(GAZELLE_AACS_GATE_TRACE)
        BD_DEBUG(DBG_BLURAY, "GAZELLE_AACS_GATE_V1 phase=context_end ok=%d\n",
                 p->aacs != NULL);
#endif
        DL_CALL(p->h_libaacs, aacs_set_fopen, p->aacs, file_open_handle, file_open_fp);
#if defined(__ANDROID__) && defined(GAZELLE_AACS_GATE_TRACE)
        BD_DEBUG(DBG_BLURAY, "GAZELLE_AACS_GATE_V1 phase=callback_set\n");
        BD_DEBUG(DBG_BLURAY, "GAZELLE_AACS_GATE_V1 phase=open_begin device_null=%d\n",
                 device == NULL);
#endif
        error_code = open_device(p->aacs, device, keyfile_path);
#if defined(__ANDROID__) && defined(GAZELLE_AACS_GATE_TRACE)
        BD_DEBUG(DBG_BLURAY, "GAZELLE_AACS_GATE_V1 phase=open_end rc=%d\n",
                 error_code);
#endif
    } else if (open2) {"""


def stage(source: str) -> str:
    if "GAZELLE_AACS_GATE_V1" in source:
        raise ValueError("already instrumented or ambiguous input")
    if source.count(OLD) != 1:
        raise ValueError("AACS 1.5.x call-sequence anchor absent or ambiguous")
    if source.count('dl_dlsym(p->h_libaacs, "aacs_open_device")') != 1:
        raise ValueError("aacs_open_device symbol-resolution anchor missing")
    if "BD_DEBUG(DBG_BLURAY" not in source:
        raise ValueError("libbluray logging contract absent")
    return source.replace(OLD, NEW, 1)


def selftest():
    fixture = ('BD_DEBUG(DBG_BLURAY, "initial");\n'
               'open_device = dl_dlsym(p->h_libaacs, "aacs_open_device");\n'
               + OLD + '\n')
    # The actual source has an assignment to the dlsym; only uniqueness matters.
    result = stage(fixture)
    assert result.count("GAZELLE_AACS_GATE_V1") == 5
    assert result.count(OLD) == 0
    assert result.index("phase=context_begin") < result.index("p->aacs = init();")
    assert result.index("phase=context_end") < result.index("phase=open_begin")
    assert result.index("phase=open_begin") < result.index("error_code = open_device(")
    assert result.index("phase=open_end") > result.index("error_code = open_device(")
    for bad in (fixture.replace(OLD, ""), fixture + OLD, result):
        try:
            stage(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("mutant source unexpectedly accepted")
    print("AACS_GATE_V1_STAGE_SELFTEST_PASS")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--source", type=Path)
    p.add_argument("--out", type=Path)
    p.add_argument("--expected-sha256")
    args = p.parse_args()

    if args.selftest:
        selftest()
        return
    if not all((args.source, args.out, args.expected_sha256)):
        p.error("--source, --out and --expected-sha256 are all mandatory")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", args.expected_sha256):
        p.error("--expected-sha256 must be an exact 64-character digest")
    if args.source.is_symlink() or not args.source.is_file():
        p.error("source must be an existing regular non-symlink file")
    if args.out == args.source or args.out.resolve() == args.source.resolve():
        p.error("refusing in-place modification")
    if args.out.exists() or args.out.is_symlink():
        p.error("output must not exist")
    if not args.out.parent.is_dir():
        p.error("output directory must already exist")

    raw = args.source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest.lower() != args.expected_sha256.lower():
        p.error("SOURCE_SHA256_MISMATCH actual=" + digest)
    try:
        original = raw.decode("utf-8")
        modified = stage(original)
    except (ValueError, UnicodeDecodeError) as e:
        p.error("SOURCE_CONTRACT_REFUSED " + str(e))
    new = modified.encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(args.out, flags, 0o644)
    with os.fdopen(fd, "wb") as output:
        output.write(new)
    print("AACS_GATE_V1_STAGED_ONLY")
    print("source_sha256=" + digest)
    print("staged_sha256=" + hashlib.sha256(new).hexdigest())
    print("deploy=NOT_PERFORMED build=NOT_PERFORMED aacs=NOT_TESTED")


if __name__ == "__main__":
    main()
