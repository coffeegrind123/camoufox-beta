#!/usr/bin/env python3
"""diff.py DIR A B [C...]: compare probe results between configurations."""
import json, sys, os
d = sys.argv[1]; tags = sys.argv[2:]
R = {t: json.load(open(os.path.join(d, t + '.json'))) for t in tags}
base = tags[0]
def hdrs(t):
    out = []
    for l in open(os.path.join(d, t + '.headers.jsonl')):
        j = json.loads(l)
        if j['path'].startswith('/probe.html') or j['path'].startswith('/blank.html'):
            out.append((j['path'][:6], [(k, v) for k, v in j['headers'] if k in ('Accept-Encoding', 'User-Agent', 'Accept-Language', 'Accept', 'Priority')]))
    return out
print('== surface (vs %s)' % base)
b = set(R[base]['surface'] or [])
for t in tags[1:]:
    s = set(R[t]['surface'] or [])
    print(f'  {t}: {len(s)} items, missing {len(b-s)}, extra {len(s-b)}')
    for x in sorted(b - s)[:25]: print('     -', x)
    for x in sorted(s - b)[:25]: print('     +', x)
print('== codecs that differ')
for k in R[base]['codecs']:
    vals = {t: R[t]['codecs'].get(k) for t in tags}
    if len({json.dumps(v, sort_keys=True) for v in vals.values()}) > 1:
        print('  ', k, ' | '.join(f"{t}={v['video']!r}/{v['audio']!r}/{v['mse']}" for t, v in vals.items()))
for key in ('mediaCaps', 'activationAtLoad', 'activationAtEnd', 'asyncStack', 'throwStack', 'wasm', 'anim', 'geo', 'webgpu', 'webrtc', 'errors', 'elapsed'):
    print('==', key)
    for t in tags: print(f'   {t:6}', json.dumps(R[t].get(key))[:300])
print('== pointer')
for t in tags:
    print('  ', t, [(p['type'], p.get('pointerType'), p['isTrusted'], p.get('mozInputSource'), p.get('pressure'), p.get('width')) for p in R[t]['pointer']][:6])
print('== misc')
for k in R[base]['misc']:
    vals = [json.dumps(R[t]['misc'].get(k))[:90] for t in tags]
    print(f'   {k:10}', ' | '.join(vals))
print('== request headers for probe.html')
for t in tags:
    print('  ', t, hdrs(t))
