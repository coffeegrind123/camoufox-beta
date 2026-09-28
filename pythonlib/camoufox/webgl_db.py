"""WebGL identities from webgl_data.db, behind fpgen's recorded devices.

fingerprints.webgl_for_gpu and fingerprints.sample_webgl_for_screen draw from
camoufox.webgl first and fall back to this table for a GPU fpgen has not
recorded, or when fpgen cannot answer at all.
"""

import sqlite3
from pathlib import Path
from typing import Dict, FrozenSet, Optional, Tuple

import numpy as np
import orjson

from camoufox.pkgman import OS_ARCH_MATRIX

DB_PATH = Path(__file__).parent / 'webgl_data.db'


def _load_webgl_data(data_str: str, os: str) -> Dict[str, str]:
    # Not at the top: camoufox.webgl imports fingerprints, which imports this
    # module. One extension filter for both sources: the same Firefox serves
    # either table.
    from camoufox.webgl import _filtered_extensions

    data = orjson.loads(data_str)
    blocked = _filtered_extensions(os)
    for key in ('webGl:supportedExtensions', 'webGl2:supportedExtensions'):
        exts = data.get(key)
        if isinstance(exts, list):
            data[key] = [e for e in exts if e not in blocked]
    return data


def database_gpus(os: str) -> FrozenSet[Tuple[str, str]]:
    """Every (vendor, renderer) pair webgl_data.db can serve for this OS."""
    if os not in OS_ARCH_MATRIX:
        raise ValueError(f'Invalid OS: {os}. Must be one of: win, mac, lin')
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            f'SELECT vendor, renderer FROM webgl_fingerprints WHERE {os} > 0'  # nosec
        ).fetchall()
    finally:
        conn.close()
    return frozenset(rows)


def sample_webgl(
    os: str, vendor: Optional[str] = None, renderer: Optional[str] = None, seed: Optional[int] = None
) -> Dict[str, str]:
    """
    Sample a random WebGL vendor/renderer combination and its data based on OS probabilities.
    Optionally use a specific vendor/renderer pair.

    Args:
        os: Operating system ('win', 'mac', or 'lin')
        vendor: Optional specific vendor to use
        renderer: Optional specific renderer to use (requires vendor to be set)

    Returns:
        Dict containing WebGL data including vendor, renderer and additional parameters

    Raises:
        ValueError: If invalid OS provided or no data found for OS/vendor/renderer
    """
    # Check that the OS is valid (avoid SQL injection)
    if os not in OS_ARCH_MATRIX:
        raise ValueError(f'Invalid OS: {os}. Must be one of: win, mac, lin')

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()

        if vendor and renderer:
            # Get specific vendor/renderer pair and verify it exists for this OS
            cursor.execute(
                f'SELECT vendor, renderer, data, {os} FROM webgl_fingerprints '  # nosec
                'WHERE vendor = ? AND renderer = ?',
                (vendor, renderer),
            )
            result = cursor.fetchone()

            if not result:
                raise ValueError(f'No WebGL data found for vendor "{vendor}" and renderer "{renderer}"')

            if result[3] <= 0:  # Check OS-specific probability
                # Get a list of possible (vendor, renderer) pairs for this OS
                cursor.execute(
                    f'SELECT DISTINCT vendor, renderer FROM webgl_fingerprints WHERE {os} > 0'  # nosec
                )
                possible_pairs = cursor.fetchall()
                raise ValueError(
                    f'Vendor "{vendor}" and renderer "{renderer}" combination not valid for {os.title()}.\n'
                    f'Possible pairs: {", ".join(str(pair) for pair in possible_pairs)}'
                )

            return _load_webgl_data(result[2], os)

        # Get all vendor/renderer pairs and their probabilities for this OS
        cursor.execute(
            f'SELECT vendor, renderer, data, {os} FROM webgl_fingerprints WHERE {os} > 0'  # nosec
        )
        results = cursor.fetchall()
    finally:
        conn.close()

    if not results:
        raise ValueError(f'No WebGL data found for OS: {os}')

    # Drop pairs this OS cannot report before sampling (an ANGLE string on
    # macOS, say), so a refreshed database cannot put one back in the draw.
    # Filtering here rather than repairing later keeps reported and sampled
    # WebGL parameters from the same recorded device.
    from camoufox.coherence import gpu_fits_os

    coherent = [row for row in results if gpu_fits_os(row[1], os)]
    if coherent:
        results = coherent

    # Split into separate arrays
    _, _, data_strs, probs = map(list, zip(*results))

    # Convert probabilities to numpy array and normalize
    probs_array = np.array(probs, dtype=np.float64)
    probs_array = probs_array / probs_array.sum()

    # Sample based on probabilities
    # Seeded so the same identity always draws the same device (#442/#765).
    idx = np.random.default_rng(seed).choice(len(probs_array), p=probs_array)

    # Parse the JSON data string
    return _load_webgl_data(data_strs[idx], os)
