"""
Verify worker reads of per-context values (anti-font-fingerprinting.patch,
RoverfoxStorageManager; lang315/camoufox#145).

  values  a worker in a macOS context of a Windows launch reports the context's
          navigator.platform, hardwareConcurrency and timezone, like its window
  race    workers reading navigator in a tight loop while other contexts are
          created (each one's values reach every process as new prefs) do not
          crash the content process

Workers used to fall through to libpref, whose table is main-thread only and
looked up without a lock in a release build. On cg.4 before the fix the race
case crashed the content process within 8 s in 8 of 8 runs; the controls held
for 60 s: no workers (117-133 contexts), workers reading navigator.onLine
(~2e9 reads), and config-reading workers with no contexts created.

    python tests/patches/worker-config-reads.py
"""

import functools
import http.server
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import resolve_binary  # noqa: E402

RACE_SECONDS = 30
WORKERS = 4
# One content process, so every context's prefs land in the workers' process.
ONE_PROCESS = {"dom.ipc.processCount": 1, "dom.ipc.processCount.webIsolated": 1}

VALUES = """async () => {
  const read = () => ({platform: navigator.platform, cores: navigator.hardwareConcurrency,
                       tz: Intl.DateTimeFormat().resolvedOptions().timeZone});
  const code = 'postMessage((' + read.toString() + ')())';
  const w = new Worker(URL.createObjectURL(new Blob([code])));
  const worker = await new Promise(r => { w.onmessage = e => r(e.data); });
  return {window: read(), worker};
}"""

SPIN = """(n) => {
  window.__reads = 0;
  const code = 'for(;;){ for(let i=0;i<2000;i++){ navigator.hardwareConcurrency; navigator.platform;'
             + ' navigator.userAgent; navigator.language; } postMessage(0); }';
  for (let i = 0; i < n; i++) {
    const w = new Worker(URL.createObjectURL(new Blob([code])));
    w.onmessage = () => { window.__reads += 2000; };
  }
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def log_error(self, *a):
        pass


def check_values(binary, url, failures):
    from camoufox.sync_api import Camoufox
    from camoufox.fingerprints import generate_context_fingerprint

    fp = generate_context_fingerprint(os="macos", timezone="Asia/Tokyo")
    with Camoufox(os="windows", headless=True, executable_path=str(binary),
                  i_know_what_im_doing=True) as browser:
        ctx = browser.new_context(**fp["context_options"])
        ctx.add_init_script(fp["init_script"])
        page = ctx.new_page()
        page.goto(url)
        out = page.evaluate(VALUES)
    print(f"values: {out}")
    if out["window"]["platform"] != "MacIntel" or out["window"]["tz"] != "Asia/Tokyo":
        failures.append(f"values: the context's own values did not apply to its window -- check is vacuous: {out}")
    elif out["worker"] != out["window"]:
        failures.append(f"values: worker {out['worker']} differs from window {out['window']}")


def check_race(binary, url, failures):
    from camoufox.sync_api import Camoufox
    from camoufox.fingerprints import generate_context_fingerprint

    fps = [generate_context_fingerprint(os=o) for o in ("macos", "linux", "windows")]
    crashed = []
    created = 0
    reads = 0
    with Camoufox(os="windows", headless=True, executable_path=str(binary),
                  firefox_user_prefs=ONE_PROCESS, i_know_what_im_doing=True) as browser:
        spin = browser.new_page()
        spin.on("crash", lambda _: crashed.append("spinning page"))
        spin.goto(url)
        spin.evaluate(SPIN, WORKERS)
        deadline = time.time() + RACE_SECONDS
        try:
            while time.time() < deadline and not crashed:
                fp = fps[created % len(fps)]
                ctx = browser.new_context(**fp["context_options"])
                ctx.add_init_script(fp["init_script"])
                page = ctx.new_page()
                page.on("crash", lambda _: crashed.append("new context's page"))
                page.goto(url, timeout=15000)
                ctx.close()
                created += 1
            if not crashed:
                reads = spin.evaluate("window.__reads")
        except Exception as exc:  # a crash mid-call surfaces as a closed target
            crashed.append(f"{type(exc).__name__}: {str(exc).splitlines()[0]}")
    print(f"race: {created} contexts in {RACE_SECONDS} s, {reads} worker reads, crashed: {crashed or 'no'}")
    if crashed:
        failures.append(f"race: content process crashed after {created} contexts ({crashed[0]})")
    elif created < 10 or reads == 0:
        failures.append(f"race: {created} contexts / {reads} worker reads -- check is vacuous")


def main() -> int:
    binary = resolve_binary()
    site = tempfile.mkdtemp()
    Path(site, "p.html").write_text("<!doctype html><meta charset=utf-8><body>x</body>")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=site))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/p.html"

    failures = []
    try:
        check_values(binary, url, failures)
        check_race(binary, url, failures)
    finally:
        srv.shutdown()

    print()
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("PASS: workers read their context's values and survive concurrent context creation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
