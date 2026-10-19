"""Real, purchasable APC propellers (names from APC's published performance-data list).

The QMIL blades are aerodynamic designs nobody sells, so each one is matched to the
real APC model at the SAME diameter with the closest pitch. Matching is by pitch only:
chord and twist distribution are NOT compared, and APC's nominal pitch is not defined
exactly like our geometric pitch at 75% radius, so treat a match as "closest candidate
to buy and bench-test", not "same performance".

Model list source: https://www.apcprop.com/technical-information/performance-data/
(PER3_<model>.dat files). Excluded: marine, reverse-rotation/pusher (-RH, -LH),
pattern-plane (F2B) and ambiguous names. Product links are SEARCH links, not verified pages.
"""
from __future__ import annotations

import re

from .links import search_url

_MODELS = {
    12: ["12x10", "12x10E", "12x11", "12x12", "12x12E", "12x13", "12x14", "12x38SF", "12x4", "12x45MR",
         "12x47SF", "12x5", "12x55MR", "12x58SF", "12x6", "12x6E", "12x6SF", "12x7", "12x8", "12x8E",
         "12x8SF", "12x85F", "12x9"],
    9: ["9x10", "9x3", "9x3N", "9x37SF", "9x38SF", "9x4", "9x41SF", "9x44SFR", "9x45E", "9x45MR", "9x46SF",
        "9x47SF", "9x5", "9x5F", "9x6", "9x65", "9x6E", "9x6N", "9x6SF", "9x7", "9x75", "9x75E", "9x75SF",
        "9x8", "9x8E-3", "9x85", "9x9", "9x9E"],
}
# series by suffix: E = thin electric, SF = slow flyer, MR = multirotor, else standard (gas-engine shape)
_SUFFIX = re.compile(r"^(\d+)x(\d+)([A-Za-z\-0-9]*)$")


def parse_pitch(diameter: int, digits: str) -> float:
    """'6' -> 6, '10' -> 10, '45' on a 12in prop -> 4.5 (two digits above 1.4 x diameter = tenths)."""
    v = float(digits)
    return v if len(digits) == 1 or v <= 1.4 * diameter else v / 10.0


def _series(suffix: str) -> str:
    s = suffix.upper()
    if s.startswith("E") or s.startswith("8E"):
        return "E (electric)"
    if "SF" in s:
        return "SF (slow flyer)"
    if "MR" in s:
        return "MR (multirotor)"
    return "standard"


def _build():
    rows = []
    for dia, names in _MODELS.items():
        for n in names:
            m = _SUFFIX.match(n)
            rows.append({"diameter_in": dia, "name": f"APC {n}", "pitch_in": parse_pitch(dia, m.group(2)),
                         "series": _series(m.group(3))})
    return rows


CATALOG = _build()
_PREFERRED = {"E (electric)": 0, "SF (slow flyer)": 1, "MR (multirotor)": 1, "standard": 2}


def closest_real_props(diameter_in: float, pitch_in: float, n: int = 3, vendor="google"):
    """Closest real APC props at the same diameter: [{name, pitch_in, gap_in, series, url}], best first.

    Sorted by |pitch gap|; within 0.25 in of each other, electric-suitable series win.
    Empty list if no catalog entry exists for that diameter.
    """
    dia = round(diameter_in)
    pool = [c for c in CATALOG if c["diameter_in"] == dia]
    pool.sort(key=lambda c: (round(abs(c["pitch_in"] - pitch_in) / 0.25), _PREFERRED[c["series"]],
                             abs(c["pitch_in"] - pitch_in)))
    return [{**c, "gap_in": abs(c["pitch_in"] - pitch_in),
             "url": search_url(f"{c['name']} propeller", vendor)} for c in pool[:n]]
