"""Load sweep results, attach prop geometry/links, and apply the current limit."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .props import prop_table
from .units import N_TO_LBF


def load_results(results_csv, props_dir=None, *, max_amps, min_thrust_lbf=0.0, vendor="google"):
    """Return the sweep with lbf columns, feasibility flags and (optionally) prop info.

    Feasible = QPROP gave a result, thrust >= 0 (not windmilling) and amps <= max_amps,
    at both takeoff and climb. `qualifies` additionally needs thrust >= min_thrust_lbf.
    """
    path = Path(results_csv)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run: python -m pipeline sweep")
    df = pd.read_csv(path)
    need = {"takeoff_thrust_N", "climb_thrust_N", "takeoff_amps", "climb_amps", "kv", "motor", "prop"}
    if need - set(df.columns):
        raise KeyError(f"{path} is missing columns {sorted(need - set(df.columns))}; "
                       f"it is from an older version - re-run: python -m pipeline sweep")

    for cond in ("takeoff", "climb"):
        df[f"{cond}_thrust_lbf"] = df[f"{cond}_thrust_N"] * N_TO_LBF
        df[f"{cond}_feasible"] = (df[f"{cond}_thrust_N"] >= 0.0) & (df[f"{cond}_amps"] <= max_amps)
    df["feasible"] = df["takeoff_feasible"] & df["climb_feasible"]
    df["qualifies"] = (df["feasible"] & (df["takeoff_thrust_lbf"] >= min_thrust_lbf)
                       & (df["climb_thrust_lbf"] >= min_thrust_lbf))

    if props_dir is not None and Path(props_dir).exists():
        info = prop_table(props_dir, vendor)
        df = df.merge(info, on="prop", how="left")
    return df
