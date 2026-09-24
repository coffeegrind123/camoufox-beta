"""
Spoofed getters cost what stock Firefox's do, timed from script.

Every spoofed getter consults the config or the per-context store. When those
lookups were slow the difference was visible to a page with no reference
machine: against stock Firefox 152.0.4 on the same host, screen.width took
820-940 ns vs 130 ns, navigator.hardwareConcurrency 380-680 ns vs 45 ns, and
screen.width's cost relative to screen.orientation.type (untouched by
Camoufox) was ~10x where stock's is ~2x.

This guard times the same page in stock Firefox of the version in upstream.sh
(STOCK_FIREFOX=<path to the firefox binary>, else downloaded once into
~/.cache/camoufox-ci) and in Camoufox with a per-context identity, on the same
machine, and fails when a getter costs more than SLOWER_FACTOR times stock and
at least MIN_GAP_NS more. Each figure is the fastest of several rounds over
two launches, so a busy runner inflates both browsers rather than one.

    python tests/patches/getter-cost-parity.py
"""

import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import resolve_binary  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
LAUNCHES = 2
SLOWER_FACTOR = 2.0
MIN_GAP_NS = 30.0
PAGE_TIMEOUT_S = 240

# Spoofed getters, and controls Camoufox does not touch (a sanity check that
# the two browsers are comparable on this machine).
WINDOW = [
    "screen.width", "screen.height", "screen.availWidth", "screen.availHeight",
    "screen.colorDepth", "screen.pixelDepth", "devicePixelRatio", "innerWidth",
    "innerHeight", "outerWidth", "screenX", "history.length",
    "navigator.hardwareConcurrency", "navigator.globalPrivacyControl",
    "navigator.maxTouchPoints", "G.getParameter(G.MAX_TEXTURE_SIZE)",
    "C.measureText('mmmmmmmmmmlli').width",
    "matchMedia('(color: 8)').matches", "matchMedia('(resolution: 1dppx)').matches",
]
WORKER = [
    "navigator.hardwareConcurrency", "navigator.globalPrivacyControl",
    "new Date(1e12).getTimezoneOffset()",
]
CONTROLS = ["screen.orientation.type", "navigator.onLine"]

PAGE = """<!doctype html><meta charset=utf-8><body><script>
function bench(exprs, setup) {
  eval(setup);
  const out = {};
  const ctx = typeof C === 'undefined' ? [null, null] : [C, G];
  const mk = (e) => new Function('C', 'G', 'N',
    'let t = performance.now(); let x; for (let i = 0; i < N; i++) { x = (' + e + '); } return performance.now() - t;');
  const empty = mk('i');
  const time = (f, N) => { let b = Infinity; for (let r = 0; r < 7; r++) b = Math.min(b, f(ctx[0], ctx[1], N)); return b; };
  for (const e of exprs) {
    let f;
    try { f = mk(e); f(ctx[0], ctx[1], 10); } catch (err) { out[e] = null; continue; }
    let N = 100;
    while (N < 5e6 && f(ctx[0], ctx[1], N) < 25) N *= 4;
    out[e] = Math.max(0, time(f, N) - time(empty, N)) * 1e6 / N;
  }
  return out;
}
(async () => {
  const spec = JSON.parse(decodeURIComponent(location.hash.slice(1)));
  const src = 'const bench = ' + bench.toString() + '; onmessage = e => postMessage(bench(e.data, ""));';
  const w = new Worker(URL.createObjectURL(new Blob([src])));
  const worker = await new Promise(r => { w.onmessage = e => r(e.data); w.postMessage(spec.worker); });
  const win = bench(spec.window,
    "var C = document.createElement('canvas').getContext('2d'); var G = document.createElement('canvas').getContext('webgl');");
  const res = {window: win, worker};
  document.body.dataset.result = JSON.stringify(res);
  fetch('/result', {method: 'POST', body: JSON.stringify(res)});
})();
</script></body>"""


class Server(http.server.ThreadingHTTPServer):
    results = None


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def log_error(self, *a):
        pass

    def do_GET(self):
        body = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.server.results.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(204)
        self.end_headers()


