#!/bin/bash
# go.sh NAME [docker -e args...]: run suite.sh in a fresh container, copy results to results/NAME.
#
# The image needs camoufox in /opt/camoufox, the launcher, Xvfb and xdotool, and
# stock Firefox in /opt/stockff (see README.md). Files reach the container by
# `docker cp`, not a bind mount, so this works from inside another container.
here=$(cd "$(dirname "$0")" && pwd)
name=$1; shift
img=${IMG:-camoufox-lab:latest}
c=parity-$name-$$
gpu=()
if [ -z "$NO_GPU" ]; then
  # WSL2 GPU passthrough (Mesa d3d12): GPU presence changes which APIs exist.
  gpu=(--device /dev/dxg -v /usr/lib/wsl:/usr/lib/wsl:ro -e LD_LIBRARY_PATH=/usr/lib/wsl/lib -e GALLIUM_DRIVER=d3d12)
fi
docker create --init --name "$c" --shm-size 2g "${gpu[@]}" "$@" "$img" bash /lab/suite.sh >/dev/null
docker cp "$here" "$c:/lab"
docker start -a "$c"
mkdir -p "$here/results"
rm -rf "$here/results/$name"
docker cp "$c:/lab/out" "$here/results/$name"
docker rm -f "$c" >/dev/null
