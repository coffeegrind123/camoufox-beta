r"""
Math.sin/cos/tan/pow give Windows' results, to the last bit.

The last bit of these differs between math libraries, so one call tells a page
which one it is talking to -- and a Linux build claiming Windows answered with
glibc's (or fdlibm's). windows-crt-math.patch computes them as the Windows CRT
does (additions/js/src/builtin/UcrtMath*.c); the launcher turns it on for a
Windows identity (javascript.options.use_ucrt_math).

The reference, tests/patches/assets/windows-crt-math.json, is what stock Firefox
on Windows returned for the same inputs (tests/ucrt-math/record_firefox.py), so
this checks the whole path a page sees: the interpreter, the JITs (the probe
runs hot), constant folding, and SpiderMonkey's own exponent fast paths around
pow. tests/ucrt-math/check.py covers the C alone, against ucrtbase.dll, on a
much larger set.

A control run with the pref off must differ, or the reference would not be
telling the two apart.

    python tests/patches/windows-crt-math.py
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import resolve_binary  # noqa: E402

HERE = Path(__file__).resolve().parent
REFERENCE = json.loads((HERE / "assets" / "windows-crt-math.json").read_text())
PROBE = (HERE.parent / "ucrt-math" / "probe.js").read_text()
TIMEOUT_MS = 120_000


async def run_probe(binary, prefs):
    from camoufox.async_api import AsyncCamoufox

    async with AsyncCamoufox(headless=True, executable_path=str(binary), os="windows",
                             firefox_user_prefs=prefs, i_know_what_im_doing=True) as browser:
        page = await browser.new_page()
        page.set_default_timeout(TIMEOUT_MS)
        return await page.evaluate(PROBE, REFERENCE["input"])


def mismatches(got):
    """{name: (differing, total)} against the Windows reference."""
    want = REFERENCE["expected"]
    out = {}
    for phase in ("cold", "hot"):
        for name, values in want["results"].items():
            bad = sum(1 for a, b in zip(got[phase][name], values) if a != b)
            out[f"{phase} {name}"] = (bad, len(values))
    bad = sum(1 for a, b in zip(got["constants"], want["constants"]) if a != b)
    out["constant-folded"] = (bad, len(want["constants"]))
    return out


def main() -> int:
    binary = resolve_binary()
    windows = mismatches(asyncio.run(run_probe(binary, {})))
    control = mismatches(asyncio.run(run_probe(binary, {"javascript.options.use_ucrt_math": False})))

    print(f"reference: {REFERENCE['firefox']} on Windows")
    failures = []
    for key, (bad, total) in windows.items():
        print(f"  {key}: {total - bad}/{total} match")
        if bad:
            failures.append(f"{key}: {bad} of {total} results differ from Windows")

    control_bad = sum(control[f"cold {name}"][0] for name in ("sin", "cos", "tan"))
    print(f"  control (use_ucrt_math off): {control_bad} sin/cos/tan results differ, as they must")
    if not control_bad:
        failures.append(
            "with javascript.options.use_ucrt_math off the results still match Windows: "
            "the reference no longer tells the host libm from the CRT"
        )

    for failure in failures:
        print("FAIL:", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
