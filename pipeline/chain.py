"""The original 3-stage chain: PyThrust Kv search -> QMIL design -> QPROP check -> rank.

One candidate = one Kv paired with its own QMIL blade (the "diagonal").
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .defaults import DEFAULT_NO_LOAD_CURRENT_A, DEFAULT_RESISTANCE_OHM
from .qmil_io import design_prop, design_speed_for
from .qprop_io import solve_voltage_for_thrust, write_motor_file

THRUST_TOLERANCE = 0.02


def design_candidates(candidates, config, qmil_exe, workdir):
    """Stage 2. Returns candidates QMIL succeeded on (adds cand_dir / prop_file)."""
    base = Path(workdir).resolve()
    good = []
    for i, c in enumerate(candidates):
        cdir = base / f"c{i:02d}"
        stem = f"kv{c['kv']:.0f}"
        path, text = design_prop(qmil_exe, cdir, stem, diameter_in=c["diameter_in"],
                                 design_speed_mps=design_speed_for(config), rpm=c["takeoff_rpm"],
                                 thrust_n=config["takeoff_thrust_per_prop_N"],
                                 label=f"Candidate Kv={c['kv']:.1f}")
        if path is None:
            print(f"  [warn] QMIL failed for Kv={c['kv']:.1f}: ...{text.strip()[-200:]}")
            continue
        c["cand_dir"], c["prop_file"] = str(cdir), str(path)
        good.append(c)
    return good


def validate_candidates(candidates, config, qprop_exe):
    """Stage 3. Bisect motor voltage (capped at pack voltage) to hit each thrust target."""
    good = []
    for c in candidates:
        cdir, prop = Path(c["cand_dir"]), Path(c["prop_file"]).name
        write_motor_file(cdir / "motor.mot", {"name": f"Kv{c['kv']:.0f}", "kv": c["kv"],
                                              "rm": DEFAULT_RESISTANCE_OHM, "i0": DEFAULT_NO_LOAD_CURRENT_A})
        vmax = config["voltage_v"]
        c["qprop_takeoff"], _ = solve_voltage_for_thrust(qprop_exe, cdir, prop, "motor.mot",
            config["takeoff_speed_mps"], config["takeoff_thrust_per_prop_N"], vmax)
        c["qprop_climb"], _ = solve_voltage_for_thrust(qprop_exe, cdir, prop, "motor.mot",
            config["climb_speed_mps"], config["climb_thrust_per_prop_N"], vmax)
        if c["qprop_takeoff"] is None or c["qprop_climb"] is None:
            print(f"  [warn] QPROP failed for Kv={c['kv']:.1f}")
            continue
        good.append(c)
    return good


def rank(candidates, config, max_amps) -> pd.DataFrame:
    rows = []
    for c in candidates:
        to, cl = c["qprop_takeoff"], c["qprop_climb"]
        eff = lambda r: r["Pshaft_W"] / r["Pelec_W"] * 100.0 if r["Pelec_W"] > 1e-3 else float("nan")
        meets = (to["T_N"] >= config["takeoff_thrust_per_prop_N"] * (1 - THRUST_TOLERANCE)
                 and cl["T_N"] >= config["climb_thrust_per_prop_N"] * (1 - THRUST_TOLERANCE))
        within = to["Amps"] <= max_amps and cl["Amps"] <= max_amps
        rows.append({
            "kv": c["kv"], "diameter_in": c["diameter_in"], "prop_file": c["prop_file"],
            "meets_spec": meets, "within_current_limit": within,
            "takeoff_thrust_N": to["T_N"], "takeoff_pelec_W": to["Pelec_W"],
            "takeoff_pshaft_W": to["Pshaft_W"], "takeoff_amps": to["Amps"], "takeoff_eff_pct": eff(to),
            "climb_thrust_N": cl["T_N"], "climb_pelec_W": cl["Pelec_W"],
            "climb_pshaft_W": cl["Pshaft_W"], "climb_amps": cl["Amps"], "climb_eff_pct": eff(cl),
            "avg_power_W": (to["Pelec_W"] + cl["Pelec_W"]) / 2.0,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["_ok"] = df["meets_spec"] & df["within_current_limit"]
    return df.sort_values(["_ok", "avg_power_W"], ascending=[False, True]).drop(columns="_ok").reset_index(drop=True)


def run_chain(config, *, qmil_exe, qprop_exe, data_dir, workdir, max_amps) -> pd.DataFrame:
    from .search import search_kv_candidates
    print("=== Stage 1: PyThrust Kv search ===")
    cands = search_kv_candidates(config, data_dir, max_amps)
    print(f"  {len(cands)} feasible candidate(s)")
    if not cands:
        raise SystemExit("No Kv satisfied both thrust targets in PyThrust's model. "
                         "Widen kv_min/kv_max or lower the targets.")
    print("=== Stage 2: QMIL blade design ===")
    cands = design_candidates(cands, config, qmil_exe, workdir)
    print(f"  {len(cands)} got a blade")
    if not cands:
        raise SystemExit("QMIL failed for every candidate - run: python -m pipeline doctor")
    print("=== Stage 3: QPROP validation ===")
    cands = validate_candidates(cands, config, qprop_exe)
    print(f"  {len(cands)} validated")
    if not cands:
        raise SystemExit("QPROP failed for every candidate - run: python -m pipeline doctor")
    return rank(cands, config, max_amps)
