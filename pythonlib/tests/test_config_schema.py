"""
Guard: every config key the browser reads must be declared in the schema.

Regression guard for the `media:spoof_codecs` gap in PR #562. The C++ side read
the key via MaskConfig::GetBool("media:spoof_codecs"), but nothing ever added it
to settings/properties.json, and validate_config() drops any key it does not
recognise -- printing "Skipping unknown patch media:spoof_codecs" and moving on.
The documented usage,

    AsyncCamoufox(config={"media:spoof_codecs": True})

therefore did nothing at all: the key never reached the browser, so the feature
could not be switched on through the supported path.

This is the read-but-undeclared direction of a mistake the project has made
before in the other direction -- canvas:seed (#721) and navigator.maxTouchPoints
(#696) were both declared in the schema while nothing consumed them. A patch and
a schema entry are two halves of one change; this test fails the build when only
one half lands.

Run with:
    cd pythonlib && python -m pytest tests/test_config_schema.py -v
"""

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROPERTIES = REPO / "settings" / "properties.json"

# MaskConfig::GetBool("k") / GetString("k") / GetUint32("k") / HasKey("k") ...
MASKCONFIG_READ = re.compile(r'MaskConfig::(?:Get|Has)\w*\(\s*"([^"]+)"')

# Keys read through a variable or built at runtime rather than a string literal.
# Add here (with a reason) only when the read genuinely cannot name its key.
ALLOWED_UNDECLARED: set = set()


def _sources():
    for pattern in ("patches/**/*.patch", "additions/**/*"):
        for path in REPO.glob(pattern):
            if path.is_file():
                yield path


def _declared_keys() -> set:
    return {entry["property"] for entry in json.loads(PROPERTIES.read_text())}


def _keys_read() -> dict:
    """Map config key -> sorted list of files that read it."""
    found: dict = {}
    for path in _sources():
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for match in MASKCONFIG_READ.finditer(text):
            found.setdefault(match.group(1), set()).add(
                str(path.relative_to(REPO))
            )
    return {k: sorted(v) for k, v in found.items()}


def test_properties_json_is_wellformed():
    entries = json.loads(PROPERTIES.read_text())
    assert entries, "settings/properties.json is empty"
    for entry in entries:
        assert "property" in entry and "type" in entry, f"malformed entry: {entry}"


def test_every_key_the_browser_reads_is_declared():
    declared = _declared_keys()
    read = _keys_read()
    assert read, "found no MaskConfig reads -- the scanner regexp has gone stale"

    undeclared = {
        key: files
        for key, files in read.items()
        if key not in declared and key not in ALLOWED_UNDECLARED
    }
    if undeclared:
        lines = [
            "config keys are read by the browser but missing from "
            "settings/properties.json,",
            "so validate_config() silently drops them and the feature cannot be "
            "enabled through the Python API:",
            "",
        ]
        for key, files in sorted(undeclared.items()):
            lines.append(f"  {key}")
            for f in files:
                lines.append(f"      read in {f}")
        pytest.fail("\n".join(lines))


@pytest.mark.parametrize("key", ["media:spoof_codecs"])
def test_known_previously_missing_keys_stay_declared(key):
    """Pin the specific keys this guard was written for, so a schema edit that
    drops one fails loudly here rather than only in the general scan above."""
    assert key in _declared_keys(), (
        f"{key} is read by the browser but is not declared in "
        f"settings/properties.json -- see PR #562"
    )
