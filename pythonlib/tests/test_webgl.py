"""WebGL identities: fpgen's recorded Firefox devices first, webgl_data.db behind them."""

import dataclasses
import json
from pathlib import Path

import pytest
from test_identity_salt import host, launch

from camoufox import coherence, utils
from camoufox import fingerprints as fp
from camoufox import webgl
from camoufox.fingerprints import gpu_screen_is_plausible, is_software_renderer
from camoufox.webgl import sample_webgl_for_screen, webgl_for_gpu
from camoufox.webgl_db import database_gpus, sample_webgl

SEEDS = range(300)
OSES = ("win", "mac", "lin")

_GTX_980_LINUX = ("NVIDIA Corporation", "NVIDIA GeForce GTX 980, or similar")
_BASIC_RENDER_DRIVER = (
    "Google Inc. (Microsoft)",
    "ANGLE (Microsoft, Microsoft Basic Render Driver Direct3D11 vs_5_0 ps_5_0), or similar",
)
_UNKNOWN_GPU = ("Google Inc. (Acme)", "ANGLE (Acme, Acme GPU 9000 Direct3D11 vs_5_0 ps_5_0), or similar")
_NVIDIA_WIN = ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 980 Direct3D11 vs_5_0 ps_5_0), or similar")

# Limits WebGL1 and WebGL2 read from the same device: MAX_TEXTURE_SIZE,
# MAX_VIEWPORT_DIMS, MAX_RENDERBUFFER_SIZE, MAX_CUBE_MAP_TEXTURE_SIZE,
# MAX_VERTEX_ATTRIBS, MAX_TEXTURE_IMAGE_UNITS, MAX_VERTEX_TEXTURE_IMAGE_UNITS,
# MAX_COMBINED_TEXTURE_IMAGE_UNITS and the three uniform/varying vector limits.
_SHARED_LIMITS = ("3379", "3386", "34024", "34076", "34921", "34930", "35660", "35661", "36347", "36348", "36349")


def _as_json(value):
    # JSON has one number type: 2**64 stored as an int and as a float is the
    # same value to the browser's parser.
    return json.loads(json.dumps(value), parse_int=float)


def test_converter_reproduces_the_recorded_device():
    """The fixture is what webgl_data.db gives launch_options for this GPU.
    fpgen records the same device, so everything the browser reads must come
    out identical: parameters are compared where the row has a value, less the
    UNMASKED_* strings, which the browser takes from webGl:vendor/renderer
    rather than the table."""
    old = json.loads((Path(__file__).parent / "data" / "webgl-gtx980-linux.json").read_text())
    new = webgl_for_gpu("lin", *_GTX_980_LINUX, seed=0)

    assert new.keys() == old.keys()
    for key in old:
        if key.endswith(":parameters"):
            recorded = {
                pname: value
                for pname, value in old[key].items()
                if value is not None and pname not in ("37445", "37446")
            }
            assert _as_json({pname: new[key].get(pname) for pname in recorded}) == _as_json(recorded), key
        else:
            assert new[key] == old[key], key


def test_same_seed_same_device():
    for target_os in OSES:
        for seed in (0, 1, 12345):
            assert sample_webgl_for_screen(target_os, 1920, 1080, seed) == sample_webgl_for_screen(
                target_os, 1920, 1080, seed
            )
    gpu = ("AMD", "Radeon R9 200 Series, or similar")
    assert webgl_for_gpu("lin", *gpu, seed=7) == webgl_for_gpu("lin", *gpu, seed=7)


def test_seed_chooses_among_a_gpus_recorded_devices():
    # fpgen records several Linux R9 200 devices; one seed must not pin them all.
    drawn = {json.dumps(webgl_for_gpu("lin", "AMD", "Radeon R9 200 Series, or similar", seed=s)) for s in range(40)}
    assert len(drawn) > 1


@pytest.mark.parametrize("target_os", OSES)
def test_synthetic_draw_is_a_hardware_gpu_the_os_reports(target_os):
    renderers = {sample_webgl_for_screen(target_os, 1920, 1080, s)["webGl:renderer"] for s in SEEDS}
    for renderer in renderers:
        assert not is_software_renderer(renderer), renderer
        assert renderer != "Mozilla"
        assert coherence.gpu_fits_os(renderer, target_os), renderer
    # A single GPU per OS is its own tell.
    assert len(renderers) >= 2


