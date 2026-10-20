#!/usr/bin/env python3
"""Gazelle FEL Stage38: bounded host-only read of current VFM provider graph.

No firmware, property, sysfs, log, process or playback writes. User controls
playback. Store ONLY allowlisted VFM names/counts, no raw sysfs/log output.
Provider co-occurrence and empty provider lists NEVER prove an alias or failure.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import zipfile

PHASES = ('idle', 'P8', 'P7')
SAMPLES = 3
SAMPLE_DELAY = 2
TIMEOUT = 12
MAX_TEXT = 65536
PROBES = {
    'vfm_map': '/sys/class/vfm/map',
    'dv_provider': '/sys/class/amdolby_vision/dv_provider',
    'dv_source': '/sys/class/amdolby_vision/src_format',
    'vdec_status': '/sys/class/vdec/vdec_status',
}
NODES = frozenset((
    'decoder', 'decoder.h265', 'decoder.h265.00', 'decoder.h265.01',
    'dvbldec', 'dvbldec2', 'dveldec', 'dveldec2', 'dvel',
    'v4lvideo.0', 'v4lvideo.1', 'videopip', 'amvideo',
    'v4lvideo.2', 'ppmgr', 'deinterlace', 'amlvideo',
    'videosync.0', 'videosync.1',
))
ROUTE_NAMES = frozenset(('dvblpath', 'dvelpath', 'dvblpath2', 'dvelpath2',
                         'default', 'default_amlvideo2', 'dvhdmiin'))
PROBE_MAX_BYTES = {'vfm_map': MAX_TEXT, 'dv_provider': 8192,
                   'dv_source': 8192, 'vdec_status': 16384}
NODE_TOKEN = re.compile(r'^([A-Za-z_][A-Za-z0-9_.-]{0,48})(?:\((\d{1,6})\))?$')
ROUTE_RE = re.compile(r'^\s*\[\d{1,3}\]\s+([A-Za-z0-9_.-]{1,50})\s*\{\s*([^{}]{0,2000})\}\s*$', re.M)


def parse_node(token):
    matched = NODE_TOKEN.fullmatch(token.strip())
    if not matched or matched.group(1) not in NODES:
        return None
    return {'name': matched.group(1),
            'count': int(matched.group(2)) if matched.group(2) is not None else None}


def parse_map(payload):
    """Never return unknown names or raw map lines."""
    routes = []
    for matched in ROUTE_RE.finditer(payload):
        label = matched.group(1)
        if label not in ROUTE_NAMES:
            continue
        tokens = matched.group(2).split()[:40]
        nodes = [parsed for token in tokens if (parsed := parse_node(token))]
        routes.append({'route': label, 'nodes': nodes})
    section = None
    seen_provider_section = False
    seen_receiver_section = False
    registered = set()
    receivers = set()
    for line in payload.splitlines():
        s = line.strip()
        if s == 'provider list:':
            section = 'provider'; seen_provider_section = True; continue
        if s == 'receiver list:':
            section = 'receiver'; seen_receiver_section = True; continue
        if not s:
            continue
        if '{' in s or s.endswith(':') or s.startswith('['):
            section = None; continue
        if section in ('provider', 'receiver'):
            name = s.split()[0]
            parsed = parse_node(name)
            if parsed:
                (registered if section == 'provider' else receivers).add(parsed['name'])
    pair_in_same_route = any(
        {'decoder.h265', 'dvbldec'} <= {item['name'] for item in r['nodes']}
        for r in routes)
    counts = {}
    for name in ('decoder.h265', 'dvbldec', 'dveldec', 'dvbldec2', 'dveldec2'):
        counts[name] = [n['count'] for r in routes for n in r['nodes']
                        if n['name'] == name and n['count'] is not None]
    return {
        'route_count_recognized': len(routes),
        'routes': routes,
        'provider_section_seen': seen_provider_section,
        'receiver_section_seen': seen_receiver_section,
        'registered_known_providers': sorted(registered),
        'registered_known_receivers': sorted(receivers),
        'recognized_route_counts': counts,
        'decoder_h265_dvbldec_same_route': pair_in_same_route,
        'alias_or_forwarding_proven': False,
    }


def parse_dolby_provider(raw):
    return {'known_provider_tokens': [x for x in raw.split()
                                      if x in NODES]}


def parse_source(raw):
    m = re.search(r'^inst1:\s*([^\n]{1,120})', raw, re.M)
    if not m:
        return 'UNKNOWN'
    if 'FORMAT_DOVI' in m[1]:
        return 'DOVI'
    if 'FORMAT_HDR10' in m[1]:
        return 'HDR10'
    if 'FORMAT_SDR' in m[1]:
        return 'SDR'
    return 'OTHER_OR_UNKNOWN'


def parse_decoder(raw):
    if re.search(r'\bNo vdec\s*\.', raw, re.I):
        return 'NO_VDEC'
    if not raw.strip():
        return 'UNKNOWN'
    if re.search(r'\b(?:hevc|h265)\b', raw, re.I):
        return 'HEVC_REPORT'
    return 'NONEMPTY_UNCLASSIFIED'


def device_path():
    if os.environ.get('ADB'):
        adb = shutil.which(os.environ['ADB'])
    else:
        adb = shutil.which('adb')
        if not adb:
            fallback = '/Applications/adblink.app/Contents/MacOS/adbfiles/adb'
            adb = fallback if Path(fallback).is_file() else None
    if not adb:
        raise RuntimeError('adb missing; install Android platform-tools or set ADB=...')
    p = subprocess.run((adb, 'devices'), capture_output=True, text=True,
                       errors='replace', timeout=TIMEOUT)
    connected = [line.split() for line in p.stdout.splitlines()[1:]
                 if len(line.split()) == 2 and line.split()[1] == 'device']
    if p.returncode or len(connected) != 1:
        raise RuntimeError('require exactly one authorized ADB device')
    return adb


def remote_read(adb, key):
    if key not in PROBES:
        raise ValueError('read path not allowlisted')
    try:
        res = subprocess.run([adb, 'shell', "su -c 'cat " + PROBES[key] + "'"],
                             capture_output=True, text=True, errors='replace',
                             timeout=TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        return {'status': 'TIMEOUT', 'value': None}
    if res.returncode:
        return {'status': 'UNAVAILABLE', 'value': None}
    raw = res.stdout.replace('\r', '')
    if len(raw.encode('utf-8')) > PROBE_MAX_BYTES[key]:
        return {'status': 'TRUNCATED', 'value': None}
    if key == 'vfm_map':
        parsed = parse_map(raw)
    elif key == 'dv_provider':
        parsed = parse_dolby_provider(raw)
    elif key == 'dv_source':
        parsed = parse_source(raw)
    else:
        parsed = parse_decoder(raw)
    return {'status': 'OK', 'value': parsed}


def take(adb, phase, ordinal):
    start = dt.datetime.now(dt.timezone.utc).isoformat(timespec='milliseconds')
    probes = {key: remote_read(adb, key) for key in PROBES}
    end = dt.datetime.now(dt.timezone.utc).isoformat(timespec='milliseconds')
    return {'phase': phase, 'sample': ordinal,
            'started_utc': start, 'finished_utc': end, 'probes': probes}


def summary(rows):
    txt = [
        'GAZELLE_FEL_STAGE38_PROVIDER_GRAPH_CAPTURE',
        'DEVICE_WRITES=NONE',
        'RAW_SYSFS_DATA_RETAINED=NO',
        'ROUTE_NAMES_ARE_CONFIGURED_CHAINS_NOT_LIVE_DECODER_PROOF',
        'PROVIDER_ALIAS=NOT_PROVEN',
        'P7_RECEIVER_AUX_PAYLOAD=NOT_MEASURED',
        'P7_EL_DECODER=NOT_PROVEN',
        'P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN',
    ]
    for phase in PHASES:
        for s in (x for x in rows if x['phase'] == phase):
            p = s['probes']
            route = p['vfm_map']['value'] or {}
            counts = route.get('recognized_route_counts') or {}
            known = route.get('registered_known_providers') or []
            source = p['dv_source']['value']
            txt.append('PHASE=%s SAMPLE=%s source=%s vdec=%s map=%s provider_list=%s known_providers=%s '%(
                phase, s['sample'], source, p['vdec_status']['value'],
                p['vfm_map']['status'], route.get('provider_section_seen', 'UNKNOWN'),
                ','.join(known) or '(none)') +
                'dvbldec_counts=%s dveldec_counts=%s co_route=%s'%(
                    counts.get('dvbldec', []), counts.get('dveldec', []),
                    route.get('decoder_h265_dvbldec_same_route', 'UNKNOWN')))
    txt += ['ABSENT_PROVIDER_LABEL_IS_NOT_PROOF_OF_NO_DECODER',
            'NON_ATOMIC_PROBE_READS=true',
            'GAZELLE_FEL_STAGE38_CAPTURE_COMPLETE']
    return '\n'.join(txt) + '\n'


def selftest():
    real_idle = '''[00]  default { decoder(0) ppmgr(0) deinterlace(0) amvideo}
[02]  dvblpath { dvbldec(0) v4lvideo.0}
[03]  dvelpath { dveldec(0) dvel}
[04]  dvblpath2 { dvbldec2(0) videopip}
[05]  dvelpath2 { dveldec2(0) dvel}
provider list:

receiver list:
   v4lvideo.0
   dvel
'''
    p = parse_map(real_idle)
    assert p['registered_known_providers'] == [] and p['provider_section_seen']
    assert p['recognized_route_counts']['dvbldec'] == [0]
    assert p['recognized_route_counts']['dveldec'] == [0]
    assert p['decoder_h265_dvbldec_same_route'] is False
    active = parse_map('''[02] dvblpath { decoder.h265(3) dvbldec(1) v4lvideo.0 }
provider list:
 decoder.h265
 dvbldec
receiver list:
 v4lvideo.0
''')
    assert active['registered_known_providers'] == ['decoder.h265', 'dvbldec']
    assert active['decoder_h265_dvbldec_same_route'] is True
    assert active['alias_or_forwarding_proven'] is False
    assert parse_node('123ABCsecret') is None
    assert parse_node('decoder.h265(4)') == {'name': 'decoder.h265', 'count': 4}
    assert parse_source('inst1: HDR10 FORMAT_HDR10') == 'HDR10'
    assert parse_source('inst1: DV FORMAT_DOVI') == 'DOVI'
    assert parse_decoder('No vdec.') == 'NO_VDEC'
    assert list(PHASES) == ['idle', 'P8', 'P7'] and SAMPLES == 3
    assert all(p.startswith('/sys/class/') and p.count("'") == 0
               for p in PROBES.values())
    print('GAZELLE_FEL_STAGE38_SOURCE_SELFTEST_PASS')


def capture(out):
    adb = device_path()
    print('Stage38: all reads are from existing status files; no device writes.')
    rows = []
    prompts = {
        'idle': 'Stop all Kodi video playback.',
        'P8': 'Start the known-working Profile 8 video.',
        'P7': 'Stop P8 and start the Profile 7 FEL test video.',
    }
    for phase in PHASES:
        print('\n%s: %s Press Enter once in that state.'%(phase, prompts[phase]),flush=True)
        input()
        for ordinal in range(1, SAMPLES+1):
            rows.append(take(adb, phase, ordinal))
            print('  %s sample %d/%d complete'%(phase, ordinal, SAMPLES),flush=True)
            if ordinal < SAMPLES:
                time.sleep(SAMPLE_DELAY)
    out.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M%S')
    prefix = 'stage38-provider-graph-' + stamp
    output_json = out / (prefix + '.json')
    output_txt = out / (prefix + '.txt')
    output_zip = out / (prefix + '.zip')
    output_json.write_text(json.dumps({
        'schema': 'gazelle-fel-stage38-v1',
        'device_writes': False,
        'raw_sysfs_retained': False,
        'user_controlled_playback': True,
        'probe_reads_atomic': False,
        'observations': rows,
    }, indent=2) + '\n', encoding='utf-8')
    output_txt.write_text(summary(rows), encoding='utf-8')
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(output_json, arcname=output_json.name)
        z.write(output_txt, arcname=output_txt.name)
    print(summary(rows),end='')
    print('UPLOAD_FILE=' + str(output_zip))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    action = p.add_mutually_exclusive_group(required=True)
    action.add_argument('--selftest',action='store_true')
    action.add_argument('--capture',action='store_true')
    p.add_argument('--out', type=Path,
                   default=Path.home()/'Downloads'/'gazelle-fel-stage38-results')
    opts = p.parse_args()
    selftest()
    if opts.capture:
        capture(opts.out.expanduser())


if __name__ == '__main__':
    try:
        main()
    except (OSError,ValueError,subprocess.TimeoutExpired,RuntimeError,EOFError,KeyboardInterrupt) as exc:
        print('GAZELLE_FEL_STAGE38_FAIL',str(exc),file=sys.stderr)
        sys.exit(1)
