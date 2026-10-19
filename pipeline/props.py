"""Prop axis: a family of QMIL blades at the fixed diameter, varying design thrust.

Changing the design-thrust target changes twist/chord, i.e. effective pitch.
`prop_table` reads the finished .prop files back and reports diameter, geometric
pitch and the nearest buyable APC size + search link for each.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import catalog, links, propfile
from .qmil_io import design_prop, design_speed_for


def generate_props(config, qmil_exe, count, out_dir, workdir, design_rpm=6000.0):
    """Design `count` props. Returns the number that succeeded."""
    lo = 0.6 * min(config["climb_thrust_per_prop_N"], config["takeoff_thrust_per_prop_N"])
    hi = 1.2 * max(config["climb_thrust_per_prop_N"], config["takeoff_thrust_per_prop_N"])
    out_dir, workdir = Path(out_dir), Path(workdir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    made = 0
    for i in range(count):
        thrust = lo + (hi - lo) * (i / (count - 1) if count > 1 else 0.0)
        stem = f"p{i:02d}"
        prop_path, text = design_prop(
            qmil_exe, workdir / stem, stem,
            diameter_in=config["prop_diameter_in"],
            design_speed_mps=design_speed_for(config),
            rpm=design_rpm, thrust_n=thrust,
            label=f"Prop grid point {stem} (design T={thrust:.2f} N)",
        )
        if prop_path is None:
            print(f"  [warn] QMIL failed for {stem} (design thrust {thrust:.2f} N): ...{text.strip()[-200:]}")
            continue
        (out_dir / prop_path.name).write_bytes(prop_path.read_bytes())
        made += 1
    print(f"Generated {made}/{count} prop geometries in {out_dir}")
    return made


def prop_table(props_dir, vendor="google") -> pd.DataFrame:
    """One row per .prop: prop, diameter_in, pitch_in, prop_label, prop_url."""
    rows = []
    for path in sorted(Path(props_dir).glob("*.prop")):
        try:
            d, pitch = propfile.diameter_in(path), propfile.geometric_pitch_in(path)
        except ValueError as exc:
            print(f"  [warn] {exc}")
            continue
        near = catalog.closest_real_props(d, pitch, 3, vendor)
        if near:
            b = near[0]
            label, url, gap = b["name"], b["url"], b["gap_in"]
            alts = "; ".join(f"{x['name']} ({x['pitch_in']:g} in)" for x in near[1:])
            real_pitch, series = b["pitch_in"], b["series"]
        else:   # diameter not in the catalog: fall back to a generic search
            label, url, gap = f"APC {links.prop_label(d, pitch)}", links.prop_search_url(d, pitch, vendor), float("nan")
            alts, real_pitch, series = "", float("nan"), ""
        rows.append({"prop": path.stem, "diameter_in": d, "pitch_in": pitch, "prop_label": label,
                     "prop_url": url, "real_pitch_in": real_pitch, "pitch_gap_in": gap,
                     "real_series": series, "alternatives": alts})
    return pd.DataFrame(rows, columns=["prop", "diameter_in", "pitch_in", "prop_label", "prop_url",
                                     "real_pitch_in", "pitch_gap_in", "real_series", "alternatives"])