@pytest.mark.parametrize("target_os", OSES)
def test_netbook_screen_never_draws_a_discrete_gpu(target_os):
    for seed in SEEDS:
        renderer = sample_webgl_for_screen(target_os, 1024, 600, seed)["webGl:renderer"]
        assert gpu_screen_is_plausible(renderer, 1024, 600), renderer


def test_no_coherent_gpu_raises(monkeypatch):
    # A pool with nothing that fits is a data defect; substituting a GPU the
    # filters rejected would present exactly what they exist to prevent.
    only_software = tuple(r for r in webgl._trace("gpu", "lin") if is_software_renderer(r.value["renderer"]))
    assert only_software
    monkeypatch.setattr(webgl, "_trace", lambda *a, **kw: only_software)
    with pytest.raises(ValueError, match="No recorded lin GPU"):
        sample_webgl_for_screen("lin", 1920, 1080, seed=0)


@pytest.mark.parametrize("target_os", OSES)
def test_webgl2_comes_from_the_same_device_as_webgl1(target_os):
    # webgl2 is pinned to the drawn webgl; drawn on the GPU alone, a Linux
    # Intel identity paired MAX_TEXTURE_SIZE 8192 with 16384.
    for seed in SEEDS:
        config = sample_webgl_for_screen(target_os, 1920, 1080, seed)
        for pname in _SHARED_LIMITS:
            assert config["webGl:parameters"][pname] == config["webGl2:parameters"][pname], (seed, pname)


def test_gpu_is_pinned_by_vendor_and_renderer():
    # "Mesa" and "AMD" both report this renderer on Linux. A dict condition on
    # fpgen matches the renderer alone and mixed their devices.
    for seed in range(40):
        assert webgl_for_gpu("lin", "Mesa", "Radeon HD 3200 Graphics, or similar", seed)["webGl:vendor"] == "Mesa"


def test_device_without_webgl2():
    config = webgl_for_gpu("win", *_BASIC_RENDER_DRIVER, seed=0)
    assert config["webGl2Enabled"] is False
    assert not any(key.startswith("webGl2:") for key in config)

    with host():
        options = utils.launch_options(
            os="windows", webgl_config=_BASIC_RENDER_DRIVER, headless=True, i_know_what_im_doing=True
        )
    assert options["firefox_user_prefs"]["webgl.enable-webgl2"] is False


def test_unknown_webgl_config_raises():
    # webgl_data.db has this GPU for macOS only.
    with pytest.raises(ValueError, match="not valid for Win"):
        launch(os="windows", webgl_config=("Apple", "Apple M1, or similar"))


def test_preset_keeps_its_own_gpu():
    preset = fp.load_presets("152")["presets"]["linux"][0]
    gpu = (preset["webgl"]["unmaskedVendor"], preset["webgl"]["unmaskedRenderer"])
    config = launch(os="linux", fingerprint_preset=preset)
    assert (config["webGl:vendor"], config["webGl:renderer"]) == gpu
    pinned = (webgl._pin("gpu", {"vendor": gpu[0], "renderer": gpu[1]}),)
    recorded = [webgl.to_config(r.value, [], "lin")["webGl:parameters"] for r in webgl._trace("webgl", "lin", pinned)]
    assert config["webGl:parameters"] in recorded


def test_preset_gpu_neither_source_has_raises():
    preset = fp.load_presets("152")["presets"]["windows"][0]
    preset = {**preset, "webgl": {"unmaskedVendor": _UNKNOWN_GPU[0], "unmaskedRenderer": _UNKNOWN_GPU[1]}}
    with pytest.raises(ValueError, match="Acme GPU 9000"):
        launch(os="windows", fingerprint_preset=preset)


# -- webgl_data.db behind fpgen -----------------------------------------------


def _database_only(target_os):
    only = sorted(database_gpus(target_os) - webgl.firefox_gpus(target_os))
    assert only, f"every {target_os} database GPU is also in fpgen; pick another fixture"
    return only


@pytest.mark.parametrize("target_os", OSES)
def test_synthetic_launch_draws_from_fpgen(target_os):
    recorded = webgl.firefox_gpus(target_os)
    for seed in range(50):
        config = fp.sample_webgl_for_screen(target_os, 1920, 1080, seed=seed)
        assert (config["webGl:vendor"], config["webGl:renderer"]) in recorded


