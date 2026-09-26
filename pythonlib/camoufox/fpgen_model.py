"""
fpgen's model data, installed from a pinned release before fpgen is imported.

Left to itself, `import fpgen` fetches its model the first time, from whichever
release the unauthenticated GitHub API lists first, with TLS verification off,
into its own package directory -- and fetches it again whenever the files are
more than five weeks old (fpgen.pkgman.assert_downloaded / files_are_recent).
That fails in three ways:

- the API allows 60 unauthenticated requests an hour per IP, so CI runners and
  shared egress IPs get a 403 and no fingerprint can be generated (Tests run
  36247317299: 22 of 26 patch guards died on it);
- a package directory the launching user cannot write (a Docker image built as
  root and run as another user, a read-only site-packages) fails every launch
  once the model is five weeks old, however it was seeded;
- the model is whatever scrapfly listed first on the day, not a pinned input.

So the model is pinned here by URL and sha256, downloaded with TLS verified,
checked file by file, and stamped with a far-future mtime so fpgen's five-week
refresh never fires for a model this module installed.
"""

import hashlib
import importlib.util
import os
import shutil
import tempfile
import time
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional
from zipfile import ZipFile

from .exceptions import CorruptedDownload, FpgenModelError
from .pkgman import rprint, verify_sha256, webdl

# The release fpgen's own fetcher picks today: the API lists model-4/2025 ahead
# of the newer model-2/2026, and fpgen takes the first zip it sees. Pinning it
# keeps every generated fingerprint on the corpus the launcher was measured
# against. Moving to another model is a deliberate change: update both values.
FPGEN_MODEL_URL = (
    "https://github.com/scrapfly/fingerprint-generator/releases/download/"
    "model-4/2025/model-release.zip"
)
FPGEN_MODEL_SHA256 = "5059ccbcd364020f4325c18de0352d78e63852ff5e6fdd6a8eddaa04b55c61d1"

# The archive's members, as fpgen.pkgman.FILE_PAIRS names their compressed form.
FPGEN_MODEL_FILES: Dict[str, str] = {
    "fingerprint-network.json.zst": "d2340d91b72f81e786e88ec5dc56275d020582e8108f1311636a490162fec65d",
    "values.json.zst": "6f9cbd73d68517a479c2d2369a4c90f67292c1bf7556362a8cc76617562f097d",
    "values.dat.zst": "07d502512b3c4aefac855094e308322b6daf7c815e3fdf1da91ec6d8d5e1fe63",
}

# `python -m fpgen decompress` replaces each .zst with its decompressed file;
# fpgen then reads (and ages) those instead.
DECOMPRESSED_FILES = ["fingerprint-network.json", "values.json", "values.dat"]

# 2100-01-01T00:00:00Z. fpgen refreshes files whose mtime is more than five
# weeks in the past; this one never is. It also marks the files as ones this
# module wrote and verified, which lets later launches skip re-hashing them.
PINNED_MTIME = 4102444800

# fpgen.pkgman.files_are_recent: older than this and fpgen fetches again.
FPGEN_MAX_AGE_S = 5 * 7 * 24 * 3600

# fpgen honours this to fetch a custom (possibly password-protected) model.
# Someone who set it chose their model; this module stays out of the way.
CUSTOM_MODEL_ENV = "FPGEN_MODEL_URL"

_LOCK = Lock()


def fpgen_data_dir() -> Path:
    """
    Where fpgen reads its model from, found without importing fpgen (importing
    it is what triggers its own fetch).
    """
    spec = importlib.util.find_spec("fpgen")
    if spec is None or spec.origin is None:
        raise FpgenModelError("fpgen is not installed.")
    return Path(spec.origin).parent / "data"


