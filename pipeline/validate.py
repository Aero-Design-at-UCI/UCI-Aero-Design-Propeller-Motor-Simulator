"""Compare the chain's simulated results with bench telemetry (thrust stand CSV).

The bench CSV must have a `kv` column and any of takeoff_thrust_N, takeoff_pelec_W,
climb_thrust_N, climb_pelec_W. Each bench row is matched to the NEAREST simulated Kv
within a tolerance (exact float equality would silently match nothing).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

METRICS = ["takeoff_thrust_N", "takeoff_pelec_W", "climb_thrust_N", "climb_pelec_W"]


def compare(sim: pd.DataFrame, bench_csv, kv_tol=10.0, pass_mape=10.0):
    bench_csv = Path(bench_csv)
    if not bench_csv.exists():
        raise FileNotFoundError(
            f"Benchmark file not found: {bench_csv}\n"
            f"It is a CSV of real thrust-stand measurements (kv + the metric columns). "
            f"Without a stand there is nothing to validate against yet.")
    bench = pd.read_csv(bench_csv)
    bench["kv"] = bench["kv"].astype(float)      # merge_asof tolerance needs float keys
    bench = bench.sort_values("kv")
    merged = pd.merge_asof(bench, sim.sort_values("kv"), on="kv", direction="nearest",
                           tolerance=kv_tol, suffixes=("_actual", "_sim"))
    cols = [m for m in METRICS if f"{m}_actual" in merged and f"{m}_sim" in merged]
    if not cols:
        raise ValueError("No shared metric columns between the bench file and the simulation: "
                         + ", ".join(METRICS))
    merged = merged.dropna(subset=[f"{m}_sim" for m in cols])
    if merged.empty:
        raise ValueError(f"No bench row is within +/-{kv_tol:g} RPM/V of a simulated Kv. "
                         f"Narrow kv_min/kv_max around your bench motors or raise num_candidates.")
    stats = []
    for m in cols:
        a, s = merged[f"{m}_actual"].to_numpy(float), merged[f"{m}_sim"].to_numpy(float)
        merged[f"{m}_err_pct"] = (s - a) / a * 100.0
        nz = a != 0
        mape = float(np.mean(np.abs((a[nz] - s[nz]) / a[nz])) * 100.0) if nz.any() else float("nan")
        stats.append({"metric": m, "rmse": float(np.sqrt(np.mean((a - s) ** 2))), "mape_pct": mape,
                      "status": "PASS" if mape <= pass_mape else f"WARNING (>{pass_mape:g}%)"})
    return merged, pd.DataFrame(stats)
