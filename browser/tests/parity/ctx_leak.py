#!/usr/bin/env python3
"""Cross-context leaks inside one browser: fonts (#149, #83), voices, timezone.

Context B's font list allows PROBE and its timezone is Asia/Tokyo; it renders
first, so any process-wide cache or flag it fills is warm. Context A's list
refuses PROBE and its timezone is America/New_York; A then opens pages on
several origins (so several content processes). Every A page must refuse PROBE
and report New York, and all A pages must report the same voice count.

  ctx_leak.py <camoufox-dir>
"""
import http.server
import functools
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

PROBE = "Georgia"
SAMPLE = "mmmmmmmmmmlliWWQ@#"
MEASURE = """async (probe) => {
  const s = %r;
  const c = document.createElement('canvas').getContext('2d');
  const w = (f) => { c.font = '72px ' + f; return c.measureText(s).width; };
  const cands = ['sans-serif', 'monospace', 'serif'];
  let pair = null;
  for (const a of cands) for (const b of cands) if (!pair && a !== b && w(a) !== w(b)) pair = [a, b];
  let vs = speechSynthesis.getVoices();
  for (let i = 0; i < 20 && !vs.length; i++) { await new Promise(r => setTimeout(r, 100)); vs = speechSynthesis.getVoices(); }
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  if (!pair) return { valid: false, voices: vs.length, tz };
  const [a, b] = pair;
  const pa = w('"' + probe + '", ' + a), pb = w('"' + probe + '", ' + b);
  return { valid: true, rendered: pa === pb, refused: pa === w(a) && pb === w(b), voices: vs.length, tz };
}""" % SAMPLE


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    from camoufox.sync_api import Camoufox, NewContext  # noqa: F401
    from camoufox.fingerprints import generate_context_fingerprint

    site = tempfile.mkdtemp()
    Path(site, "p.html").write_text("<!doctype html><meta charset=utf-8><body>x</body>")
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", 0), functools.partial(Quiet, directory=site))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    ext = os.environ.get("EXT", "127.0.0.1")

    base = generate_context_fingerprint(os="windows")
    fonts = sorted(set(base["config"].get("fonts", [])) - {PROBE})
    fp_a = generate_context_fingerprint(os="windows", timezone="America/New_York", config_overrides={"fonts": fonts})
    fp_b = generate_context_fingerprint(os="windows", timezone="Asia/Tokyo", config_overrides={"fonts": fonts + [PROBE]})

    out = {"ok": True}
    exe = os.path.join(sys.argv[1], "camoufox-bin")
    with Camoufox(os="windows", fonts=fonts + [PROBE], headless=False, executable_path=exe) as browser:
        ctx_b = browser.new_context(**fp_b["context_options"])
        ctx_b.add_init_script(fp_b["init_script"])
        pb = ctx_b.new_page()
        pb.goto(f"http://127.0.0.1:{port}/p.html")
        out["control"] = pb.evaluate(MEASURE, PROBE)

        ctx_a = browser.new_context(**fp_a["context_options"])
        ctx_a.add_init_script(fp_a["init_script"])
        rows = []
        for host in ("127.0.0.1", "localhost", ext, "127.0.0.1", "localhost", ext):
            page = ctx_a.new_page()
            page.goto(f"http://{host}:{port}/p.html")
            rows.append({"host": host, **page.evaluate(MEASURE, PROBE)})
        out["a"] = rows

    c = out["control"]
    out["control_ok"] = bool(c.get("valid") and c.get("rendered") and c.get("tz") == "Asia/Tokyo")
    out["font_leaks"] = [r["host"] for r in rows if not r.get("refused")]
    out["tz_leaks"] = [r["tz"] for r in rows if r.get("tz") != "America/New_York"]
    out["voice_counts"] = sorted({r["voices"] for r in rows})
    out["ok"] = out["control_ok"] and not out["font_leaks"] and not out["tz_leaks"] and len(out["voice_counts"]) == 1
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
