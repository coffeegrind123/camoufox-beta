"""
Tests for camoufox.fpgen_model: fpgen's model installed from a pinned release.

Regression guard for Tests run 36247317299, where 22 of 26 patch guards died
before launching anything: `import fpgen` asked the unauthenticated GitHub API
for its model and got "403 rate limit exceeded". The same fetcher re-runs once
the files are five weeks old, which breaks a root-seeded Docker image for a
non-root runtime five weeks after it was built.

Run with:
    cd pythonlib && python -m pytest tests/test_fpgen_model.py -v
"""

import hashlib
import io
import json
import os
import subprocess
import sys
import time
import zipfile

import pytest

# Make `import camoufox` resolve to the in-tree pythonlib without an install.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from camoufox import fpgen_model  # noqa: E402
from camoufox.exceptions import CorruptedDownload, FpgenModelError  # noqa: E402
from camoufox.fpgen_model import (  # noqa: E402
    DECOMPRESSED_FILES,
    FPGEN_MAX_AGE_S,
    PINNED_MTIME,
    ensure_fpgen_model,
)

MEMBERS = {
    "fingerprint-network.json.zst": b"network" * 1000,
    "values.json.zst": b"values-json" * 1000,
    "values.dat.zst": b"values-dat" * 1000,
}
STALE = time.time() - FPGEN_MAX_AGE_S - 86400


def _archive(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


@pytest.fixture
def pinned(monkeypatch):
    """
    Pin a small synthetic model instead of the 7 MB release, and count the
    downloads. Returns the list of downloaded URLs; set `.payload` to serve
    different bytes than the pin describes.
    """
    archive = _archive(MEMBERS)
    monkeypatch.setattr(fpgen_model, "FPGEN_MODEL_SHA256", hashlib.sha256(archive).hexdigest())
    monkeypatch.setattr(
        fpgen_model,
        "FPGEN_MODEL_FILES",
        {name: hashlib.sha256(data).hexdigest() for name, data in MEMBERS.items()},
    )
    monkeypatch.delenv("FPGEN_MODEL_URL", raising=False)

    class Downloads(list):
        payload = archive

    downloads = Downloads()

    def fake_webdl(url, desc=None, buffer=None, bar=True, progress_callback=None):
        downloads.append(url)
        return io.BytesIO(downloads.payload)

    monkeypatch.setattr(fpgen_model, "webdl", fake_webdl)
    return downloads


def _write(data_dir, members, mtime=None):
    data_dir.mkdir(parents=True, exist_ok=True)
    for name, data in members.items():
        path = data_dir / name
        path.write_bytes(data)
        if mtime is not None:
            os.utime(path, (mtime, mtime))


def _mtimes(data_dir, names):
    return {name: int((data_dir / name).stat().st_mtime) for name in names}


def test_missing_model_is_installed_and_stamped(tmp_path, pinned):
    data_dir = tmp_path / "data"
    ensure_fpgen_model(data_dir)

    assert pinned == [fpgen_model.FPGEN_MODEL_URL]
    for name, data in MEMBERS.items():
        assert (data_dir / name).read_bytes() == data
    assert set(_mtimes(data_dir, MEMBERS).values()) == {PINNED_MTIME}
    # No staging directory left behind.
    assert sorted(p.name for p in data_dir.iterdir()) == sorted(MEMBERS)


def test_stamped_model_is_not_downloaded_or_rehashed(tmp_path, pinned, monkeypatch):
    data_dir = tmp_path / "data"
    ensure_fpgen_model(data_dir)
    monkeypatch.setattr(fpgen_model, "_hash", lambda path: pytest.fail("re-hashed a stamped file"))

    ensure_fpgen_model(data_dir)

    assert len(pinned) == 1


def test_stale_pinned_model_is_restamped_not_refetched(tmp_path, pinned):
    """The five-week case: fpgen would fetch again; the pin says nothing changed."""
    data_dir = tmp_path / "data"
    _write(data_dir, MEMBERS, mtime=STALE)

    ensure_fpgen_model(data_dir)

    assert pinned == []
    assert set(_mtimes(data_dir, MEMBERS).values()) == {PINNED_MTIME}


def test_unpinned_model_is_replaced(tmp_path, pinned):
    data_dir = tmp_path / "data"
    _write(data_dir, {**MEMBERS, "values.dat.zst": b"another model"})

    ensure_fpgen_model(data_dir)

    assert len(pinned) == 1
    assert (data_dir / "values.dat.zst").read_bytes() == MEMBERS["values.dat.zst"]


def test_partial_model_is_completed(tmp_path, pinned):
    data_dir = tmp_path / "data"
    _write(data_dir, {"values.json.zst": MEMBERS["values.json.zst"]})

    ensure_fpgen_model(data_dir)

    assert len(pinned) == 1
    assert all((data_dir / name).exists() for name in MEMBERS)


@pytest.mark.parametrize(
    "tamper",
    [
        pytest.param(lambda a: a[:-1], id="truncated-archive"),
        pytest.param(lambda a: _archive({**MEMBERS, "values.dat.zst": b"x"}), id="member-changed"),
    ],
)
def test_tampered_download_installs_nothing(tmp_path, pinned, tamper):
    data_dir = tmp_path / "data"
    pinned.payload = tamper(_archive(MEMBERS))

    with pytest.raises(CorruptedDownload):
        ensure_fpgen_model(data_dir)

    assert not data_dir.exists() or list(data_dir.iterdir()) == []


def test_member_hashes_are_checked_even_when_the_archive_hash_matches(tmp_path, pinned, monkeypatch):
    """The archive digest and the per-file digests are two pins; either catches a bad model."""
    bad = _archive({**MEMBERS, "values.dat.zst": b"x"})
    pinned.payload = bad
    monkeypatch.setattr(fpgen_model, "FPGEN_MODEL_SHA256", hashlib.sha256(bad).hexdigest())

    with pytest.raises(CorruptedDownload, match="values.dat.zst"):
        ensure_fpgen_model(tmp_path / "data")


def test_decompressed_model_is_kept_and_stamped(tmp_path, pinned):
    data_dir = tmp_path / "data"
    _write(data_dir, {name: b"{}" for name in DECOMPRESSED_FILES}, mtime=STALE)

    ensure_fpgen_model(data_dir)

    assert pinned == []
    assert set(_mtimes(data_dir, DECOMPRESSED_FILES).values()) == {PINNED_MTIME}


def test_custom_model_url_is_left_to_fpgen(tmp_path, pinned, monkeypatch):
    monkeypatch.setenv("FPGEN_MODEL_URL", "https://example.invalid/model.zip")
    data_dir = tmp_path / "data"

    ensure_fpgen_model(data_dir)

    assert pinned == []
    assert not data_dir.exists()


needs_non_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores file permissions"
)


