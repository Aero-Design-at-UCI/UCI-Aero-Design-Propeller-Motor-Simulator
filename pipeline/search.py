"""Stage 1: PyThrust Kv search (only module that needs openmdao + pythrust).

Imports are lazy so every other command works without those packages installed.
"""
from __future__ import annotations

from pathlib import Path

from .defaults import (DEFAULT_CURRENT_MAX_A, DEFAULT_NO_LOAD_CURRENT_A, DEFAULT_RESISTANCE_OHM,
                       DEFAULT_RHO, DEFAULT_SYSTEM_RESISTANCE_OHM)
from .units import IN_TO_M

# PyThrust database entry used as the aerodynamic stand-in, keyed by diameter (in).
DIAMETER_TO_PROP_ENTRY = {12: "APC_12x8E", 9: "APC_9x6E"}


def load_prop_entry(data_dir, diameter_in):
    from pythrust.propellers import PropellerDatabase
    name = DIAMETER_TO_PROP_ENTRY.get(int(diameter_in))
    if name is None:
        raise ValueError(f'No PyThrust database entry for a {diameter_in}" prop. '
                         f"Add one to DIAMETER_TO_PROP_ENTRY in pipeline/search.py.")
    if not Path(data_dir).exists():
        raise FileNotFoundError(f"PyThrust data directory not found: {data_dir}\n"
                                f"Set it with: python -m pipeline setup --pythrust-data-dir <folder>")
    db = PropellerDatabase()
    db.load(Path(data_dir), strict=False)
    entry = db.get(name)
    if entry is None:
        raise ValueError(f"Propeller '{name}' not found in {data_dir}.")
    return entry


def _solve_point(prop_entry, kv, diameter_m, voltage_v, airspeed, target_n, max_amps):
    import openmdao.api as om
    from pythrust.openmdao import PropulsionComponent
    from scipy.optimize import brentq

    prob = om.Problem(reports=False)
    prob.model.add_subsystem("prop", PropulsionComponent(prop_entry=prop_entry), promotes=["*"])
    prob.setup()
    for k, v in (("kv_rpm_per_v", kv), ("diameter_m", diameter_m),
                 ("resistance_ohm", DEFAULT_RESISTANCE_OHM), ("no_load_current_a", DEFAULT_NO_LOAD_CURRENT_A),
                 ("current_max_a", max_amps), ("voltage_v", voltage_v),
                 ("resistance_system_ohm", DEFAULT_SYSTEM_RESISTANCE_OHM), ("rho", DEFAULT_RHO),
                 ("airspeed_mps", airspeed)):
        prob.set_val(k, v)

    def residual(throttle):
        prob.set_val("throttle", throttle)
        prob.run_model()
        return target_n - float(prob.get_val("thrust_n")[0])

    try:
        if residual(1.0) > 0:
            return {"feasible": False, "error": "Insufficient thrust at max throttle"}
        thr = brentq(residual, 0.05, 1.0, xtol=1e-4)
        prob.set_val("throttle", thr); prob.run_model()
        got = float(prob.get_val("thrust_n")[0])
        return {"feasible": abs(got - target_n) <= 0.02 * max(target_n, 1.0) + 0.05,
                "throttle": float(thr), "rpm": float(prob.get_val("rpm")[0]),
                "power_w": float(prob.get_val("battery_power_w")[0]),
                "current_a": float(prob.get_val("motor_current_a")[0]), "thrust_n": got}
    except Exception as exc:                      # PyThrust/OpenMDAO raise many types
        return {"feasible": False, "error": str(exc)}


def search_kv_candidates(config, data_dir, max_amps=DEFAULT_CURRENT_MAX_A):
    d_in = config["prop_diameter_in"]
    entry = load_prop_entry(data_dir, d_in)
    n_top = int(config.get("num_candidates", 10))
    n_sweep = max(n_top * 3, 15)
    out = []
    for i in range(n_sweep):
        kv = config["kv_min"] + (config["kv_max"] - config["kv_min"]) * i / (n_sweep - 1)
        to = _solve_point(entry, kv, d_in * IN_TO_M, config["voltage_v"], config["takeoff_speed_mps"],
                          config["takeoff_thrust_per_prop_N"], max_amps)
        if not to["feasible"]:
            continue
        cl = _solve_point(entry, kv, d_in * IN_TO_M, config["voltage_v"], config["climb_speed_mps"],
                          config["climb_thrust_per_prop_N"], max_amps)
        if not cl["feasible"]:
            continue
        out.append({"kv": kv, "diameter_in": d_in,
                    "takeoff_throttle": to["throttle"], "takeoff_rpm": to["rpm"],
                    "takeoff_power_w": to["power_w"], "takeoff_current_a": to["current_a"],
                    "climb_throttle": cl["throttle"], "climb_rpm": cl["rpm"],
                    "climb_power_w": cl["power_w"], "climb_current_a": cl["current_a"]})
    out.sort(key=lambda c: c["takeoff_power_w"])
    return out[:n_top]
