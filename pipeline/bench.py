"""Bench check: which purchasable props, on a motor you describe, reproduce what the stand measured?

You give the motor (Kv, and R / Io you are unsure of), the measured loaded voltage, and the measured
thrust / current / power. For every real APC model at your diameter we build an APPROXIMATE blade
(constant geometric pitch = the model's nominal pitch, generic chord, same airfoil polar as the rest of
the pipeline), run QPROP for each plausible motor resistance, and rank by how close the prediction is.

APPROXIMATIONS (read before trusting a number):
  * Real APC geometry is not public here; pitch comes from the model name, chord/twist are generic.
  * Motor R and Io are unknown, so the ranking is across a grid of R values, not a single answer.
  * With --measured-lbf the script finds the throttle (effective motor voltage, as a fraction of the loaded
    pack voltage) that gives that thrust, so a part-throttle step compares fairly. Without it, full voltage is used.
  * Battery sag is "in" the measured pack voltage you pass; it is not modeled separately.
  * The meter sits on the battery side, so predicted battery watts = motor input / ESC efficiency.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import qmil_io as q
from .catalog import CATALOG
from .qprop_io import run_point, solve_voltage_for_thrust, write_motor_file
from .units import IN_TO_M, N_TO_LBF

HUB_FRAC = 0.15


def _chord_over_R(x):
    """Generic thin-electric chord distribution: grows to ~0.19 R near 65% radius, tapers to the tip."""
    return np.interp(x, [0.15, 0.30, 0.65, 0.90, 1.0], [0.11, 0.16, 0.19, 0.13, 0.05])


def write_approx_prop(path, diameter_in: float, pitch_in: float, n_stations: int = 30, nblades: int = 2) -> None:
    R = diameter_in * IN_TO_M / 2.0
    lines = ["Approximate prop (constant pitch, generic chord) -- pipeline/bench.py", "",
             f" {nblades}       ! Nblades", "",
             f"   {q.CL0:.4f}  {q.CL_A:.4f}    ! CL0    CL_a",
             f"  {q.CLMIN:.4f}  {q.CLMAX:.4f}    ! CLmin  CLmax", "",
             f"   {q.CD0:.5f}  {q.CD2U:.5f}  {q.CD2L:.5f}  {q.CLCD0:.4f}    ! CD0    CD2u   CD2l  CLCD0",
             f"    {q.RE_REF:.1f}  {q.RE_EXP:.3f}            ! REref  REexp", "",
             "   1.0000  1.0000  1.0000   !  Rfac   Cfac   Bfac",
             "   0.0000  0.0000  0.0000   !  Radd   Cadd   Badd", "", "#        r            c        beta"]
    for x in np.linspace(HUB_FRAC, 1.0, n_stations):
        r = x * R
        beta = math.degrees(math.atan(pitch_in * IN_TO_M / (2.0 * math.pi * r)))
        lines.append(f"   {r:.5E}  {float(_chord_over_R(x)) * R:.5E}  {beta:.4f}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _err(pred, meas):
    return float("nan") if meas is None else (pred - meas) / meas * 100.0


def run_bench(qprop_exe, workdir, *, diameter_in, kv, rm_list, i0, volts, esc_eff=0.95,
              measured_lbf=None, measured_amps=None, measured_watts=None, blades=(2,), pitches=None):
    """pitches=None -> every catalog model at this diameter; pitches=[4.5] -> just those custom pitches.
    Each prop is tried with every blade count in `blades`."""
    if pitches:
        props = [{"name": f"{diameter_in:g}x{p:g}", "pitch_in": p, "series": "custom"} for p in pitches]
    else:
        props = [c for c in CATALOG if c["diameter_in"] == round(diameter_in)]
    if not props:
        raise ValueError(f'No APC models for a {diameter_in}" prop in catalog.py - add them to _MODELS.')
    workdir = Path(workdir)
    rows = []
    unreachable = failed = 0
    for c, nb in [(c, nb) for c in props for nb in blades]:
        pdir = workdir / f"{c['name'].replace(' ', '_')}_{nb}blade"
        pdir.mkdir(parents=True, exist_ok=True)
        pname = "approx.prop"
        write_approx_prop(pdir / pname, diameter_in, c["pitch_in"], nblades=nb)
        for rm in rm_list:
            write_motor_file(pdir / "motor.mot", {"name": "bench", "kv": kv, "rm": rm, "i0": i0})
            if measured_lbf is not None:
                # The stand was NOT at full throttle: find the effective motor voltage (throttle x pack V)
                # at which this prop makes the MEASURED thrust, then compare current and power.
                tgt = measured_lbf / N_TO_LBF
                r, _ = solve_voltage_for_thrust(qprop_exe, pdir, pname, "motor.mot", 0.0, tgt, volts,
                                                tol_N=0.02, max_iter=30)
                if r is not None and abs(r["T_N"] - tgt) > 0.03 * tgt:
                    unreachable += 1
                    continue        # cannot reach the measured thrust even at full voltage
            else:
                r = run_point(qprop_exe, pdir, pname, "motor.mot", 0.0, volts)
            if r is None:
                failed += 1
                continue
            bw = r["Pelec_W"] / esc_eff
            ba = bw / volts
            row = {"prop": c["name"], "blades": nb, "pitch_in": c["pitch_in"], "series": c["series"], "R_ohm": rm,
                   "throttle_equiv": r["Volts"] / volts, "rpm": r["rpm"], "thrust_lbf": r["T_N"] * N_TO_LBF, "thrust_N": r["T_N"],
                   "motor_amps": r["Amps"], "batt_amps": ba, "batt_watts": bw,
                   "thrust_err_pct": _err(r["T_N"] * N_TO_LBF, measured_lbf),
                   "amps_err_pct": _err(ba, measured_amps), "watts_err_pct": _err(bw, measured_watts)}
            errs = [row[k] for k in ("thrust_err_pct", "amps_err_pct", "watts_err_pct") if not math.isnan(row[k])]
            row["score_rms_err_pct"] = math.sqrt(sum(e * e for e in errs) / len(errs)) if errs else float("nan")
            rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        if unreachable and not failed:
            raise RuntimeError(f"None of the {unreachable} combinations can reach {measured_lbf} lbf even at full voltage "
                               f"({volts} V). Check Kv/volts/diameter, or the measured thrust.")
        raise RuntimeError("QPROP gave no results - run: python -m pipeline doctor")
    if unreachable:
        print(f"  note: {unreachable} prop/R combination(s) cannot reach {measured_lbf} lbf at full voltage and were dropped.")
    key = "score_rms_err_pct" if df["score_rms_err_pct"].notna().any() else "thrust_lbf"
    return df.sort_values(key, ascending=key == "score_rms_err_pct").reset_index(drop=True)