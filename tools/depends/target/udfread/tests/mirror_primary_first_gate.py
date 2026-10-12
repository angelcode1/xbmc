#!/usr/bin/env python3
"""Host behavior gate for the exact libudfread _map_metadata_partition function.

Run against the pinned, extracted 1.2.0 sources AFTER both repository
patches are applied. No device, media, disc data, Kodi, network or root.
The function under test is lifted verbatim and compiled with a minimal
synthetic block-input/file-entry harness. No substring-only "test".
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

def find_function(source):
    marker = "static int _map_metadata_partition("
    start = source.find(marker)
    if start < 0 or source.find(marker, start + 1) >= 0:
        raise AssertionError("exactly one metadata mapper required")
    brace = source.find("{", start)
    if brace < 0:
        raise AssertionError("metadata mapper has no body")
    depth = 0
    for pos in range(brace, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[start:pos + 1]
    raise AssertionError("unterminated metadata mapper")

HEADER = r"""
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#define UDF_BLOCK_SIZE 2048
#define ECMA_ExtendedFileEntry 266
#define UDF_FT_METADATA 250
#define UDF_FT_METADATA_MIRROR 251
#define udf_trace(...) ((void)0)
#define udf_log(...) ((void)0)
#define udf_error(...) ((void)0)
typedef struct udfread_block_input { int unused; } udfread_block_input;
struct partition_descriptor { uint32_t start_block; uint16_t number; };
struct udf_partitions {
    uint32_t num_partition;
    struct { uint16_t number; uint32_t lba, mirror_lba; } p[2];
};
struct file_entry {
    uint8_t file_type;
    struct { struct { uint32_t lba; } ad[1]; } data;
};
static unsigned reads_primary, reads_mirror;
static int primary_valid, mirror_valid;
static int _read_descriptor_block(udfread_block_input *input, uint32_t lba, uint8_t *buf)
{
    (void)input;
    memset(buf, 0, UDF_BLOCK_SIZE);
    if (lba == 1004) {
        ++reads_primary;
        if (!primary_valid) return -1;
        buf[0] = UDF_FT_METADATA;
        return ECMA_ExtendedFileEntry;
    }
    if (lba == 1005) {
        ++reads_mirror;
        if (!mirror_valid) return -1;
        buf[0] = UDF_FT_METADATA_MIRROR;
        return ECMA_ExtendedFileEntry;
    }
    return -1;
}
static struct file_entry *decode_ext_file_entry(const uint8_t *buf,
                                                 uint32_t n, uint16_t part)
{
    (void)n; (void)part;
    struct file_entry *fe = calloc(1, sizeof(*fe));
    if (!fe) return NULL;
    fe->file_type = buf[0];
    fe->data.ad[0].lba = 10;
    return fe;
}
static void free_file_entry(struct file_entry **fe)
{
    free(*fe); *fe = NULL;
}
"""

MAIN = r"""
static int check(int good_primary, int good_mirror,
                 int expect_success, unsigned expect_primary, unsigned expect_mirror)
{
    udfread_block_input input = {0};
    struct udf_partitions part = {0};
    struct partition_descriptor pd = {1000, 0};
    reads_primary = reads_mirror = 0;
    primary_valid = good_primary; mirror_valid = good_mirror;
    const int rc = _map_metadata_partition(&input, &part, 4, 5, &pd);
    if ((rc == 0) != expect_success ||
        reads_primary != expect_primary ||
        reads_mirror != expect_mirror ||
        (expect_success && part.p[1].lba != 1010)) {
        fprintf(stderr, "MIRROR_GATE_FAIL primary=%d mirror=%d rc=%d reads=%u,%u mapped=%u\n",
                good_primary, good_mirror, rc, reads_primary,
                reads_mirror, part.p[1].lba);
        return 1;
    }
    return 0;
}
int main(void)
{
    int failures = 0;
    /* This is the actual Cube failure: mirror unreadable; primary healthy. */
    failures += check(1, 0, 1, 1, 0);
    /* Primary healthy: even a healthy mirror is never needed during mount. */
    failures += check(1, 1, 1, 1, 0);
    /* Primary missing: preserve mirror fallback. */
    failures += check(0, 1, 1, 1, 1);
    /* Neither readable: fail closed. */
    failures += check(0, 0, 0, 1, 1);
    if (failures) return 1;
    puts("LIBUDFREAD_120_PRIMARY_FIRST_MIRROR_FALLBACK_HOST_PASS");
    return 0;
}
"""

def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: mirror_primary_first_gate.py /path/to/libudfread-1.2.0")
    source = pathlib.Path(sys.argv[1]) / "src/udfread.c"
    content = source.read_text()
    func = find_function(content)
    if "i == 1 && part->p[1].lba" not in func:
        raise AssertionError("primary-first safeguard not in compiled function")
    cc = shutil.which("cc")
    if not cc:
        raise RuntimeError("C compiler required")
    with tempfile.TemporaryDirectory(prefix="gazelle-udf-host-") as tmp:
        src = pathlib.Path(tmp) / "mirror_gate.c"
        exe = pathlib.Path(tmp) / "mirror_gate"
        src.write_text(HEADER + "\n" + func + "\n" + MAIN)
        subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
                        str(src), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
    print("LIBUDFREAD_PINNED_SOURCE_FUNCTION_COMPILED_PASS no_disc=1")

if __name__ == "__main__":
    main()
