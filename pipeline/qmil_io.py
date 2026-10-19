"""QMIL: write a .mil design file and run qmil to get a QPROP-ready .prop.

The airfoil polar below is a generic, calibrated prop-airfoil model (CD0 +18%,
CL0 -7% vs the cam6x3 sample). It is NOT measured data for a real blade, so a
QMIL-designed prop is an aerodynamic design only - you cannot buy it.

QMIL and QPROP are old Fortran programs with fixed-length filename buffers, so
we always run them with cwd = a short per-prop folder and pass BARE filenames.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .units import IN_TO_M

NBLADES = 2
CL0, CL_A, CLMIN, CLMAX = 0.4650, 5.8, -0.3, 1.2
CD0, CD2U, CD2L, CLCD0 = 0.03304, 0.050, 0.020, 0.5
RE_REF, RE_EXP = 70000.0, -0.7
XIDES = [0.3, 0.6, 1.0]
CLDES = [0.5115, 0.4650, 0.4185]
HUB_RADIUS_M = 0.0127
DESIGN_SPEED_FLOOR_MPS = 1.0   # QMIL cannot design at exactly V = 0
NOUT = 30


def design_speed_for(config) -> float:
    v = config["takeoff_speed_mps"]
    return v if v > 0 else DESIGN_SPEED_FLOOR_MPS


def write_mil(path, *, diameter_in, design_speed_mps, rpm, thrust_n, label) -> None:
    tip_radius_m = diameter_in * IN_TO_M / 2.0
    xs = "  ".join(f"{x:.3f}" for x in XIDES)
    cs = "  ".join(f"{c:.3f}" for c in CLDES)
    text = f"""{label}

 {NBLADES}       ! Nblades

 {CL0:.4f}  {CL_A:.4f}    ! CL0    CL_a
 {CLMIN:.4f}  {CLMAX:.4f}    ! CLmin  CLmax

 {CD0:.5f}   {CD2U:.3f}  {CD2L:.3f}  {CLCD0:.2f}  ! CD0    CD2u   CD2l  CLCD0
 {RE_REF:.1f} {RE_EXP:.3f}               ! REref  REexp

  {xs}   ! XIdes
  {cs}   ! CLdes

  {HUB_RADIUS_M:.4f}    !  hub radius(m)
  {tip_radius_m:.4f}    !  tip radius(m)
  {design_speed_mps:.3f}    !  speed(m/s)
  {rpm:.1f}   !  rpm

  {thrust_n:.4f}      !  Thrust(N)   ( 0 if power  specified )
  0.0    !  Power(W)    ( 0 if thrust specified )

 0   0.2   ! Ldes    KQdes

  {NOUT}       ! Nout
"""
    Path(path).write_text(text, encoding="utf-8")


def run_qmil(qmil_exe, cwd, mil_name: str, prop_name: str, timeout=60):
    """Run qmil in cwd. Returns (ok, text). ok means exit 0 AND the .prop exists."""
    cmd = [str(Path(qmil_exe).resolve()), mil_name, prop_name]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd), timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    ok = res.returncode == 0 and (Path(cwd) / prop_name).exists()
    return ok, res.stdout + res.stderr


def design_prop(qmil_exe, cand_dir, stem, *, diameter_in, design_speed_mps, rpm, thrust_n, label):
    """Write <stem>.mil in cand_dir, run qmil, return (path to .prop or None, text)."""
    cand_dir = Path(cand_dir)
    cand_dir.mkdir(parents=True, exist_ok=True)
    mil, prop = f"{stem}.mil", f"{stem}.prop"
    stale = cand_dir / prop
    if stale.exists():
        stale.unlink()          # never mistake an old file for a fresh result
    write_mil(cand_dir / mil, diameter_in=diameter_in, design_speed_mps=design_speed_mps,
              rpm=rpm, thrust_n=thrust_n, label=label)
    ok, text = run_qmil(qmil_exe, cand_dir, mil, prop)
    return (cand_dir / prop if ok else None), text
