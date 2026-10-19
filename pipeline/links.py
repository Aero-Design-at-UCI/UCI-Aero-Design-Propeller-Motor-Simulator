"""
links.py
=========
Generates shopping links for plot nodes.

* Props: the pipeline designs custom blades that nobody sells, so each prop is
  mapped to the NEAREST off-the-shelf size (diameter x pitch rounded to the
  nearest half inch) and linked to a search for that APC size.
* Motors: a catalog URL if the motors JSON entry has a "url" key, otherwise a
  search for that Kv on the right cell count.

These are search links, not verified product pages.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote_plus

VENDORS = {
    "google": "https://www.google.com/search?q=",
    "amazon": "https://www.amazon.com/s?k=",
}


def search_url(query: str, vendor: str = "google") -> str:
    return VENDORS.get(vendor, VENDORS["google"]) + quote_plus(query)


def nearest_pitch(pitch_in: float, step: float = 0.5) -> float:
    return max(step, round(pitch_in / step) * step)


def prop_label(diameter_in: float, pitch_in: float, step: float = 0.5) -> str:
    return f"{round(diameter_in):g}x{nearest_pitch(pitch_in, step):g}"


def prop_search_url(diameter_in: float, pitch_in: float, vendor: str = "google") -> str:
    return search_url(f"APC {prop_label(diameter_in, pitch_in)} electric propeller", vendor)


def motor_search_url(kv: float, cells: int = 4, vendor: str = "google") -> str:
    return search_url(f"{kv:.0f}Kv brushless outrunner motor {cells}S", vendor)


def load_motor_urls(motors_file) -> dict:
    """name -> url for every motor entry that has a "url" key."""
    path = Path(motors_file)
    if not path.exists():
        return {}
    try:
        motors = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {m["name"]: m["url"] for m in motors if "name" in m and m.get("url")}