@pytest.fixture
def read_only(tmp_path):
    """A data dir this user can read but not write, like a root-seeded image."""
    data_dir = tmp_path / "data"
    yield data_dir
    if data_dir.exists():
        data_dir.chmod(0o755)


@needs_non_root
def test_read_only_fresh_model_is_used_as_is(read_only, pinned):
    """A root-seeded model under five weeks old: fpgen accepts it, so must we."""
    _write(read_only, MEMBERS)
    read_only.chmod(0o555)
    for name in MEMBERS:
        (read_only / name).chmod(0o444)

    ensure_fpgen_model(read_only)

    assert pinned == []


@needs_non_root
def test_read_only_stale_model_fails_with_a_fix(read_only, pinned, monkeypatch):
    _write(read_only, MEMBERS, mtime=STALE)
    read_only.chmod(0o555)
    # utime on a file one does not own raises EPERM; chmod alone cannot
    # reproduce that for the owner, so stand in for the kernel.
    def eperm(path, times):
        raise PermissionError(1, "Operation not permitted", str(path))

    monkeypatch.setattr(fpgen_model.os, "utime", eperm)

    with pytest.raises(FpgenModelError, match="camoufox fetch"):
        ensure_fpgen_model(read_only)
    assert pinned == []


@needs_non_root
def test_read_only_missing_model_fails_with_a_fix(read_only, pinned):
    read_only.mkdir()
    read_only.chmod(0o555)

    with pytest.raises(FpgenModelError, match=str(read_only)):
        ensure_fpgen_model(read_only)


def test_constants_match_the_installed_fpgen():
    """
    The file names and the five-week window are fpgen's; if an fpgen release
    renames a file or changes the window, this module would install a model
    fpgen cannot see. FPGEN_NO_INIT keeps fpgen from fetching while it is read.
    """
    probe = (
        "import json, fpgen.pkgman as p;"
        "print(json.dumps({"
        "'dir': str(p.DATA_DIR),"
        "'compressed': sorted(v.name for v in p.FILE_PAIRS.values()),"
        "'decompressed': sorted(k.name for k in p.FILE_PAIRS.keys())}))"
    )
    env = {**os.environ, "FPGEN_NO_INIT": "1"}
    out = subprocess.run(
        [sys.executable, "-c", probe], env=env, capture_output=True, text=True, check=True
    )
    seen = json.loads(out.stdout.strip().splitlines()[-1])

    assert seen["dir"] == str(fpgen_model.fpgen_data_dir())
    assert seen["compressed"] == sorted(fpgen_model.FPGEN_MODEL_FILES)
    assert seen["decompressed"] == sorted(DECOMPRESSED_FILES)

    source = (fpgen_model.fpgen_data_dir().parent / "pkgman.py").read_text()
    assert "timedelta(weeks=5)" in source, "fpgen changed its refresh window"
