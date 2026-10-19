"""
qprop_io.py
============
Everything that talks to qprop lives here (it used to be copy-pasted into three
files): motor file writing, output parsing, running one point, and the voltage
bisection that hits a target thrust.

QPROP command line used:  qprop <prop file> <motor file> <V m/s> <rpm=0> <volts>
(rpm 0 tells QPROP to use the voltage instead). Always run with cwd set to the
folder holding the files and pass only bare file names: QPROP/QMIL are old
Fortran programs with fixed-length filename buffers.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

COLUMNS = [
    "V", "rpm", "Dbeta", "T_N", "Q_Nm", "Pshaft_W", "Volts", "Amps",
    "effmot", "effprop", "adv", "CT", "CP", "DV_ms", "eff", "Pelec_W",
    "Pprop_W", "cl_avg", "cd_avg",
]


def write_motor_file(path, motor: dict) -> None:
    """motor needs keys: name, rm (ohm), i0 (A), kv (RPM/V)."""
    text = f"""{motor['name']}
1           ! motor type
{motor['rm']:.5f}        ! R (Ohms)
{motor['i0']:.4f}        ! Io (Amps)
{motor['kv']:.1f}      ! Kv (rpm/Volt)
"""
    Path(path).write_text(text, encoding="utf-8")


def parse_qprop_output(stdout_text: str):
    """Parse the first result row of QPROP output into a dict (None if not found)."""
    lines = stdout_text.splitlines()
    for idx, line in enumerate(lines):
        if "V(m/s)" in line and "rpm" in line:
            for data_line in lines[idx + 1:]:
                stripped = data_line.strip().lstrip("#").strip()
                if not stripped:
                    continue
                parts = stripped.split()
                if len(parts) < len(COLUMNS):
                    return None
                try:
                    return dict(zip(COLUMNS, (float(p) for p in parts[:len(COLUMNS)])))
                except ValueError:
                    return None
    return None


def run_qprop(qprop_exe, cwd, prop_name, motor_name, airspeed_mps, volts, timeout=60):
    """Run one QPROP point. Returns (parsed dict or None, raw text for diagnostics)."""
    cmd = [str(Path(qprop_exe).resolve()), prop_name, motor_name, f"{airspeed_mps}", "0", f"{volts}"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd), timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if res.returncode != 0:
        return None, res.stdout + res.stderr
    return parse_qprop_output(res.stdout), res.stdout


def run_point(qprop_exe, cwd, prop_name, motor_name, airspeed_mps, volts):
    return run_qprop(qprop_exe, cwd, prop_name, motor_name, airspeed_mps, volts)[0]


def solve_voltage_for_thrust(qprop_exe, cwd, prop_name, motor_name, airspeed_mps,
                             target_thrust_N, v_max, *, v_min=0.5, tol_N=0.05, max_iter=15):
    """Bisect the motor voltage so thrust at this airspeed matches the target.

    Assumes thrust rises monotonically with voltage (true for a fixed-pitch prop in
    normal operation). Returns (best parsed result or None, last raw output).
    """
    lo, hi = v_min, v_max
    best, raw = None, ""
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        parsed, raw = run_qprop(qprop_exe, cwd, prop_name, motor_name, airspeed_mps, mid)
        if parsed is None:
            break
        best = parsed
        if abs(parsed["T_N"] - target_thrust_N) <= tol_N:
            break
        if parsed["T_N"] < target_thrust_N:
            lo = mid
        else:
            hi = mid
    return best, raw
