"""Answers that come from the host must follow the claimed OS instead.

Every expected value here was measured on stock Firefox 152.0.4 on Windows 10
against this build on a Linux host claiming Windows (2026-09-24): subpixel glyph
positioning, the Windows system colours, Web Audio's output device, WebGPU, the
codec matrix, and real-time CSS animations.
"""

import pytest

from camoufox import utils
from camoufox.geolocation import IP_ACCURACY_RANGE_M, ip_accuracy

from test_launch_environment import isolated_launch_dependencies  # noqa: F401

WIN_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0"
MAC_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:152.0) Gecko/20100101 Firefox/152.0"
LIN_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:152.0) Gecko/20100101 Firefox/152.0"


@pytest.fixture
def launch(monkeypatch, isolated_launch_dependencies):  # noqa: F811
    """launch_options on a Linux host; returns (config, prefs)."""
    monkeypatch.setattr(utils, "_host_os_key", lambda: "lin")
    seen = {}

    def capture(config, *args, **kwargs):
        seen["config"] = dict(config)
        return {}

    monkeypatch.setattr(utils, "get_env_vars", capture)

    def run(ua, **kwargs):
        config = {"navigator.userAgent": ua, **kwargs.pop("config", {})}
        prefs = utils.launch_options(config=config, i_know_what_im_doing=True, **kwargs)["firefox_user_prefs"]
        return seen["config"], prefs

    return run


def test_windows_identity_gets_windows_look_and_feel(launch):
    config, prefs = launch(WIN_UA)
    assert prefs["gfx.text.subpixel-position.force-enabled"] is True
    for pref, value in utils.WINDOWS_UI_COLORS.items():
        assert prefs[pref] == value
    assert prefs["dom.webgpu.enabled"] is True
    assert config["AudioContext:sampleRate"] == 48000
    assert config["AudioContext:maxChannelCount"] == 2
    assert config["media:spoof_codecs"] is True
    assert config["fonts:metrics"] == "windows"
    assert config["media:hwCodecs"] == utils.WINDOWS_HW_CODECS
    assert config["webGpu:limits"] == utils.WINDOWS_WEBGPU_LIMITS


def test_macos_identity_gets_codecs_and_subpixel_only(launch):
    config, prefs = launch(MAC_UA)
    assert prefs["gfx.text.subpixel-position.force-enabled"] is True
    assert config["media:spoof_codecs"] is True
    # Windows-only values (unmeasured on macOS) stay unset.
    assert "ui.highlight" not in prefs
    assert "dom.webgpu.enabled" not in prefs
    assert "AudioContext:sampleRate" not in config


def test_linux_identity_on_linux_host_is_left_alone(launch):
    config, prefs = launch(LIN_UA)
    assert "gfx.text.subpixel-position.force-enabled" not in prefs
    assert "media:spoof_codecs" not in config
    assert "ui.highlight" not in prefs


def test_windows_identity_on_windows_host_is_left_alone(launch, monkeypatch):
    monkeypatch.setattr(utils, "_host_os_key", lambda: "win")
    config, prefs = launch(WIN_UA)
    assert "gfx.text.subpixel-position.force-enabled" not in prefs
    assert "media:spoof_codecs" not in config
    assert "dom.webgpu.enabled" not in prefs


def test_caller_values_win(launch):
    config, prefs = launch(
        WIN_UA,
        config={"AudioContext:sampleRate": 44100, "media:spoof_codecs": False},
        firefox_user_prefs={"ui.highlight": "#ff0000", "dom.webgpu.enabled": False},
    )
    assert config["AudioContext:sampleRate"] == 44100
    assert config["media:spoof_codecs"] is False
    assert prefs["ui.highlight"] == "#ff0000"
    assert prefs["dom.webgpu.enabled"] is False


@pytest.mark.parametrize("ua", [WIN_UA, MAC_UA, LIN_UA])
def test_css_animations_run_in_real_time(launch, ua):
    config, _ = launch(ua)
    assert config["disableInstantAnimations"] is True


def test_caller_can_keep_instant_animations(launch):
    config, _ = launch(LIN_UA, config={"disableInstantAnimations": False})
    assert config["disableInstantAnimations"] is False


class TestIpAccuracy:
    """An IP-derived position reports a city-scale accuracy, not the 6e-10 m the
    browser derived from float32 decimal places."""

    def test_database_radius_is_used(self):
        assert ip_accuracy("81.230.0.1", 20) == 20000.0

    def test_fallback_is_stable_and_in_range(self):
        low, high = IP_ACCURACY_RANGE_M
        a = ip_accuracy("81.230.0.1")
        assert a == ip_accuracy("81.230.0.1")
        assert low <= a <= high
        assert a == round(a)

    def test_fallback_varies_by_ip(self):
        assert len({ip_accuracy(f"81.230.0.{i}") for i in range(1, 20)}) > 1


class TestAudioNoiseOff:
    """Stock Firefox 152 renders the OfflineAudioContext probe identically on
    every machine (75.83002272993326 on Linux and Windows), so noise can only
    make an identity unique; it is off unless asked for."""

    def test_launch_default(self, launch):
        config, _ = launch(WIN_UA)
        assert config["audio:seed"] == 0

    def test_caller_seed_kept(self, launch):
        config, _ = launch(WIN_UA, config={"audio:seed": 9})
        assert config["audio:seed"] == 9

    def test_context_default(self):
        from camoufox.fingerprints import generate_context_fingerprint

        assert generate_context_fingerprint(os="windows")["config"]["audio:seed"] == 0
