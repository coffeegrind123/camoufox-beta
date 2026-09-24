#!/bin/bash
# Runs inside camoufox-lab: Xvfb + collector + every configuration in $RUNS.
# CFX_DIR selects the camoufox build under test (default: the image's cg.3).
set -u
export OUT=/lab/out PORT=8765 XDG_CACHE_HOME=${XDG_CACHE_HOME:-/opt/cache}
CFX_DIR=${CFX_DIR:-/opt/camoufox}
mkdir -p $OUT
# PYLIB: test a launcher from /lab/pythonlib instead of the image's.
[ -d /lab/pythonlib ] && pip install -q --no-deps /lab/pythonlib 2>&1 | tail -2
Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp >/dev/null 2>&1 &
export DISPLAY=:99
export EXT=$(hostname -I | awk '{print $1}')
python3 /lab/server.py $PORT $OUT > /lab/out/server.log 2>&1 &
sleep 2

# Same shape as the consumers' launch (app/fox.py), minus the proxy.
FOX='{"os":"windows","humanize":true,"block_webrtc":true,"locale":["sv-SE","sv"],
      "webgl_config":["Google Inc. (NVIDIA)","ANGLE (NVIDIA, NVIDIA GeForce GTX 980 Direct3D11 vs_5_0 ps_5_0), or similar"],
      "geoip":"'"${GEOIP_IP:-81.230.0.1}"'"}'

for r in ${RUNS:-stock raw cfx fox}; do
  case $r in
    stock) TAG=stock timeout 120 python3 /lab/run.py stock /opt/stockff ;;
    raw)   TAG=raw   timeout 120 python3 /lab/run.py raw $CFX_DIR ;;
    cfx)   TAG=cfx   timeout 120 python3 /lab/run.py cfx $CFX_DIR '{}' ;;
    fox)   TAG=fox   timeout 180 python3 /lab/run.py cfx $CFX_DIR "$FOX" ;;
    stock-nc) NOCLICK=1 TAG=$r timeout 120 python3 /lab/run.py stock /opt/stockff ;;
    cfx-nc)   NOCLICK=1 TAG=$r timeout 120 python3 /lab/run.py cfx $CFX_DIR '{}' ;;
    *)     TAG=$r    timeout 180 python3 /lab/run.py cfx $CFX_DIR "${!r}" ;;
  esac
done
ls -la $OUT
