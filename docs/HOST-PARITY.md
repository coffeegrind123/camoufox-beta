# Host parity: a Windows identity on a Linux host

The Linux build is meant to pass for Firefox on the OS it claims. Measured on
2026-09-24 against stock Firefox 152.0.4 on Windows 10 and on Linux, with
`tests/parity/`, many answers still came from the host. This lists each one,
what a page reads, and how it is closed.

| Tell (before) | What the page read | Fix | Where |
|---|---|---|---|
| CSS animations finished instantly | a 2 s transition sampled at 0.5 s: 10px, stock ~60px | `disableInstantAnimations` on by default | launcher |
| Codec matrix of a Linux container | `canPlayType` "" for H.264/HEVC; stock Windows "probably" | `media:spoof_codecs` for Windows/macOS identities; matches Windows on 58 strings | launcher |
| `decodingInfo()` asked the host | H.264, HEVC, AAC unsupported; VP9 not power-efficient | with codec spoofing, supported + smooth, power-efficient per `media:hwCodecs` (Windows: H.264, HEVC, VP9) or small frames | `media-codec-spoofing.patch` |
| WebGPU off | no `navigator.gpu`, ~390 `GPU*` members missing | `dom.webgpu.enabled` + external textures for Windows identities | launcher |
| WebGPU limits from Vulkan | 14 of 36 limits differ from D3D12 | adapter reports `webGpu:limits`; requests validated against them, clamped to the real adapter for wgpu | `webgpu-limits-spoofing.patch` |
| Glyph advances rounded | text widths whole pixels (953) vs fractional (953.0667) | forced subpixel positioning; widths and `<input>`/`<select>` widths then match exactly | launcher |
| Line boxes from FreeType | Arial 16px 19/19 px vs 17/18; all 26 fonts measured differed | `fonts:metrics: "windows"`: DirectWrite's metrics from the same tables, Arial Black case included | `font-metrics-windows.patch` |
| GTK system colours | Highlight/SelectedItem/AccentColor Adwaita blue, dialog colours | Windows values via `ui.*` prefs | launcher |
| No sound device | AudioContext 44100 Hz, 0 output channels | 48000 Hz, 2 channels | launcher |
| Audio noise | OfflineAudioContext probe unique per identity; stock is 75.83002272993326 on every machine | `audio:seed` 0 by default | launcher |
| WebGL `RENDERER` from the host | "Generic Renderer" next to an ANGLE `UNMASKED_RENDERER` | `RENDERER` answers the spoofed renderer too, as stock derives both from one string | `webgl-spoofing.patch` |
| Display scale | 1536x864 screen at `devicePixelRatio` 1 (36% of Windows draws, 74% of macOS) | render at the drawn scale (`layout.css.devPixelsPerPx`); redraw if it cannot fit the monitor | launcher |
| Geolocation precision | float32 coordinates, accuracy 6e-10 m | coordinates at database precision, IP-scale accuracy | launcher, `geolocation-spoofing.patch` |
| Font list in later processes | a context's 2nd..6th pages rendered a font its list refused | per-process "setter called" flag (lang315/camoufox#149) | `font-list-spoofing.patch`, `speech-voices-spoofing.patch` |

Already at parity in cg.3 and re-checked: API surface (0 missing, 0 extra with the
fixes above), user activation, wasm speed, debuggee stack capture, `pointerType`,
plain-HTTP `Accept-Encoding`, voices, plugins, timer resolution, Math, WebRTC
candidates (mDNS host + spoofed srflx only).

Animations, audio noise and display scale apply to every identity; the rest only
when the claimed OS differs from the host. Every default yields to a value the
caller sets.
