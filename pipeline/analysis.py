"""Flight-performance estimates for the top feasible candidates.

Per-motor numbers come from the sweep; anything about the battery or aircraft is
multiplied by num_props (all motors share one pack).

Airframe assumptions are NOT from the simulation: L/D and cruise speed are
arguments, drag is weight/(L/D) at cruise and scales with V^2.
Not modeled: SAE power limiter, battery sag, heating, wind, real drag polar.
"""
from __future__ import annotations

import concurrent.futures as cf
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .qprop_io import run_point, solve_voltage_for_thrust
from .sweep import combo_dir
from .units import LBF_TO_N, N_TO_LBF


@dataclass
class Assumptions:
    ld_ratio: float = 8.0
    cruise_speed: float = 15.0
    usable_fraction: float = 0.8
    esc_efficiency: float = 0.95
    max_speed: float = 40.0
    speed_step: float = 2.0


def weight_newtons(config) -> float:
    if "total_weight_N" in config:
        return float(config["total_weight_N"])
    if "total_weight_lb" in config:
        return float(config["total_weight_lb"]) * LBF_TO_N
    raise KeyError("config needs total_weight_N (or total_weight_lb) for flight estimates")


def first_crossing(xs, ys):
    """x where ys first goes from >= 0 to < 0 (linear interpolation), else NaN."""
    for i in range(1, len(xs)):
        if ys[i - 1] >= 0 > ys[i]:
            f = ys[i - 1] / (ys[i - 1] - ys[i])
            return xs[i - 1] + f * (xs[i] - xs[i - 1])
    return float("nan")


def select_top(df, top, rank_by="thrust"):
    ok = df[df["qualifies"] & (df["takeoff_thrust_N"] > 0) & (df["climb_thrust_N"] > 0)]
    key, asc = {"thrust": ("takeoff_thrust_N", False), "current": ("takeoff_amps", True),
                "efficiency": ("takeoff_eff_pct", False)}[rank_by]
    return ok.sort_values(key, ascending=asc).head(top)


def analyze_candidate(row, config, qprop_exe, workdir, a: Assumptions):
    d = combo_dir(workdir, row["motor"], row["prop"])
    prop = f"{row['prop']}.prop"
    if not (d / "motor.mot").exists() or not (d / prop).exists():
        print(f"  [skip] {d.name}: files not found in {d.parent} (was the sweep run for this run name?)")
        return None, None

    n = int(config["num_props"]); w = weight_newtons(config)
    vpack = config["voltage_v"]; cap_ah = config["battery_capacity_mah"] / 1000.0
    usable = cap_ah * a.usable_fraction; vclimb = config["climb_speed_mps"]
    drag_c = w / a.ld_ratio
    drag = lambda v: drag_c * (v / a.cruise_speed) ** 2

    sweep = []
    for v in np.arange(0.0, a.max_speed + 1e-9, a.speed_step):
        r = run_point(qprop_exe, d, prop, "motor.mot", float(v), vpack)
        if r is not None:
            sweep.append((float(v), n * r["T_N"]))
    sv = [s[0] for s in sweep]; st = [s[1] for s in sweep]

    to_a, cl_a = n * row["takeoff_amps"], n * row["climb_amps"]
    roc = (n * row["climb_thrust_N"] - drag(vclimb)) * vclimb / w

    nan = float("nan"); thr = ib = mins = nan
    top = run_point(qprop_exe, d, prop, "motor.mot", a.cruise_speed, vpack)
    if top is not None and top["T_N"] >= drag_c / n:
        best, _ = solve_voltage_for_thrust(qprop_exe, d, prop, "motor.mot", a.cruise_speed,
                                           drag_c / n, vpack, tol_N=0.02, max_iter=25)
        if best is not None:
            thr = best["Volts"] / vpack
            ib = n * best["Pelec_W"] / (vpack * a.esc_efficiency)
            mins = usable / ib * 60.0

    out = {
        "motor": row["motor"], "prop": row["prop"], "kv": row["kv"],
        "prop_label": row.get("prop_label", ""), "prop_url": row.get("prop_url", ""),
        "T/O thrust/motor (N)": row["takeoff_thrust_N"],
        "T/O thrust/motor (lbf)": row["takeoff_thrust_N"] * N_TO_LBF,
        "T/O amps/motor (A)": row["takeoff_amps"], "T/O total amps (A)": to_a,
        "T/O batt C-rate req": to_a / cap_ah,
        "T/O thrust-to-weight": n * row["takeoff_thrust_N"] / w,
        "full-throttle runtime (min)": usable / to_a * 60.0,
        "climb thrust total (N)": n * row["climb_thrust_N"], "climb total amps (A)": cl_a,
        "climb runtime (min)": usable / cl_a * 60.0, "est. rate of climb (m/s)": roc,
        "prop-limited max speed (m/s)": first_crossing(sv, st),
        "est. max level speed (m/s)": first_crossing(sv, [t - drag(v) for v, t in zip(sv, st)]),
        "cruise throttle (%)": thr * 100.0, "cruise batt current (A)": ib,
        "cruise endurance (min)": mins,
    }
    curve = {"label": f"{row['motor']}/{row['prop']}", "v": sv, "t": st, "drag": [drag(v) for v in sv]}
    return out, curve


def analyze_top(df, config, qprop_exe, workdir, a: Assumptions, top=10, rank_by="thrust", workers=4):
    chosen = select_top(df, top, rank_by)
    if chosen.empty:
        return pd.DataFrame(), []
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(analyze_candidate, r, config, qprop_exe, workdir, a) for _, r in chosen.iterrows()]
        res = [f.result() for f in futs]
    rows = [o for o, _ in res if o is not None]
    curves = [c for o, c in res if o is not None]
    return pd.DataFrame(rows), curves
