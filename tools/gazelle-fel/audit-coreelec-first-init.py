#!/usr/bin/env python3
"""Read-only, pin-verified CoreELEC FEL-first-native-open source comparison.

Compares public pinned CE sources with the CURRENT Kodi research source.
It does not contact the Cube, modify the decoder, or assert FEL runtime.
Python >=3.9; standard library. --selftest never accesses the network.
"""
from __future__ import annotations
import argparse
import hashlib
import pathlib
import re
import sys
import urllib.request

KODI_PIN = "884eab3a40712e7a853db68eb114d712e9600fc2"
KERNEL_PIN = "c15aebb1ac93028d0aceadf8f35dda2204d33424"
FILES = {
    "ce_kodi_add": (
        f"https://raw.githubusercontent.com/CoreELEC/xbmc/{KODI_PIN}/xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecAmlogic.cpp",
        "36e8ef006050fc6d955c130cd467e1907396628d",
    ),
    "ce_kodi_native": (
        f"https://raw.githubusercontent.com/CoreELEC/xbmc/{KODI_PIN}/xbmc/cores/VideoPlayer/DVDCodecs/Video/AMLCodec.cpp",
        "dce7f6a581cea20313bd98e4251ed22ea44dae61",
    ),
    "ce_amstream": (
        f"https://raw.githubusercontent.com/CoreELEC/media_modules-aml/{KERNEL_PIN}/drivers/stream_input/amports/amstream.c",
        "bb92d1a834fbd542f56e4429459a290f15b93656",
    ),
}

def require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError("REFUSE " + msg)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def download(name: str) -> str:
    url, pinned_blob = FILES[name]
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "gazelle-source-audit/1.0"}), timeout=20) as stream:
        data = stream.read(1_000_001)
    require(len(data) <= 1_000_000, f"{name}_too_large")
    require(git_blob_sha(data) == pinned_blob, f"{name}_blob_identity_changed")
    return data.decode("utf-8", errors="strict")


def ordered(src: str, first: str, second: str, label: str) -> None:
    a = src.find(first)
    b = src.find(second)
    require(a >= 0 and b > a, label)


def inspect_ce(add: str, native: str, driver: str) -> dict:
    # Check the exact call sites, not generic tokens such as "FEL" in comments.
    require("bool CDVDVideoCodecAmlogic::AddData(const DemuxPacket &packet)" in add, "ce_add_entry_missing")
    fn = add.split("bool CDVDVideoCodecAmlogic::AddData(const DemuxPacket &packet)", 1)[1]
    ordered(fn, "doviIsFEL = m_bitstream->GetDoviIsFEL();", "m_Codec->OpenDecoder(m_hints, doviIsFEL)", "ce_fel_before_open")
    require("bool CAMLCodec::OpenDecoder(CDVDStreamInfo &hints, bool doviIsFEL)" in native, "ce_native_entry_missing")
    fn2 = native.split("bool CAMLCodec::OpenDecoder(CDVDStreamInfo &hints, bool doviIsFEL)", 1)[1]
    ordered(fn2, "am_private->gcodec.dec_mode    = STREAM_TYPE_FRAME;", "if (doviIsFEL) // use stream path if not MEL", "ce_default_frame_before_fel")
    fel = fn2.split("if (doviIsFEL) // use stream path if not MEL", 1)[1].split("\n    }", 1)[0]
    require("am_private->gcodec.dec_mode = STREAM_TYPE_STREAM;" in fel, "ce_fel_stream_mode_missing")
    require('"enable_fel 1"' in fel and '"enable_mel 1"' in fel, "ce_global_controls_not_recorded")
    ordered(fn2, "am_private->gcodec.dec_mode = STREAM_TYPE_STREAM;", "m_dll->codec_init_para(&am_private->gcodec, &am_private->vcodec);", "ce_mode_after_init")
    ordered(fn2, "m_dll->codec_init_para(&am_private->gcodec, &am_private->vcodec);", "m_dll->codec_init(&am_private->vcodec)", "ce_config_before_open")
    require('CSysfsPath("/sys/module/amvdec_h265/parameters/nal_skip_policy", 1)' in fn2, "ce_global_sysfs_not_recorded")
    require('amlVideoFile->Open("/dev/video10", O_RDONLY | O_NONBLOCK)' in native, "ce_video10_output_not_recorded")
    require("priv->vdec = vdec_create(port, NULL);" in driver, "ce_master_create_missing")
    ordered(driver, "if (!(port->type & PORT_TYPE_FRAME))", "priv->vdec->slave = vdec_create(port, priv->vdec);", "ce_slave_conditional_missing")
    require("(port->type & PORT_TYPE_DUALDEC)" in driver and "(vdec_get_debug_flags() & 0x100)" in driver, "ce_second_decoder_guard_missing")
    return {"fel_before_decoder_open": True, "stream_before_codec_init": True,
            "ce_global_controls_not_portable": True, "ce_video10_not_android_video30": True,
            "ce_second_vdec_requires_nonframe_and_guard": True}


