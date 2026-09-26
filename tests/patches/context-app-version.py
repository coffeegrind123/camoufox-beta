r"""
Verify a NewContext() identity's navigator agrees with itself and the engine.

Two mismatches a page reads in one line each, both measured on 152.0.4:

  - navigator.appVersion came only from the launch config, so a macOS
    context in a Windows launch reported "5.0 (Windows)" beside a Macintosh
    user agent, in the page and in its workers. NavigatorManager::GetAppVersion
    derives it from the context's user agent, as Firefox does.
  - NewContext() without ff_version sent its corpus's version: every page
    said `rv:135.0 ... Firefox/135.0` on a 152 engine, where launch-level
    pages said 152 (the UA/engine mismatch of daijro/camoufox#744).

The launch identity is Windows; contexts claim macOS and Linux, so the
per-context answer cannot be the launch one by accident.

    python tests/patches/context-app-version.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import resolve_binary  # noqa: E402

EXPECTED = {"macos": "5.0 (Macintosh)", "linux": "5.0 (X11)", "windows": "5.0 (Windows)"}

READ = """async () => {
  const src = 'postMessage([navigator.appVersion, navigator.userAgent])';
  const w = new Worker(URL.createObjectURL(new Blob([src])));
  const worker = await new Promise(r => { w.onmessage = e => r(e.data); });
  return {window: [navigator.appVersion, navigator.userAgent], worker};
}"""


def main() -> int:
    from camoufox.sync_api import Camoufox, NewContext

    binary = resolve_binary()
    failures = []
    with Camoufox(os="windows", headless=True, executable_path=str(binary),
                  i_know_what_im_doing=True) as browser:
        major = browser.version.split(".", 1)[0]
        launch_page = browser.new_page()
        launch_page.goto("about:blank")
        print(f"  launch: {launch_page.evaluate('navigator.appVersion')!r} (engine {major})")

        for os_name in ("macos", "linux", "windows"):
            context = NewContext(browser, os=os_name)
            page = context.new_page()
            page.set_content("<p>x</p>")
            seen = page.evaluate(READ)
            context.close()
            print(f"  {os_name:8s} window={seen['window']} worker={seen['worker']}")

            for where in ("window", "worker"):
                app_version, user_agent = seen[where]
                if app_version != EXPECTED[os_name]:
                    failures.append(f"{os_name} {where}: appVersion {app_version!r}, "
                                    f"expected {EXPECTED[os_name]!r} for UA {user_agent!r}")
                versions = set(re.findall(r"(?:rv:|Firefox/)(\d+)\.0", user_agent))
                if versions != {major}:
                    failures.append(f"{os_name} {where}: UA claims {sorted(versions)}, engine is {major}")

    for f in failures:
        print(f"FAIL: {f}")
    if failures:
        return 1
    print("PASS: context appVersion follows the context's user agent, which claims the engine's version.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
