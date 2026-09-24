#!/usr/bin/env python3
"""fpdiff.py A.json B.json: key-by-key diff of the value-level fingerprint section."""
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
fa, fb = a.get('fp') or {}, b.get('fp') or {}
if isinstance(fa, str) or isinstance(fb, str): print('ERR', fa if isinstance(fa, str) else fb); sys.exit()
def walk(x, y, path):
    if isinstance(x, dict) and isinstance(y, dict):
        for k in sorted(set(x) | set(y)): walk(x.get(k), y.get(k), path + [k])
    elif isinstance(x, list) and isinstance(y, list) and all(isinstance(i, str) for i in x + y) and len(x) > 6:
        sx, sy = set(x), set(y)
        if sx != sy: print('.'.join(path), '\n    only A:', sorted(sx - sy)[:40], '\n    only B:', sorted(sy - sx)[:40])
    elif x != y:
        print('.'.join(path), '\n    A:', json.dumps(x)[:300], '\n    B:', json.dumps(y)[:300])
walk(fa, fb, [])
