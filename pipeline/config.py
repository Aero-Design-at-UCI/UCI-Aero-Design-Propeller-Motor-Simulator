"""Parses a mission config (key=value text file) into a dict with numeric types."""

from pathlib import Path

INT_FIELDS = {
    "num_props",
    "num_full_bottles",
    "num_empty_bottles",
    "num_candidates",
}

REQUIRED_KEYS = [
    "prop_diameter_in", "num_props", "voltage_v", "battery_capacity_mah",
    "takeoff_speed_mps", "takeoff_thrust_per_prop_N",
    "climb_speed_mps", "climb_thrust_per_prop_N",
    "kv_min", "kv_max", "num_candidates",
]


def load_config(path):
    """Read a key=value config file into a dict of numbers."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    config = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key in INT_FIELDS:
            config[key] = int(float(value))
        else:
            try:
                config[key] = float(value)
            except ValueError:
                config[key] = value
    return config


def validate_config(config):
    missing = [k for k in REQUIRED_KEYS if k not in config]
    if missing:
        raise KeyError("config is missing required field(s): " + ", ".join(missing))


def load_validated(path):
    config = load_config(path)
    validate_config(config)
    return config
