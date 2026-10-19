"""Read geometry out of a QPROP .prop file (radius / chord / blade angle table)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .units import M_TO_IN


def read_stations(path):
    """Return (r_m, chord_m, beta_deg) arrays from the station table."""
    rs, cs, betas = [], [], []
    in_table = False
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if s.startswith("#") and "beta" in s.lower():
            in_table = True
            continue
        if not in_table or not s or s.startswith("#"):
            continue
        parts = s.split()
        if len(parts) >= 3:
            try:
                r, c, b = float(parts[0]), float(parts[1]), float(parts[2])
            except ValueError:
                continue
            rs.append(r); cs.append(c); betas.append(b)
    if len(rs) < 2:
        raise ValueError(f"No r/c/beta station table found in {path}")
    return np.array(rs), np.array(cs), np.array(betas)


def diameter_in(path) -> float:
    r, _, _ = read_stations(path)
    return 2.0 * float(r.max()) * M_TO_IN


def geometric_pitch_in(path, frac: float = 0.75) -> float:
    """Geometric pitch (in) at `frac` of tip radius: 2*pi*r*tan(beta).

    Comparable in spirit to the second number in a name like 12x6, but not
    guaranteed to equal a manufacturer's nominal pitch.
    """
    r, _, beta = read_stations(path)
    r_eval = frac * float(r.max())
    beta_eval = float(np.interp(r_eval, r, beta))
    return 2.0 * np.pi * r_eval * np.tan(np.radians(beta_eval)) * M_TO_IN
