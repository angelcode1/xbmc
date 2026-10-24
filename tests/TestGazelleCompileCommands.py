#!/usr/bin/env python3
"""Host-only negative tests for exact Android compiler command attestation."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import tempfile

script = Path(__file__).resolve().parents[1] / "tools/gazelle-fel/compile-android-kodi-tus.py"
spec = importlib.util.spec_from_file_location("compile_android_tus", script)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp).resolve()
    ndk = root / "ndk"
    clang = ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin/clang++"
    clang.parent.mkdir(parents=True)
    clang.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    clang.chmod(0o755)
    os.environ["ANDROID_NDK_HOME"] = str(ndk)
    entries = []
    for i, target in enumerate(mod.TARGETS):
        source = root / target
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("// stub to verify runner commands only\n", encoding="utf-8")
        entries.append({
            "file": str(source),
            "directory": str(root),
            "arguments": [
                str(clang), "--target=armv7a-linux-androideabi28",
                "-c", str(source), "-o", str(root / f"mock{i}.o")
            ],
        })
    db = root / "compile_commands.json"
    def run(values, should_pass: bool, needle: str = "") -> None:
        db.write_text(json.dumps(values), encoding="utf-8")
        try:
            mod.compile_units(db, root)
        except RuntimeError as error:
            if should_pass or needle not in str(error):
                raise
        else:
            if not should_pass:
                raise AssertionError("NEGATIVE_COMMAND_ACCEPTED " + needle)

    run(entries, True)
    bad = json.loads(json.dumps(entries))
    wrong_source = root / "other.cpp"
    wrong_source.write_text("// unrelated\n", encoding="utf-8")
    bad[0]["arguments"][3] = str(wrong_source)
    run(bad, False, "WRONG_COMPILED_SOURCE")
    bad = json.loads(json.dumps(entries))
    bad[0]["arguments"].remove("-c")
    run(bad, False, "WRONG_COMPILED_SOURCE")
    bad = json.loads(json.dumps(entries))
    bad[0]["arguments"].remove("--target=armv7a-linux-androideabi28")
    run(bad, False, "NOT_ANDROID_ARMV7_COMMAND")
    bad = json.loads(json.dumps(entries))
    bad[1]["file"] = str(wrong_source)
    run(bad, False, "COMPILATION_UNIT_NOT_UNIQUE")
    bad = json.loads(json.dumps(entries))
    bad[0]["arguments"][-1] = str(root / "fake.txt")
    run(bad, False, "NOT_OBJECT_OUTPUT")
    bad = json.loads(json.dumps(entries))
    bad.pop()
    run(bad, False, "COMPILATION_UNIT_NOT_UNIQUE")
    # Only source-reviewed CMake ExternalProject targets may be auto-built,
    # and only for an actual, single, unambiguous missing-header diagnostic.
    recover = mod.recoverable_prerequisite
    assert recover("fatal error: 'pcre2.h' file not found", set()) == "build-pcre2"
    assert recover("fatal error: 'nlohmann/json.hpp' file not found", set()) == "build-nlohmann_json"
    assert recover("fatal error: 'tinyxml2.h' file not found", set()) == "build-tinyxml2"
    assert recover("fatal error: 'unknown.h' file not found", set()) is None
    assert recover("fatal error: 'pcre2.h' file not found", {"build-pcre2"}) is None
    assert recover("error: bad application source", set()) is None
    assert recover(
        "fatal error: 'pcre2.h' file not found\\n"
        "fatal error: 'fmt/format.h' file not found", set()
    ) is None
    print("GAZELLE_ANDROID_COMPILE_COMMANDS_SOURCE_SELFTEST_PASS "
          "negative=13 exact_tus=true armv7_only=true "
          "real_android_compilation=false no_device=true")
