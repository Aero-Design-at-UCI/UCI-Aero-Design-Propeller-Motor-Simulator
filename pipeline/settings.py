"""
settings.py
============
The one place that knows where everything lives, so the pipeline behaves the
same on any machine and never depends on the current working directory.

Tool lookup order for qprop / qmil (first hit wins):
  1. --qprop-exe / --qmil-exe on the command line
  2. environment variable QPROP_EXE / QMIL_EXE
  3. pipeline_settings.json in the project root (written by `python -m pipeline setup`)
  4. auto-detect: PATH, <project>/tools/qprop*/, ~/Downloads/qprop*/, ~/Documents/qprop*/,
     the folder next to the project, and the project root itself
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = PROJECT_ROOT / "pipeline_settings.json"
EXE_SUFFIX = ".exe" if os.name == "nt" else ""
ENV_VARS = {"qprop": "QPROP_EXE", "qmil": "QMIL_EXE"}
DEFAULT_DATA_DIR = "data/propellers/apc_202602"


class ToolNotFound(RuntimeError):
    """qprop or qmil could not be located."""


# ----------------------------------------------------------------------
# settings file
# ----------------------------------------------------------------------
def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def save_settings(updates: dict) -> dict:
    data = load_settings()
    data.update(updates)
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


# ----------------------------------------------------------------------
# tool lookup
# ----------------------------------------------------------------------
def _autodetect(tool: str):
    exe = tool + EXE_SUFFIX
    on_path = shutil.which(tool)
    if on_path:
        yield Path(on_path)
    home = Path.home()
    bases = [PROJECT_ROOT / "tools", home / "Downloads", home / "Documents",
             PROJECT_ROOT.parent, PROJECT_ROOT]
    for base in bases:
        yield base / exe
        try:
            yield from sorted(base.glob(f"qprop*/{exe}"))
        except OSError:
            continue


def find_tool(tool: str, cli_value: str | None = None):
    """Return (path, source) for 'qprop' or 'qmil', or (None, None) if not found."""
    if cli_value:
        p = Path(cli_value).expanduser()
        return (p.resolve(), "command-line flag") if p.is_file() else (None, None)

    env_value = os.environ.get(ENV_VARS[tool])
    if env_value and Path(env_value).expanduser().is_file():
        return Path(env_value).expanduser().resolve(), f"environment variable {ENV_VARS[tool]}"

    saved = load_settings().get(f"{tool}_exe")
    if saved and Path(saved).expanduser().is_file():
        return Path(saved).expanduser().resolve(), "pipeline_settings.json"

    for candidate in _autodetect(tool):
        if candidate.is_file():
            return candidate.resolve(), "auto-detected"
    return None, None


def require_tool(tool: str, cli_value: str | None = None) -> Path:
    path, _ = find_tool(tool, cli_value)
    if path is not None:
        return path
    exe = tool + EXE_SUFFIX
    if cli_value:
        raise ToolNotFound(f"--{tool}-exe points to a file that does not exist: {cli_value}")
    raise ToolNotFound(
        f"Could not find {exe}. Fix it any ONE of these ways:\n"
        f"  1. Put QPROP in {PROJECT_ROOT / 'tools' / 'qprop1.22'} (qprop and qmil together), or\n"
        f"  2. Run: python -m pipeline setup --qprop-exe <path to {exe}> --qmil-exe <path to qmil{EXE_SUFFIX}>, or\n"
        f"  3. Set the {ENV_VARS[tool]} environment variable, or pass --{tool}-exe.\n"
        f"Then check everything with: python -m pipeline doctor"
    )


# ----------------------------------------------------------------------
# folders
# ----------------------------------------------------------------------
def _project_path(value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else PROJECT_ROOT / p


def pythrust_data_dir() -> Path:
    return _project_path(load_settings().get("pythrust_data_dir", DEFAULT_DATA_DIR))


def outputs_root() -> Path:
    return _project_path(load_settings().get("outputs_dir", "outputs"))


def default_config() -> Path:
    for p in (PROJECT_ROOT / "configs" / "2motor.txt",
              PROJECT_ROOT / "configs" / "config.txt",
              PROJECT_ROOT / "pipeline" / "config.txt"):
        if p.exists():
            return p
    return PROJECT_ROOT / "configs" / "2motor.txt"


@dataclass(frozen=True)
class RunDirs:
    """Every file one named run produces lives under outputs/<name>/."""
    name: str
    root: Path

    @property
    def motors_json(self) -> Path: return self.root / "motors.json"
    @property
    def props_dir(self) -> Path: return self.root / "props"
    @property
    def qprop_dir(self) -> Path: return self.root / "qprop_runs"
    @property
    def propgen_dir(self) -> Path: return self.root / "qmil_runs"
    @property
    def results_csv(self) -> Path: return self.root / "results.csv"
    @property
    def pivots_dir(self) -> Path: return self.root / "pivots"
    @property
    def graphs_dir(self) -> Path: return self.root / "graphs"
    @property
    def performance_dir(self) -> Path: return self.root / "performance"

    def make(self) -> "RunDirs":
        self.root.mkdir(parents=True, exist_ok=True)
        return self


def run_dirs(name: str) -> RunDirs:
    return RunDirs(name, outputs_root() / name)
