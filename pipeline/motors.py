"""Synthetic motor axis: a Kv sweep with placeholder R and Io.

R and Io are the SAME for every Kv (real motors differ: higher Kv usually means
lower R and higher Io). Use this to see the SHAPE of the design space, then
replace with datasheet values (motors_real.json) for the motors you can buy.
"""
from __future__ import annotations

import json
from pathlib import Path

from .defaults import DEFAULT_NO_LOAD_CURRENT_A, DEFAULT_RESISTANCE_OHM


def generate_motors(config, count=25, rm=DEFAULT_RESISTANCE_OHM, i0=DEFAULT_NO_LOAD_CURRENT_A):
    kv_min, kv_max = config["kv_min"], config["kv_max"]
    motors = []
    for i in range(count):
        kv = kv_min + (kv_max - kv_min) * (i / (count - 1) if count > 1 else 0.0)
        motors.append({"name": f"Kv{kv:.0f}", "kv": round(kv, 1), "rm": rm, "i0": i0})
    return motors


def save_motors(motors, path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(motors, indent=2), encoding="utf-8")


def load_motors(path):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Motors file not found: {p}  (create it with: python -m pipeline motors)")
    motors = json.loads(p.read_text(encoding="utf-8"))
    for m in motors:
        for k in ("name", "kv", "rm", "i0"):
            if k not in m:
                raise KeyError(f"motor entry {m} is missing '{k}'")
    return motors
