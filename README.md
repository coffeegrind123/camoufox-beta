# camoufox-beta

A fork of [Camoufox](https://github.com/daijro/camoufox), the Firefox build
that spoofs device fingerprints in C++. For what Camoufox is, its features and
how to build it, read [upstream's README](https://github.com/daijro/camoufox#readme).

This fork follows upstream `main` (026ec90, Firefox 158.0) and releases its
own builds. Everything it adds is listed below; fixes are offered upstream.

> [!NOTE]
> Under development. Test a release against your own targets before relying on it.

## What this fork adds

### Rendering as the claimed OS

For an identity whose OS is not the host's. Offered upstream in
[#896](https://github.com/daijro/camoufox/pull/896).

- **Per-script font fallback** follows the claimed OS's tables and `font.*`
  defaults, so Thai, emoji, Mongolian and other scripts draw with the faces
  stock Firefox uses there. ([7c8e6a9](https://github.com/coffeegrind123/camoufox-beta/commit/7c8e6a9d8b3312846c26fe8e31984c10a1d3d6c6))
- **DirectWrite line metrics** for a Windows identity (`fonts:metrics`), so
  line boxes match Windows instead of FreeType. ([c8cd204](https://github.com/coffeegrind123/camoufox-beta/commit/c8cd20423c9640bbb381fc33a293c33ccbbddadf), [6023d01](https://github.com/coffeegrind123/camoufox-beta/commit/6023d01bd194ad38e1fae7a3660c0c02d5c200fa))
- **Subpixel glyph positions** for a Windows or macOS identity, so text and
  form-control widths match those OSes. ([806329a](https://github.com/coffeegrind123/camoufox-beta/commit/806329ab64dcf271802b672b57cae1ca7ac34ec6))
- **macOS UCS4 cmaps** are read for a macOS identity, so Geneva, Apple Symbols
  and Heiti render instead of sitting unused in the font list. ([82092da](https://github.com/coffeegrind123/camoufox-beta/commit/82092dac9937b7d87fd62cd64c84a4197f32ee0b))
- **Codecs:** `canPlayType()` and `mediaCapabilities.decodingInfo()` both
  answer as the claimed OS, with Windows' hardware codecs. ([8fa6bd8](https://github.com/coffeegrind123/camoufox-beta/commit/8fa6bd86d751734ce2bd209aab4e01392aa7580e))
- **Windows system colours** (Highlight, AccentColor, dialog) instead of the
  host's GTK theme. ([51dfed2](https://github.com/coffeegrind123/camoufox-beta/commit/51dfed22ff39a1bca9e1ab982b97b8c44292c534))

### Other browser fixes

- **Fontconfig memo keyed by context.** One context's font allow-list no longer
  answers for other contexts in the same content process. Offered upstream in
  [#942](https://github.com/daijro/camoufox/pull/942). ([6950149](https://github.com/coffeegrind123/camoufox-beta/commit/6950149e920820710122e176ab66bd14d66db4c4))
- **Storage puts sync from the main thread**, so a put from a worker cannot
  crash a content process. Upstream dropped it because nothing triggers it
  today. ([b481348](https://github.com/coffeegrind123/camoufox-beta/commit/b481348b58bf4a6b6bcd4f59a7f348fe32720212))
- **EME on for Windows identities.** With EME off, Firefox's "EME has been
  preffed off" error is one only Linux Firefox gives. ([1a43e61](https://github.com/coffeegrind123/camoufox-beta/commit/1a43e61878b66ffa66334ee30c38a846842a0f19))
- **uBlock Origin doesn't hold requests** while it compiles its lists on a
  fresh profile (1–45 s). Requests in the first seconds go unfiltered.
  Upstream keeps the hold. ([41a9903](https://github.com/coffeegrind123/camoufox-beta/commit/41a9903048c011b9fc9aa38aa9786d72d922a94d))

### Kept here after upstream declined

- **`gpu_passthrough=True`.** A Linux container on Windows can render on the
  host's real GPU through WSL's D3D12 driver while claiming Windows Firefox on
  that GPU. The canvas stays uncovered, and WebGPU reports Windows' adapter
  limits. ([aaf96d7](https://github.com/coffeegrind123/camoufox-beta/commit/aaf96d7a94641757d88fff876dcd8b17d13b689a), [f7c27c8](https://github.com/coffeegrind123/camoufox-beta/commit/f7c27c8681e55480b6f3f434b7a2e0e3a535598d))
- **`humanize_engine="mousecrack"`.** A second cursor engine, using
  [mousecrack](https://github.com/puffinsoft/mousecrack)'s trained network.
  Cursory stays the default. ([529a730](https://github.com/coffeegrind123/camoufox-beta/commit/529a730125862d65dd6085e05c398ae9bd2aabb4))
- **First humanized move** starts just inside the page's top edge, not at
  (0, 0). ([33f01dc](https://github.com/coffeegrind123/camoufox-beta/commit/33f01dc5cacc9cc58aa1cf0e41a132a7e001ae9c))
- **Geolocation accuracy.** IP-derived positions are rounded to the database's
  precision and carry a city-scale accuracy in whole metres, instead of
  14 decimals and 6e-10 m. ([bb7bc29](https://github.com/coffeegrind123/camoufox-beta/commit/bb7bc29fd5cf77167cbeffe7fbfbd1d9d0b63b10), [9954eac](https://github.com/coffeegrind123/camoufox-beta/commit/9954eac531391b0ae56917dccab150dfe81fc568))

### Build, releases and defaults

- **Linux x86_64 releases built by this repo's CI**
  ([`build.yml`](.github/workflows/build.yml)), with sha256 digests. No PyPI or
  npm packages are published, and upstream's release train doesn't run. ([b70dc6c](https://github.com/coffeegrind123/camoufox-beta/commit/b70dc6c52c1605ad8bcf7c7770cf99d2235dd8a0))
- **Cross-language LTO and PGO** with a pinned profile, as stock Firefox builds
  ([`ci/pgo.py`](ci/pgo.py)). A release is refused until a profile is pinned.
  Offered upstream in [#886](https://github.com/daijro/camoufox/pull/886). ([3381943](https://github.com/coffeegrind123/camoufox-beta/commit/3381943c57abebf06301bebee4e8f4a230781c44))
- **`canvas_noise` defaults to `False`:** the canvas is never covered.
  `canvas_noise=None` gives upstream's automatic cover. ([38ef536](https://github.com/coffeegrind123/camoufox-beta/commit/38ef536579a3b1284929dfaf544dfb6e124a217e))
- **Stock-parity probe lab**
  ([`browser/tests/parity/`](browser/tests/parity)). It's a manual harness that
  diffs what a page sees in stock Firefox and in Camoufox, and it checks for
  leaks between contexts. ([9a9de49](https://github.com/coffeegrind123/camoufox-beta/commit/9a9de495c1d223b7225ec4ee6eb05b0081b6968b))
- **CI and the TypeScript launcher.** The TypeScript jobs don't gate merges,
  and the package install gate runs on upstream only. The TypeScript launcher
  is kept as upstream has it, but not every Python change is ported to it. ([f9e1994](https://github.com/coffeegrind123/camoufox-beta/commit/f9e1994f29824bb0a58a192867e85fa7ba2cc5da), [6978636](https://github.com/coffeegrind123/camoufox-beta/commit/697863638dbaa4f2c16635f62e6ae0797fbc9a17))

## Installing

Each [release](https://github.com/coffeegrind123/camoufox-beta/releases)
carries a Linux x86_64 browser zip and its sha256. Install the launcher from
the commit the release tag points at, so the two agree about config
properties:

```bash
pip install --force-reinstall "camoufox[geoip] @ git+https://github.com/coffeegrind123/camoufox-beta.git@<release commit>#subdirectory=python"
```

Every commit reports the same package version, hence `--force-reinstall`.
Unpack the zip, check its sha256 against the release's `digest`, and point the
launcher at it:

```python
from camoufox.sync_api import Camoufox

with Camoufox(executable_path="/opt/camoufox/camoufox-bin") as browser:
    page = browser.new_page()
    page.goto("https://example.com")
```

The launcher installs fpgen's model itself, pinned by URL and sha256. To
install it ahead of time, for example while building an image:

```bash
python -c "from camoufox.fpgen_model import ensure_fpgen_model; ensure_fpgen_model()"
```

`camoufox fetch` downloads upstream's browsers, not this fork's.

## Licensing

| Part | Licence |
|---|---|
| The browser (`browser/`) | [MPL-2.0](LICENSE) |
| Vendored Cursory trajectories | LGPLv3-or-later ([`NOTICE`](browser/additions/juggler/input/cursory/NOTICE)) |
| mousecrack's model and its port | MIT (`browser/additions/juggler/input/mousecrack/LICENSE`) |
| Python and TypeScript packages | MIT ([`python/LICENSE`](python/LICENSE), [`typescript/LICENSE`](typescript/LICENSE)) |