def test_webgl_config_pair_only_the_database_has_still_resolves():
    """Every pair that worked before fpgen still works: the Direct3D 10-level
    "vs_4_x" rows, among others, are devices fpgen has not recorded."""
    for gpu in _database_only("win"):
        config = launch(os="windows", webgl_config=gpu)
        assert (config["webGl:vendor"], config["webGl:renderer"]) == gpu
        assert config["webGl:parameters"] == sample_webgl("win", *gpu)["webGl:parameters"]


def test_webgl_config_pair_neither_source_has_raises():
    assert _UNKNOWN_GPU not in fp.webgl_gpus("windows")
    with pytest.raises(ValueError, match="No WebGL data"):
        launch(os="windows", webgl_config=_UNKNOWN_GPU)


def test_fpgen_that_cannot_answer_falls_back_to_the_database(monkeypatch):
    # fpgen's model-4/2025 has WebGL records without vendor/renderer; an
    # FPGEN_MODEL_URL pointing at it must degrade, not fail every launch.
    def broken(*args, **kwargs):
        raise KeyError("vendor")

    monkeypatch.setattr(webgl, "_trace", broken)
    with pytest.warns(RuntimeWarning, match="falling back to webgl_data.db"):
        config = fp.sample_webgl_for_screen("win", 1920, 1080, seed=3)
    assert (config["webGl:vendor"], config["webGl:renderer"]) in database_gpus("win")

    with pytest.warns(RuntimeWarning, match="falling back to webgl_data.db"):
        config = fp.webgl_for_gpu("win", *_NVIDIA_WIN, seed=3)
    assert config["webGl:parameters"] == sample_webgl("win", *_NVIDIA_WIN)["webGl:parameters"]


def test_model_whose_webgl_records_lack_vendor_falls_back_to_the_database(monkeypatch):
    # model-4/2025's shape, which fpgen fetches by itself when `camoufox fetch`
    # has not installed the pinned model (CI's patch-guard job, 2026-09-27):
    # its GPU list answers, then every webgl record lacks vendor and renderer.
    real_trace = webgl._trace

    def model_4(target, *args, **kwargs):
        results = real_trace(target, *args, **kwargs)
        if target == "gpu":
            return results
        return tuple(
            dataclasses.replace(r, value={k: v for k, v in r.value.items() if k not in ("vendor", "renderer")})
            if isinstance(r.value, dict) else r
            for r in results
        )

    monkeypatch.setattr(webgl, "_trace", model_4)
    assert _NVIDIA_WIN in webgl.firefox_gpus("win")
    with pytest.warns(RuntimeWarning, match="falling back to webgl_data.db"):
        config = fp.webgl_for_gpu("win", *_NVIDIA_WIN, seed=3)
    assert config["webGl:parameters"] == sample_webgl("win", *_NVIDIA_WIN)["webGl:parameters"]
    with pytest.warns(RuntimeWarning, match="falling back to webgl_data.db"):
        config = fp.sample_webgl_for_screen("win", 1920, 1080, seed=3)
    assert (config["webGl:vendor"], config["webGl:renderer"]) in database_gpus("win")


# -- extensions ---------------------------------------------------------------


def _extensions(target_os, key):
    return [
        set(sample_webgl_for_screen(target_os, 1920, 1080, s).get(key) or ()) for s in range(100)
    ]


def test_windows_keeps_ovr_multiview2_on_webgl2():
    assert any("OVR_multiview2" in exts for exts in _extensions("win", "webGl2:supportedExtensions"))


def test_linux_filters_ovr_multiview2():
    # fpgen records it on ~20% of Linux WebGL2 devices.
    assert not any("OVR_multiview2" in exts for exts in _extensions("lin", "webGl2:supportedExtensions"))


def test_draft_extensions_filtered_on_every_os():
    recorded = {
        "vendor": "v",
        "renderer": "r",
        "contextAttributes": {},
        "params": {},
        "shaderPrecisionFormats": [],
        "supportedExtensions": ["ANGLE_instanced_arrays", "WEBGL_multi_draw", "WEBGL_compressed_texture_etc1"],
    }
    webgl2 = {**recorded, "supportedExtensions": ["EXT_texture_norm16", "WEBGL_clip_cull_distance", "OVR_multiview2"]}
    for target_os in OSES:
        config = webgl.to_config(recorded, webgl2, target_os)
        assert config["webGl:supportedExtensions"] == ["ANGLE_instanced_arrays"]
        assert config["webGl2:supportedExtensions"] == (["OVR_multiview2"] if target_os == "win" else [])
