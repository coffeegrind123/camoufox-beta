#!/usr/bin/env python3
"""Run the probe page in one browser configuration and wait for its result.

  run.py stock   <firefox-dir>         stock Firefox, plain binary, xdotool click
  run.py raw     <camoufox-dir>        camoufox binary without Playwright/Juggler
  run.py cfx     <camoufox-dir> [json] camoufox through the launcher (Playwright),
                                       json = extra launcher kwargs

Needs DISPLAY (Xvfb) and server.py on 127.0.0.1:PORT writing to OUT.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

PORT = int(os.environ.get("PORT", "8765"))
OUT = os.environ.get("OUT", "/lab/out")
TAG = os.environ.get("TAG")
TIMEOUT = 60
NOCLICK = bool(os.environ.get("NOCLICK"))
EXT = os.environ.get("EXT", "")

PREFS = """
user_pref("browser.aboutwelcome.enabled", false);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.startup.homepage_override.mstone", "ignore");
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);
user_pref("trailhead.firstrun.didSeeAboutWelcome", true);
user_pref("browser.startup.firstrunSkipsHomepage", true);
user_pref("app.update.disabledForTesting", true);
user_pref("app.update.auto", false);
user_pref("app.update.staging.enabled", false);
user_pref("app.update.background.enabled", false);
user_pref("browser.tabs.warnOnClose", false);
user_pref("browser.sessionstore.resume_from_crash", false);
"""


def url(tag):
    return f"http://127.0.0.1:{PORT}/probe.html?tag={tag}" + ("&noclick" if NOCLICK else "") + (f"&ext={EXT}:{PORT}" if EXT else "")


def wait_result(tag, proc=None):
    path = os.path.join(OUT, tag + ".json")
    end = time.time() + TIMEOUT
    while time.time() < end:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return True
        if proc is not None and proc.poll() is not None:
            print(f"browser exited early rc={proc.returncode}", file=sys.stderr)
            return False
        time.sleep(0.5)
    return False


def target_pos(tag):
    """The page reports #target's screen centre via GET /pos (logged by server.py)."""
    path = os.path.join(OUT, tag + ".headers.jsonl")
    for _ in range(60):
        if os.path.exists(path):
            for line in open(path):
                j = json.loads(line)
                if j["path"].startswith("/pos"):
                    q = dict(kv.split("=") for kv in j["path"].split("?", 1)[1].split("&"))
                    return int(q["x"]), int(q["y"])
        time.sleep(0.5)
    return None


def xclick_target(tag):
    """Real X input: move then click on #target."""
    pos = target_pos(tag)
    if not pos:
        print("page never reported #target position", file=sys.stderr)
        return
    time.sleep(2.5)
    x, y = pos
    subprocess.run(["xdotool", "mousemove", str(x - 40), str(y - 20)])
    time.sleep(0.2)
    subprocess.run(["xdotool", "mousemove", str(x), str(y)])
    time.sleep(0.2)
    subprocess.run(["xdotool", "click", "1"])


def plain(binary, tag):
    prof = tempfile.mkdtemp(prefix="prof-")
    with open(os.path.join(prof, "user.js"), "w") as f:
        f.write(PREFS)
    p = subprocess.Popen([binary, "--no-remote", "--profile", prof, "--new-instance", url(tag)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not NOCLICK:
            xclick_target(tag)
        ok = wait_result(tag, p)
    finally:
        p.terminate()
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill()
        shutil.rmtree(prof, ignore_errors=True)
    return ok


def cfx(path, tag, extra):
    from camoufox.sync_api import Camoufox
    kw = dict(headless=False, executable_path=os.path.join(path, "camoufox-bin"))
    kw.update(extra)
    with Camoufox(**kw) as browser:
        page = browser.new_page()
        page.goto(url(tag))
        time.sleep(3.5)
        if not NOCLICK:
            page.mouse.move(260, 240)
            page.mouse.click(300, 260)
        ok = wait_result(tag)
    return ok


def main():
    mode, path = sys.argv[1], sys.argv[2]
    extra = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
    tag = TAG or mode
    for suffix in (".json", ".headers.jsonl"):
        try:
            os.remove(os.path.join(OUT, tag + suffix))
        except FileNotFoundError:
            pass
    if mode == "stock":
        ok = plain(os.path.join(path, "firefox"), tag)
    elif mode == "raw":
        ok = plain(os.path.join(path, "camoufox-bin"), tag)
    elif mode == "cfx":
        ok = cfx(path, tag, extra)
    else:
        sys.exit("unknown mode " + mode)
    print(f"{tag}: {'ok' if ok else 'NO RESULT'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
