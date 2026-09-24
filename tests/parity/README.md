# Parity probe: camoufox against stock Firefox

Measures what a page can see, in the page's own main world, and diffs it between
stock Firefox and camoufox. Every change in [docs/HOST-PARITY.md](../../docs/HOST-PARITY.md)
was found and checked with it.

| File | What |
|---|---|
| `probe.html` | The page. Records the API surface (globals, prototypes, CSS properties), codec answers (`canPlayType`, `isTypeSupported`, `decodingInfo`), user activation, wasm/JS timing, debuggee side effects, CSS animation timing, geolocation, WebGPU adapter, WebRTC candidates, pointer events, and value-level fingerprint data (fonts and font metrics, system colours, form-control sizes, media queries, voices, audio, WebGL parameters, Intl). POSTs the result. |
| `server.py` | Collector. Logs every request's headers (so `Accept-Encoding` is compared on the wire) and writes `out/<tag>.json`. |
| `run.py` | Runs one configuration: `stock` (Firefox binary, real X input), `raw` (camoufox binary, no Playwright), `cfx` (camoufox through the launcher, JSON kwargs). |
| `suite.sh` | Xvfb + collector + each configuration in `$RUNS`, inside a container. |
| `go.sh` | Creates that container, copies this directory in, copies `out/` back to `results/<name>`. |
| `diff.py`, `fpdiff.py` | Diff two or more results; `fpdiff.py` walks the value-level section. |
| `ctx_leak.py` | Cross-context leaks in one browser (font list, voices, timezone). |

## Reference measurements

- **Stock Linux:** `/opt/stockff` in the image (`firefox-152.0.4.tar.xz` from ftp.mozilla.org).
- **Stock Windows:** serve this directory (`python3 server.py 8765 out`), extract
  `Firefox Setup 152.0.4.exe /ExtractDir=<dir>`, **delete `updater.exe`**, and open
  `http://localhost:8765/probe.html?tag=win152&noclick` with a fresh profile holding
  `run.py`'s `PREFS` as `user.js`. Without deleting the updater, the copy updated
  itself to 156 mid-session and silently produced 156 results.

## Pitfalls

- Measure in the page. `page.evaluate` runs in an isolated world and misses main-world leaks.
- `127.0.0.1` is a potentially trustworthy origin, so plain-HTTP header checks need
  a non-loopback origin (`probe.html?ext=` does this with the container's own IP).
- A proxy in the environment (`http_proxy`) makes stock Firefox stop at an auth prompt.
- GPU presence changes which APIs exist; `go.sh` passes the WSL2 GPU through unless `NO_GPU=1`.
