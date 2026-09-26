"""
Verify uBlock Origin starts once and does not hold navigations while it loads
(browser-init.patch, settings/distribution/policies.json).

browser-init.patch installs the `addons` config entries (uBlock Origin by
default) as temporary addons from gBrowserInit, which runs for every browser
window -- and Juggler opens a window for every page of every new context. Each
install of an already-installed temporary addon restarts the extension. A
navigation that uBO's webRequest listener had suspended when the restart hit
was never resumed: its channel sat in "Waiting until resume" and page.goto
timed out. Measured on cg.3 and cg.4: uBO's background page loaded once per
context, and a run of contexts hung within 2-30 of them (every run, both
builds, fresh addon cache).

Every launch uses a fresh profile, so every launch is uBO's first run: it
compiles its filter lists from scratch, and by default it holds every request
until that is done (suspendUntilListsAreLoaded -- its storage.js suspends for
the whole list load even on a first install). Stock Firefox pays that once;
camoufox paid it on every launch: early navigations took 1-2.6 s longer when
idle, up to 18 s with two workers busy on 4 cores, and past a 45 s goto timeout
on the 4-vCPU CI runner. policies.json sets the setting to false through uBO's
managed storage; with it the same load topped out at 2.3 s. Requests in the
first seconds after launch are unfiltered, as they always are on Chromium.

    policy     policies.json sets suspendUntilListsAreLoaded false for uBO
    contexts   create CONTEXTS contexts, one page each, and navigate it
    once       uBO's background page loaded exactly once (MOZ_LOG
               DocumentChannel records every document load in the parent)
    no hang    every navigation completed

    python tests/patches/ubo-startup.py
"""

import functools
import http.server
import os
import re
import shutil
import sys
import tempfile
import json
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import resolve_binary  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
UBO_ID = "uBlock0@raymondhill.net"
CONTEXTS = 12
# A restart-dropped request never finishes; a healthy local load takes well
# under a second even on a loaded runner.
GOTO_TIMEOUT_MS = 20000
BACKGROUND_LOAD = re.compile(r"DocumentChannelParent Init \[this=\w+, uri=moz-extension://[^/]+/background")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


class QuietServer(http.server.ThreadingHTTPServer):
    # A page torn down mid-response breaks the pipe; the default handler's
    # traceback would replace the verdict as the tail of the guard's output.
    def handle_error(self, request, client_address):
        pass


def background_loads(log_dir: Path) -> int:
    # MOZ_LOG_FILE gets a suffix per process; document loads are logged by the
    # parent, but count every file rather than guess which one that is.
    return sum(len(BACKGROUND_LOAD.findall(p.read_text(errors="replace")))
               for p in log_dir.glob("log*"))


def main() -> int:
    from camoufox.sync_api import Camoufox

    binary = resolve_binary()
    site = tempfile.mkdtemp()
    Path(site, "p.html").write_text("<!doctype html><meta charset=utf-8><body>x</body>")
    srv = QuietServer(("127.0.0.1", 0), functools.partial(Quiet, directory=site))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/p.html"

    log_dir = Path(tempfile.mkdtemp())
    env = {**os.environ, "MOZ_LOG": "DocumentChannel:5", "MOZ_LOG_FILE": str(log_dir / "log")}
    created = 0
    hang = None
    try:
        with Camoufox(headless=True, executable_path=str(binary), env=env,
                      i_know_what_im_doing=True) as browser:
            for _ in range(CONTEXTS):
                ctx = browser.new_context()
                page = ctx.new_page()
                try:
                    page.goto(url, timeout=GOTO_TIMEOUT_MS)
                except Exception as exc:
                    hang = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
                    break
                ctx.close()
                created += 1
    finally:
        srv.shutdown()
    loads = background_loads(log_dir)
    shutil.rmtree(log_dir, ignore_errors=True)

    policies = json.loads((REPO_ROOT / "settings/distribution/policies.json").read_text())["policies"]
    advanced = policies.get("3rdparty", {}).get("Extensions", {}).get(UBO_ID, {}).get("advancedSettings", [])
    suspend = dict(advanced).get("suspendUntilListsAreLoaded")

    print(f"policy: suspendUntilListsAreLoaded={suspend!r}")
    print(f"contexts: {created}/{CONTEXTS} navigated, uBO background page loads: {loads}"
          + (f", hang: {hang}" if hang else ""))
    print()
    failures = []
    if suspend != "false":
        failures.append("policies.json no longer sets uBO's suspendUntilListsAreLoaded to \"false\"")
    if loads == 0:
        failures.append("uBO's background page never loaded -- the addon did not start, check is vacuous")
    elif loads > 1:
        failures.append(f"uBO restarted: its background page loaded {loads} times for {created + 1} windows")
    if hang:
        failures.append(f"navigation {created + 1} never completed ({hang})")
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("PASS: uBO installed once, does not hold navigations for its lists; every navigation completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
