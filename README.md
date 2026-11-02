# SAE Aero propulsion pipeline

Chooses motor Kv and prop geometry for the SAE Aero Design 2026 Regular Class aircraft
(2 x 12" props, or 4 x 9", on a 4S 14.8 V / 2200 mAh pack) using
**PyThrust -> QMIL -> QPROP**, and answers one question first:
**can 2 motors reach the required thrust per motor, or do we need 4?**

All thrust, current and power numbers are **per motor**; the battery feeds all motors
(required C-rate = num_props x amps / Ah).

## 1. Where things must live

Put this folder inside your PyThrust fork (the "project root" - the folder that contains `pythrust/`):

```
PyThrust-main/              <- project root; run every command from here
  pythrust/                 <- PyThrust package (pip install -e . here)
  data/propellers/apc_202602/   <- PyThrust prop database (default location)
  pipeline/                 <- this package
  configs/2motor.txt, 4motor.txt
  tools/qprop1.22/qprop.exe, qmil.exe     <- QPROP (optional location, see below)
  outputs/<run name>/       <- everything generated (git-ignored)
```

QPROP and QMIL are found in this order (first hit wins):
`--qprop-exe/--qmil-exe` flag -> `QPROP_EXE`/`QMIL_EXE` environment variable ->
`pipeline_settings.json` (written by `setup`) -> auto-detect (PATH, `tools/`, `~/Downloads/qprop*`, `~/Documents/qprop*`).

## 2. First-time setup (PowerShell)

```powershell
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .                    # makes `pythrust` importable (run in the PyThrust root)
python -m pipeline setup --qprop-exe "C:\path\to\qprop.exe" --qmil-exe "C:\path\to\qmil.exe"
python -m pipeline doctor
```

`doctor` checks Python packages, finds QPROP/QMIL, **actually designs a prop with QMIL and runs QPROP on it**,
loads the PyThrust database entries, checks the outputs folder and validates the config.
Every problem is printed with its fix. Fix all `FAIL` lines before running anything.

## 3. Everyday commands

```powershell
python -m pipeline run --config configs\2motor.txt --max-amps 60 --min-thrust-lbf 9   # whole grid workflow
python -m pipeline run --config configs\4motor.txt --max-amps 60 --min-thrust-lbf 9   # separate folder, no mixing
```

Each config gets its own `outputs/<name>/` folder (override with `--name`). Individual steps:

| Command | What it does |
|---|---|
| `doctor` | check the installation |
| `setup` | remember tool / data / output locations |
| `motors --count 25` | Kv sweep -> `motors.json` (R and Io are placeholders) |
| `props --count 25` | QMIL blade family at the fixed diameter -> `props/` |
| `sweep [--motors-file motors_real.json]` | QPROP every motor x prop at takeoff and climb -> `results.csv` |
| `plot [--max-amps 60] [--link-to prop\|motor] [--heatmaps]` | scatter (PNG + clickable SVG), lines, links |
| `match` | closest real, purchasable APC prop (same diameter, nearest pitch) for each qualifying design -> `graphs/real_prop_matches.csv` |
| `analyze --top 10` | runtime, C-rate, climb rate, max speed, cruise endurance of the top feasible combos |
| `chain` | PyThrust Kv search -> QMIL -> QPROP -> rank (needs openmdao + pythrust) |
| `validate --bench data\benchmark_telemetry.csv` | chain results vs thrust-stand data |

`--max-amps` is applied when results are *read* (plot/analyze), so changing it never needs a re-sweep.

## 4. Outputs

`outputs/<name>/graphs/`: `scatter_thrust.png/.svg` (thrust in lbf vs prop pitch, coloured by Kv; open the **SVG in a browser** and click a dot),
`links.html` (clickable table of every combo that qualifies), `node_links.csv`, `qualifying_combos.csv`, `thrust_vs_prop_lines.png`.
`outputs/<name>/performance/`: `top_candidates_performance.csv`, `thrust_vs_airspeed.png`.

### About the links and real props
- The QMIL blades are aerodynamic designs and are **not purchasable**. `catalog.py` holds the real APC model list (from APC's published performance-data files);
  each design is matched to the real model **at the same diameter with the closest pitch**, with the next two closest as alternatives. `match` prints the table.
- Matching is by diameter and pitch only: chord and twist are not compared, and APC's nominal pitch is not defined exactly like our geometric pitch at 75% radius.
  A match is "the closest thing to buy and bench-test", not "same performance". To check a real prop's performance, use the PyThrust database entries (`chain`) or a thrust-stand run.
- Links are **search links** (Google, or `--vendor amazon`), not verified product pages. Motor links use a `"url"` key from the motors JSON if present, otherwise a search by Kv and cell count.
- Only 12 in and 9 in are in the catalog; for another diameter add its models to `_MODELS` in `catalog.py` (otherwise a generic search is used).

## 5. Limitations (read before presenting numbers)
- R and Io are the same for every synthetic Kv; real motors differ. Use datasheet values (`--motors-file`) for real candidates.
- No battery sag, no SAE power-limiter cap, no heating; the simulation is likely optimistic versus a thrust stand.
- The custom blade's structural strength is not checked; the airfoil polar is generic, not measured.
- Flight-time / speed estimates use *assumed* L/D (default 8) and cruise speed (default 15 m/s).
- Validation needs real bench data (`data/benchmark_telemetry.csv`); none exists until a stand is built.

## 6. Code map

| File | Role |
|---|---|
| `cli.py`, `__main__.py` | the `python -m pipeline <command>` entry point |
| `settings.py` | locates qprop/qmil/data/outputs; per-run folders (no reliance on current directory) |
| `doctor.py` | environment checks incl. end-to-end smoke test |
| `config.py`, `defaults.py`, `units.py` | config parsing, placeholder electrical constants, unit factors |
| `qprop_io.py`, `qmil_io.py` | write input files, run the executables, parse output (bare filenames, cwd set) |
| `motors.py`, `props.py`, `sweep.py` | the grid: motor axis, prop axis, QPROP sweep |
| `catalog.py` | real APC model list + closest-pitch matching |
| `results.py`, `links.py`, `propfile.py` | load results, apply `--max-amps`, prop geometry and shopping links |
| `plots.py`, `analysis.py` | graphs; flight-performance estimates |
| `search.py`, `chain.py`, `validate.py` | PyThrust stage, QMIL->QPROP->rank chain, bench comparison |

## 7. Troubleshooting
- `ERROR: Could not find qprop.exe` -> run `setup` (above) or copy QPROP into `tools\qprop1.22\`.
- `QPROP produced no result for N combinations` -> run `doctor`; usually a wrong exe or a corrupted prop file.
- `ModuleNotFoundError: pythrust` -> `pip install -e .` in the PyThrust root (only `chain`/`validate` need it).
- `No module named pipeline` -> run from the project root, not from inside `pipeline\`.
- Old results: delete `outputs\<name>\` to start clean.
