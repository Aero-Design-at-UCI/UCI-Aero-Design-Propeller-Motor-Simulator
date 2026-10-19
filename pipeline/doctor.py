"""`python -m pipeline doctor`: check that this machine is set up correctly.

Every check prints OK / WARN / FAIL with the exact fix. The QPROP/QMIL check is an
END-TO-END smoke test (design a prop with qmil, run qprop on it), not just "file exists".
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

from . import settings
from .config import load_validated
from .motors import generate_motors
from .qmil_io import design_prop
from .qprop_io import run_qprop, write_motor_file

_results: list[str] = []


def _say(level: str, msg: str, fix: str = "") -> None:
    _results.append(level)
    print(f"[{level:^4}] {msg}")
    if fix and level != "OK":
        for line in fix.splitlines():
            print(f"         -> {line}")


def check_python():
    v = sys.version_info
    if v < (3, 9):
        _say("FAIL", f"Python {v.major}.{v.minor} is too old", "Install Python 3.9 or newer.")
    else:
        _say("OK", f"Python {v.major}.{v.minor}.{v.micro} ({sys.executable})")


def check_packages():
    for mod, needed in (("numpy", True), ("pandas", True), ("matplotlib", True), ("scipy", True),
                        ("openmdao", False), ("pythrust", False)):
        try:
            m = importlib.import_module(mod)
            where = getattr(m, "__file__", "") or ""
            _say("OK", f"{mod} importable" + (f"  ({Path(where).parent})" if mod == "pythrust" and where else ""))
        except Exception as exc:
            if needed:
                _say("FAIL", f"{mod} missing ({type(exc).__name__})", f"pip install {mod}   (or: pip install -r requirements.txt)")
            else:
                hint = ("pip install openmdao" if mod == "openmdao" else
                        "From your PyThrust folder run: pip install -e .   (only needed for the 'chain' and 'validate' commands)")
                _say("WARN", f"{mod} not importable - the 'chain'/'validate' commands will not work", hint)


def check_tools(qprop_cli, qmil_cli):
    found = {}
    for tool, cli in (("qprop", qprop_cli), ("qmil", qmil_cli)):
        path, src = settings.find_tool(tool, cli)
        if path is None:
            _say("FAIL", f"{tool}{settings.EXE_SUFFIX} not found",
                 f"Put it in {settings.PROJECT_ROOT / 'tools' / 'qprop1.22'}, or run:\n"
                 f"python -m pipeline setup --qprop-exe <full path to qprop{settings.EXE_SUFFIX}> "
                 f"--qmil-exe <full path to qmil{settings.EXE_SUFFIX}>")
        else:
            _say("OK", f"{tool}: {path}  [{src}]")
            if len(str(path)) > 200:
                _say("WARN", "tool path is very long (old Fortran code truncates long names)")
            found[tool] = path
    return found


def smoke_test(found):
    if len(found) < 2:
        _say("WARN", "skipping the qmil -> qprop smoke test (tool(s) missing)")
        return
    with tempfile.TemporaryDirectory(prefix="pl") as tmp:
        tmp = Path(tmp)
        prop, text = design_prop(found["qmil"], tmp, "t0", diameter_in=12, design_speed_mps=1.0,
                                 rpm=6000, thrust_n=20, label="doctor smoke test")
        if prop is None:
            _say("FAIL", "qmil ran but produced no .prop", f"qmil output tail: {text.strip()[-300:]}")
            return
        _say("OK", "qmil designed a test prop")
        write_motor_file(tmp / "motor.mot", {"name": "t", "kv": 800, "rm": 0.0258, "i0": 1.3})
        parsed, raw = run_qprop(found["qprop"], tmp, "t0.prop", "motor.mot", 0.0, 14.8)
        if parsed is None:
            _say("FAIL", "qprop produced no parsable result", f"qprop output tail: {raw.strip()[-300:]}")
        elif parsed["T_N"] <= 0:
            _say("WARN", f"qprop ran but thrust is {parsed['T_N']:.2f} N - unexpected")
        else:
            _say("OK", f"qprop smoke test: 800 Kv, 14.8 V, static -> {parsed['T_N']:.1f} N, {parsed['Amps']:.1f} A")


def check_pythrust_data():
    d = settings.pythrust_data_dir()
    if not d.exists():
        _say("WARN", f"PyThrust data dir not found: {d}",
             "Only the chain/validate commands need it. Run from your PyThrust folder, or:\n"
             "python -m pipeline setup --pythrust-data-dir <folder containing the APC csv/json files>")
        return
    _say("OK", f"PyThrust data dir: {d}")
    try:
        from .search import DIAMETER_TO_PROP_ENTRY, load_prop_entry
        for dia in DIAMETER_TO_PROP_ENTRY:
            load_prop_entry(d, dia)
        _say("OK", f"database entries load: {', '.join(DIAMETER_TO_PROP_ENTRY.values())}")
    except ImportError:
        _say("WARN", "cannot test database entries (pythrust not importable)")
    except Exception as exc:
        _say("FAIL", f"database entry failed to load: {exc}")


def check_outputs():
    root = settings.outputs_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write_test"
        probe.write_text("x"); probe.unlink()
        _say("OK", f"outputs folder writable: {root}")
        if os.name == "nt" and len(str(root)) > 120:
            _say("WARN", "outputs path is long; Windows paths over 260 chars break", "Move the project closer to C:\\ or run 'setup --outputs-dir C:\\sae_out'")
    except OSError as exc:
        _say("FAIL", f"cannot write to {root}: {exc}")


def check_config(config_path):
    try:
        cfg = load_validated(config_path)
        generate_motors(cfg, 3)
        _say("OK", f"config valid: {config_path}")
    except Exception as exc:
        _say("FAIL", f"config problem ({config_path}): {exc}")


def run_doctor(config_path, qprop_cli=None, qmil_cli=None) -> int:
    _results.clear()
    print(f"Project root: {settings.PROJECT_ROOT}\n")
    check_python(); check_packages()
    found = check_tools(qprop_cli, qmil_cli)
    smoke_test(found)
    check_pythrust_data(); check_outputs(); check_config(config_path)
    fails, warns = _results.count("FAIL"), _results.count("WARN")
    print(f"\n{fails} failure(s), {warns} warning(s).")
    print("Ready for: motors, props, sweep, plot, analyze, run." if not fails else "Fix the FAIL lines above, then re-run doctor.")
    return 1 if fails else 0