def firefox_version():
    for line in (REPO / "upstream.sh").read_text().splitlines():
        if line.startswith("version="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("upstream.sh has no version=")


def stock_firefox():
    if os.environ.get("STOCK_FIREFOX"):
        return Path(os.environ["STOCK_FIREFOX"])
    version = firefox_version()
    root = Path.home() / ".cache" / "camoufox-ci" / f"stock-firefox-{version}"
    binary = root / "firefox" / "firefox"
    if binary.exists():
        return binary
    url = f"https://archive.mozilla.org/pub/firefox/releases/{version}/linux-x86_64/en-US/firefox-{version}.tar.xz"
    print(f"downloading {url}")
    root.mkdir(parents=True, exist_ok=True)
    archive = root / "firefox.tar.xz"
    with urllib.request.urlopen(url, timeout=300) as resp, open(archive, "wb") as fh:
        shutil.copyfileobj(resp, fh)
    with tarfile.open(archive) as tar:
        tar.extractall(root)
    archive.unlink()
    # A reference browser that updates itself stops being the reference.
    (root / "firefox" / "updater").unlink(missing_ok=True)
    return binary


def prepare_stock(binary):
    """Refuse a reference that is not the pinned version, and drop any update
    it staged. Stock Firefox downloads updates even with its updater deleted,
    and with one pending it exits at launch instead of loading the page."""
    root = binary.parent
    for name in ("updates", "active-update.xml", "updates.xml"):
        path = root / name
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    ini = (root / "application.ini").read_text()
    version = next((l.split("=", 1)[1] for l in ini.splitlines() if l.startswith("Version=")), None)
    if version != firefox_version():
        raise SystemExit(f"stock Firefox at {root} is {version}, not {firefox_version()}")


def no_proxy_env():
    # A proxy in the environment makes stock Firefox stop at an auth prompt.
    return {k: v for k, v in os.environ.items() if "proxy" not in k.lower()}


def run_stock(binary, url):
    prepare_stock(binary)
    srv_results = []
    profile = tempfile.mkdtemp()
    Path(profile, "user.js").write_text(
        'user_pref("app.update.enabled", false);\n'
        'user_pref("browser.shell.checkDefaultBrowser", false);\n'
        'user_pref("datareporting.policy.dataSubmissionEnabled", false);\n'
        'user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);\n'
        'user_pref("browser.aboutwelcome.enabled", false);\n')
    return srv_results, subprocess.Popen(
        [str(binary), "--headless", "--no-remote", "--profile", profile, url],
        env=no_proxy_env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_camoufox(binary, url):
    from camoufox.sync_api import Camoufox
    from camoufox.fingerprints import generate_context_fingerprint

    fp = generate_context_fingerprint(os="windows")
    with Camoufox(os="windows", headless=True, executable_path=str(binary),
                  i_know_what_im_doing=True) as browser:
        ctx = browser.new_context(**fp["context_options"])
        ctx.add_init_script(fp["init_script"])
        page = ctx.new_page()
        page.goto(url)
        page.wait_for_function("document.body.dataset.result", timeout=PAGE_TIMEOUT_S * 1000)
        return json.loads(page.evaluate("document.body.dataset.result"))


def fastest(runs):
    out = {}
    for where in ("window", "worker"):
        out[where] = {}
        for expr in runs[0][where]:
            values = [r[where][expr] for r in runs if r[where].get(expr) is not None]
            out[where][expr] = min(values) if values else None
    return out


def main() -> int:
    camoufox_bin = resolve_binary()
    stock_bin = stock_firefox()

    server = Server(("127.0.0.1", 0), Handler)
    server.results = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    spec = json.dumps({"window": WINDOW + CONTROLS, "worker": WORKER + CONTROLS[1:]})
    url = f"http://127.0.0.1:{server.server_address[1]}/#" + urllib.request.quote(spec)

    stock_runs, camou_runs = [], []
    try:
        for _ in range(LAUNCHES):
            server.results = []
            _, proc = run_stock(stock_bin, url)
            deadline = time.time() + PAGE_TIMEOUT_S
            while not server.results and time.time() < deadline:
                time.sleep(0.5)
            proc.terminate()
            proc.wait(15)
            if not server.results:
                print("FAIL: stock Firefox never reported -- check is vacuous")
                return 1
            stock_runs.append(server.results[0])
            camou_runs.append(run_camoufox(camoufox_bin, url))
    finally:
        server.shutdown()

    stock, camou = fastest(stock_runs), fastest(camou_runs)
    failures = []
    print(f"{'':6s} {'expression':44s} {'stock':>8s} {'camoufox':>9s}  ns/op")
    for where in ("window", "worker"):
        for expr, s in stock[where].items():
            c = camou[where].get(expr)
            if s is None or c is None:
                print(f"{where:6s} {expr[:44]:44s} {'-':>8s} {'-':>9s}  not measurable")
                continue
            control = expr in CONTROLS
            slow = c > SLOWER_FACTOR * s and c - s >= MIN_GAP_NS
            mark = "  <- control" if control else ("  <- SLOWER" if slow else "")
            print(f"{where:6s} {expr[:44]:44s} {s:8.0f} {c:9.0f}{mark}")
            if slow and not control:
                failures.append(f"{where} {expr}: {c:.0f} ns vs stock {s:.0f} ns")
            if slow and control:
                failures.append(f"{where} control {expr} differs ({c:.0f} vs {s:.0f} ns): "
                                f"the two browsers are not comparable here -- check is vacuous")

    print()
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print(f"PASS: no spoofed getter costs over {SLOWER_FACTOR}x stock Firefox from script.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
