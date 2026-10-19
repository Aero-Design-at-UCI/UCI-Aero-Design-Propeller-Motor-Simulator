"""Motor x prop grid: run QPROP at takeoff and climb for every pair.

Raw physics only. The current limit is NOT applied here - it is applied when the
results are read (results.py), so changing --max-amps never needs a re-sweep.
All thrust/current/power values are PER MOTOR.
"""
from __future__ import annotations

import concurrent.futures as cf
from pathlib import Path

import numpy as np
import pandas as pd

from .motors import load_motors
from .qprop_io import run_point, write_motor_file

NAN = float("nan")


def combo_dir(workdir, motor_name: str, prop_stem: str) -> Path:
    return Path(workdir) / f"{motor_name}_x_{prop_stem}".replace(" ", "_")


def _point_fields(prefix, parsed):
    if parsed is None:
        return {f"{prefix}_{k}": NAN for k in ("thrust_N", "pelec_W", "pshaft_W", "amps", "rpm", "eff_pct")}
    pe, ps = parsed["Pelec_W"], parsed["Pshaft_W"]
    return {
        f"{prefix}_thrust_N": parsed["T_N"], f"{prefix}_pelec_W": pe, f"{prefix}_pshaft_W": ps,
        f"{prefix}_amps": parsed["Amps"], f"{prefix}_rpm": parsed["rpm"],
        f"{prefix}_eff_pct": (ps / pe * 100.0) if pe > 0 else NAN,
    }


def run_combo(motor, prop_path, qprop_exe, workdir, volts, v_takeoff, v_climb):
    d = combo_dir(workdir, motor["name"], prop_path.stem)
    d.mkdir(parents=True, exist_ok=True)
    write_motor_file(d / "motor.mot", motor)
    (d / prop_path.name).write_bytes(prop_path.read_bytes())   # ALWAYS refresh: no stale props
    to = run_point(qprop_exe, d, prop_path.name, "motor.mot", v_takeoff, volts)
    cl = run_point(qprop_exe, d, prop_path.name, "motor.mot", v_climb, volts)
    return {"motor": motor["name"], "prop": prop_path.stem, "kv": motor["kv"],
            **_point_fields("takeoff", to), **_point_fields("climb", cl)}


def run_sweep(motors_file, props_dir, qprop_exe, config, workdir, output_csv, workers=None):
    motors = load_motors(motors_file)
    prop_paths = sorted(Path(props_dir).glob("*.prop"))
    if not prop_paths:
        raise FileNotFoundError(f"No .prop files in {props_dir}  (create them with: python -m pipeline props)")
    total = len(motors) * len(prop_paths)
    print(f"Sweeping {len(motors)} motors x {len(prop_paths)} props = {total} combinations "
          f"at {config['voltage_v']:g} V ...")

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(run_combo, m, p, qprop_exe, workdir, config["voltage_v"],
                          config["takeoff_speed_mps"], config["climb_speed_mps"])
                for m in motors for p in prop_paths]
        rows = [f.result() for f in cf.as_completed(futs)]

    df = pd.DataFrame(rows).sort_values(["kv", "prop"]).reset_index(drop=True)
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)

    failed = int(df[["takeoff_thrust_N", "climb_thrust_N"]].isna().any(axis=1).sum())
    print(f"Saved {len(df)} rows to {output_csv}")
    if failed:
        print(f"  WARNING: QPROP produced no result for {failed}/{len(df)} combinations "
              f"(stored as blank). Run 'python -m pipeline doctor' to test the QPROP install.")
    return df


def write_pivots(df: pd.DataFrame, out_dir) -> None:
    """Motor-by-prop matrices (CSV) for the quantities that do not depend on --max-amps."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for col in ("takeoff_thrust_N", "climb_thrust_N", "takeoff_amps", "climb_amps",
                "takeoff_eff_pct", "climb_eff_pct"):
        df.pivot(index="motor", columns="prop", values=col).to_csv(out_dir / f"{col}.csv")