def ensure_fpgen_model(data_dir: Optional[Path] = None) -> None:
    """
    Make sure fpgen will find a pinned, current-looking model and fetch nothing.

    - No model: download the pinned release, verify it, install it.
    - The pinned model, stamped by an earlier call: nothing to do.
    - A model fpgen fetched itself (or an older launcher seeded): kept if its
      files hash to the pinned ones, then stamped; replaced if they do not.
    - A decompressed model: kept and stamped. Its content cannot be checked
      against the archive's hashes, and decompressing is a deliberate act.
    """
    if os.getenv(CUSTOM_MODEL_ENV):
        return

    data_dir = data_dir or fpgen_data_dir()
    with _LOCK:
        try:
            _ensure(data_dir)
        except PermissionError as e:
            raise FpgenModelError(
                f"fpgen's model directory is not writable by this user: {data_dir}\n"
                "Install the model as the directory's owner once, e.g. while building "
                "the image: python -m camoufox fetch"
            ) from e


def _ensure(data_dir: Path) -> None:
    decompressed = [data_dir / name for name in DECOMPRESSED_FILES]
    if all(p.exists() for p in decompressed):
        _stamp(decompressed)
        return

    compressed = [data_dir / name for name in FPGEN_MODEL_FILES]
    if all(p.exists() for p in compressed):
        if all(_stamped(p) for p in compressed):
            return
        if all(_hash(p) == FPGEN_MODEL_FILES[p.name] for p in compressed):
            _stamp(compressed)
            return
        rprint(f"fpgen model in {data_dir} is not the pinned release; replacing it.", fg="yellow")
        try:
            _install(data_dir)
        except PermissionError:
            # Same rule as _stamp: an unpinned model fpgen still accepts beats
            # no fingerprint at all.
            if not all(_fpgen_considers_current(p) for p in compressed):
                raise
            rprint("Cannot replace it (directory not writable); using it as is.", fg="yellow")
        return

    _install(data_dir)


def _install(data_dir: Path) -> None:
    # One line, not webdl's per-chunk percentages: this runs inside a launch,
    # whose output usually lands in a log.
    rprint(f"Downloading fpgen model: {FPGEN_MODEL_URL}")
    buffer = webdl(FPGEN_MODEL_URL, progress_callback=lambda done, total: None)
    verify_sha256(buffer, FPGEN_MODEL_SHA256, "fpgen model")

    data_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix=".model.tmp-", dir=data_dir))
    try:
        with ZipFile(buffer) as zf:
            names = set(zf.namelist())
            if names != set(FPGEN_MODEL_FILES):
                raise CorruptedDownload(
                    f"fpgen model archive holds {sorted(names)}, "
                    f"expected {sorted(FPGEN_MODEL_FILES)}."
                )
            for name, expected in FPGEN_MODEL_FILES.items():
                data = zf.read(name)
                actual = hashlib.sha256(data).hexdigest()
                if actual != expected:
                    raise CorruptedDownload(
                        f"fpgen model member {name}: sha256 {actual}, expected {expected}."
                    )
                (tmp_dir / name).write_bytes(data)

        # Stamp before moving: a file that appears under its final name is
        # already current in fpgen's eyes. Each rename is atomic, so a
        # concurrent reader sees the old file or the new one, never a torn one.
        staged = [tmp_dir / name for name in FPGEN_MODEL_FILES]
        _stamp(staged)
        for path in staged:
            os.replace(path, data_dir / path.name)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _stamped(path: Path) -> bool:
    return int(path.stat().st_mtime) == PINNED_MTIME


def _stamp(paths: List[Path]) -> None:
    """
    Stamp each file so fpgen never considers it stale. A file this user may not
    touch (seeded by root for a non-root runtime) is fine as long as fpgen
    still considers it current; it becomes an error only once fpgen would
    refetch it.
    """
    for path in paths:
        if _stamped(path):
            continue
        try:
            os.utime(path, (PINNED_MTIME, PINNED_MTIME))
        except PermissionError:
            if not _fpgen_considers_current(path):
                raise


def _fpgen_considers_current(path: Path) -> bool:
    return path.stat().st_mtime >= time.time() - FPGEN_MAX_AGE_S


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