def inspect_fireos_kodi(worker: str, policy: str) -> dict:
    require("bool CVideoPlayerVideo::OpenStream(CDVDStreamInfo hint)" in worker, "kodi_initial_open_missing")
    require("const bool gazelleDeferredInitial = IsGazelleDeferredStockCandidate(hint, false);" in worker,
            "kodi_initial_deferred_seam_missing")
    initial = worker.split("const bool gazelleDeferredInitial = IsGazelleDeferredStockCandidate(hint, false);", 1)[1]
    require("if (!gazelleDeferredInitial)" in initial[:450], "kodi_hardoff_factory_guard_missing")
    require("codec = CDVDFactoryCodec::CreateVideoCodec(hint, m_processInfo);" in initial[:450],
            "kodi_initial_factory_order_changed")
    require("constexpr bool kDeferredStockResearchEnabled = false;" in policy, "FEL_SWITCH_NOT_OFF")
    require('static_assert(!kDeferredStockResearchEnabled' in policy, "FEL_STATIC_GUARD_MISSING")
    return {"kodi_initial_factory_is_stock": True, "deferred_seam_hard_off": True}


def selftest() -> None:
    add = '''bool CDVDVideoCodecAmlogic::AddData(const DemuxPacket &packet) {
      doviIsFEL = m_bitstream->GetDoviIsFEL();
      if (m_Codec && !m_Codec->OpenDecoder(m_hints, doviIsFEL)) return false;
    }'''
    native = '''bool CAMLCodec::OpenDecoder(CDVDStreamInfo &hints, bool doviIsFEL) {
     am_private->gcodec.dec_mode    = STREAM_TYPE_FRAME;
     if (doviIsFEL) // use stream path if not MEL
     {
       AmlDisplay->aml_set_drmProperty("dv_debug", DRM_MODE_OBJECT_CRTC, "enable_fel 1");
       AmlDisplay->aml_set_drmProperty("dv_debug", DRM_MODE_OBJECT_CRTC, "enable_mel 1");
       am_private->gcodec.dec_mode = STREAM_TYPE_STREAM;
     }
     CSysfsPath("/sys/module/amvdec_h265/parameters/nal_skip_policy", 1);
     m_dll->codec_init_para(&am_private->gcodec, &am_private->vcodec);
     m_dll->codec_init(&am_private->vcodec);
     amlVideoFile->Open("/dev/video10", O_RDONLY | O_NONBLOCK);
    }'''
    driver = '''priv->vdec = vdec_create(port, NULL);
    if (!(port->type & PORT_TYPE_FRAME)) {
      if ((port->type & PORT_TYPE_DUALDEC) || (vdec_get_debug_flags() & 0x100)) {
        priv->vdec->slave = vdec_create(port, priv->vdec);
      }
    }'''
    worker = '''bool CVideoPlayerVideo::OpenStream(CDVDStreamInfo hint) {
      const bool gazelleDeferredInitial = IsGazelleDeferredStockCandidate(hint, false);
      if (!gazelleDeferredInitial) codec = CDVDFactoryCodec::CreateVideoCodec(hint, m_processInfo);
    }'''
    policy = 'constexpr bool kDeferredStockResearchEnabled = false;\nstatic_assert(!kDeferredStockResearchEnabled, "no live use");'
    inspect_ce(add, native, driver)
    inspect_fireos_kodi(worker, policy)
    negatives = [
        lambda: inspect_ce(add.replace('doviIsFEL = m_bitstream->GetDoviIsFEL();', ''), native, driver),
        lambda: inspect_ce(add.replace('doviIsFEL = m_bitstream->GetDoviIsFEL();', 'doviIsFEL = false;'), native, driver),
        lambda: inspect_ce(add, native.replace('am_private->gcodec.dec_mode = STREAM_TYPE_STREAM;', 'am_private->gcodec.dec_mode = STREAM_TYPE_FRAME;'), driver),
        lambda: inspect_ce(add, native.replace('"enable_fel 1"', '"enable_fel 0"'), driver),
        lambda: inspect_ce(add, native.replace('"enable_mel 1"', '"enable_mel 0"'), driver),
        lambda: inspect_ce(add, native.replace('nal_skip_policy", 1', 'nal_skip_policy", 2'), driver),
        lambda: inspect_ce(add, native.replace('Open("/dev/video10"', 'Open("/dev/video30"'), driver),
        lambda: inspect_ce(add, native, driver.replace('if (!(port->type & PORT_TYPE_FRAME))', 'if (1)')),
        lambda: inspect_fireos_kodi(worker, policy.replace('= false;', '= true;')),
        lambda: inspect_fireos_kodi(worker, policy.replace('static_assert(!kDeferredStockResearchEnabled', 'static_assert(kDeferredStockResearchEnabled')),
    ]
    for i, fail in enumerate(negatives):
        try:
            fail()
        except ValueError:
            continue
        raise ValueError(f"SELFTEST_MUTATION_ACCEPTED_{i}")
    require(git_blob_sha(b"test\n") == "9daeafb9864cf43055ae93beb0afd6c7d144bfa4", "git_blob_hasher")
    print("GAZELLE_CE_ANDROID_FIRST_DIVERGENCE_SELFTEST_PASS negative=10 no_device=true fel_off=true")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true", help="Synthetic tests, never network")
    parser.add_argument("--verify-upstream", action="store_true", help="Fetch three pinned PUBLIC CoreELEC sources, verify Git blob IDs, audit actual functions")
    parser.add_argument("--kodi-root", type=pathlib.Path, help="Check local angelcode1/xbmc working tree source and hard-off policy")
    args = parser.parse_args()
    require(args.selftest or args.verify_upstream or args.kodi_root is not None, "no_mode")
    if args.selftest: selftest()
    if args.verify_upstream:
        src = {k: download(k) for k in FILES}
        out = inspect_ce(src["ce_kodi_add"], src["ce_kodi_native"], src["ce_amstream"])
        print("GAZELLE_CE_PINNED_EARLY_FEL_GATE_PASS", " ".join(f"{k}={str(v).lower()}" for k,v in out.items()), "owner_installed_ce_build=NOT_ATTESTED")
    if args.kodi_root is not None:
        base=args.kodi_root.resolve()
        worker=(base/"xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp").read_text(encoding="utf-8")
        policy=(base/"xbmc/cores/VideoPlayer/GazelleDeferredOpenPolicy.h").read_text(encoding="utf-8")
        out=inspect_fireos_kodi(worker, policy)
        print("GAZELLE_FIREOS_KODI_EARLY_FACTORY_GAP_CONFIRMED", " ".join(f"{k}={str(v).lower()}" for k,v in out.items()), "native_FEL=NOT_ENABLED")

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, UnicodeError) as exc:
        sys.exit(str(exc))