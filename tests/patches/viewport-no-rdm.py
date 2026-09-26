r"""
Verify an emulated viewport does not put the page in Responsive Design Mode.

Upstream Playwright's Juggler set `browsingContext.inRDMPane = true` whenever a
context or page had a viewport -- the default for new_context(). In RDM, Gecko
draws content with devtools' Android theme and forces overlay scrollbars
(nsPresContext::EnsureTheme / UseOverlayScrollbars), and stock getters take RDM
early returns (nsScreen::GetRect, Navigator::MaxTouchPoints). A page reads both:

  - scrollbar width: a Windows 10 identity (classic scrollbars, pinned by the
    launcher) measured 12 px on a launch-level page and 0 px in any context
    with a viewport -- Windows 10 fonts with overlay scrollbars, a pair no
    real machine produces;
  - getter cost: screen.availWidth, outerWidth and maxTouchPoints ran at
    0.2-0.6x stock Firefox's cost in a viewport context, 1.0-1.3x elsewhere.

The guard pins classic scrollbars, measures the scrollbar gutter on a
launch-level page (the control: it must be non-zero, or the check is vacuous),
then in a context with a viewport (which must really be applied), and requires
the two to match.

    python tests/patches/viewport-no-rdm.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import resolve_binary  # noqa: E402

VIEWPORT = {"width": 1000, "height": 600}

PAGE = """<!doctype html><style>body{margin:0;height:3000px}
#b{width:200px;height:100px;overflow:scroll}</style><div id=b></div>"""

MEASURE = """() => {
  const b = document.getElementById('b');
  return {
    page: innerWidth - document.documentElement.clientWidth,
    box: b.offsetWidth - b.clientWidth,
    viewport: [innerWidth, innerHeight],
  };
}"""


def main() -> int:
    from camoufox.sync_api import Camoufox

    binary = resolve_binary()
    with Camoufox(os="windows", headless=True, executable_path=str(binary),
                  firefox_user_prefs={"ui.useOverlayScrollbars": 0},
                  i_know_what_im_doing=True) as browser:
        page = browser.new_page()
        page.set_content(PAGE)
        control = page.evaluate(MEASURE)

        context = browser.new_context(viewport=VIEWPORT)
        page = context.new_page()
        page.set_content(PAGE)
        emulated = page.evaluate(MEASURE)

    print(f"  launch page:      {control}")
    print(f"  viewport context: {emulated}")

    failures = []
    if control["page"] <= 0 or control["box"] <= 0:
        failures.append(f"launch page shows no classic scrollbar ({control}) -- check is vacuous")
    if emulated["viewport"] != [VIEWPORT["width"], VIEWPORT["height"]]:
        failures.append(f"viewport {VIEWPORT} not applied: page reports {emulated['viewport']}")
    if (emulated["page"], emulated["box"]) != (control["page"], control["box"]):
        failures.append(
            f"scrollbar width differs with a viewport: {emulated['page']}/{emulated['box']} px "
            f"vs {control['page']}/{control['box']} px without (Responsive Design Mode theme)")

    for f in failures:
        print(f"FAIL: {f}")
    if failures:
        return 1
    print("PASS: an emulated viewport keeps the identity's scrollbars (no Responsive Design Mode).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
