"""Command line: python -m pipeline <command> [options]   (run from the project root)

  doctor    check python packages, qprop/qmil, PyThrust data, config
  setup     remember where qprop/qmil/PyThrust data live (pipeline_settings.json)
  motors    generate the Kv sweep (outputs/<name>/motors.json)
  props     design the QMIL prop family (outputs/<name>/props/)
  sweep     QPROP every motor x prop at takeoff + climb
  plot      scatter (PNG + clickable SVG), lines, heatmaps, links.html, qualifying CSV
  match     closest real (purchasable) APC props for the qualifying designs
  bench     which real props reproduce a thrust-stand measurement (motor Kv/R/Io, loaded V)
  analyze   flight-performance estimates for the top feasible combos
  run       motors -> props -> sweep -> plot -> analyze in one go
  chain     PyThrust -> QMIL -> QPROP -> rank (needs openmdao + pythrust)
  validate  chain results vs a bench-telemetry CSV
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import settings
from .config import load_validated
from .defaults import DEFAULT_CURRENT_MAX_A


def _common(p):
    p.add_argument("--config", help="mission config (default: configs/2motor.txt)")
    p.add_argument("--name", help="run name -> outputs/<name>/ (default: the config file's name)")


def _limits(p):
    p.add_argument("--max-amps", type=float, default=DEFAULT_CURRENT_MAX_A,
                   help=f"per-motor current limit in A (default {DEFAULT_CURRENT_MAX_A:g}); applied when reading results")
    p.add_argument("--min-thrust-lbf", type=float, default=9.0, help="required thrust per motor, lbf (default 9)")


def _tools(p):
    p.add_argument("--qprop-exe"); p.add_argument("--qmil-exe")


def build_parser():
    ap = argparse.ArgumentParser(prog="python -m pipeline", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("doctor", help="check the installation"); _common(p); _tools(p)
    p = sub.add_parser("setup", help="remember tool locations"); _tools(p)
    p.add_argument("--pythrust-data-dir"); p.add_argument("--outputs-dir")

    p = sub.add_parser("motors"); _common(p); p.add_argument("--count", type=int, default=25)
    p = sub.add_parser("props"); _common(p); _tools(p)
    p.add_argument("--count", type=int, default=25); p.add_argument("--design-rpm", type=float, default=6000.0)
    p = sub.add_parser("sweep"); _common(p); _tools(p)
    p.add_argument("--motors-file", help="default outputs/<name>/motors.json (e.g. motors_real.json)")
    p.add_argument("--props-dir", help="default outputs/<name>/props")

    p = sub.add_parser("plot"); _common(p); _limits(p)
    p.add_argument("--link-to", choices=["prop", "motor"], default="prop", help="what a dot links to")
    p.add_argument("--vendor", choices=["google", "amazon"], default="google")
    p.add_argument("--cells", type=int, default=4, help="battery cells for motor search links")
    p.add_argument("--heatmaps", action="store_true", help="also write heatmaps")
    p.add_argument("--motors-file")

    p = sub.add_parser("match", help="closest real APC props for the qualifying designs"); _common(p); _limits(p)
    p.add_argument("--vendor", choices=["google", "amazon"], default="google")
    p.add_argument("--all-props", action="store_true", help="match every designed prop, not just qualifying ones")

    p = sub.add_parser("bench", help="which real props reproduce your thrust-stand measurement?"); _tools(p)
    p.add_argument("--diameter", type=float, default=9.0, help="prop diameter in inches")
    p.add_argument("--kv", type=float, required=True, help="motor Kv (RPM/V)")
    p.add_argument("--rm", default="0.015,0.025,0.04,0.06", help="comma list of motor resistances to try (ohm)")
    p.add_argument("--i0", type=float, default=1.5, help="no-load current (A)")
    p.add_argument("--volts", type=float, required=True, help="MEASURED loaded battery voltage (V)")
    p.add_argument("--esc-eff", type=float, default=0.95)
    p.add_argument("--measured-lbf", type=float); p.add_argument("--measured-amps", type=float)
    p.add_argument("--measured-watts", type=float)
    p.add_argument("--blades", default="2", help="blade counts to try, e.g. 2,3")
    p.add_argument("--pitch", help="test only these pitches (in), e.g. 4.5 or 4.5,5 - instead of every catalog model")
    p.add_argument("--top", type=int, default=12); p.add_argument("--name", default="bench")

    p = sub.add_parser("analyze"); _common(p); _tools(p); _limits(p)
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--rank-by", choices=["thrust", "current", "efficiency"], default="thrust")
    p.add_argument("--ld-ratio", type=float, default=8.0); p.add_argument("--cruise-speed", type=float, default=15.0)
    p.add_argument("--usable-fraction", type=float, default=0.8); p.add_argument("--esc-efficiency", type=float, default=0.95)
    p.add_argument("--max-speed", type=float, default=40.0); p.add_argument("--speed-step", type=float, default=2.0)

    p = sub.add_parser("run", help="motors, props, sweep, plot, analyze"); _common(p); _tools(p); _limits(p)
    p.add_argument("--count", type=int, default=25); p.add_argument("--top", type=int, default=10)
    p.add_argument("--link-to", choices=["prop", "motor"], default="prop")

    p = sub.add_parser("chain"); _common(p); _tools(p); _limits(p)
    p = sub.add_parser("validate"); _common(p); _tools(p); _limits(p)
    p.add_argument("--bench", help="bench CSV (default data/benchmark_telemetry.csv)")
    p.add_argument("--kv-tol", type=float, default=10.0)
    return ap


def _ctx(args):
    cfg_path = Path(args.config) if getattr(args, "config", None) else settings.default_config()
    name = getattr(args, "name", None) or cfg_path.stem
    return cfg_path, name, settings.run_dirs(name)


def _tool(args, tool):
    return settings.require_tool(tool, getattr(args, f"{tool}_exe", None))


def cmd_setup(args):
    updates = {}
    for tool in ("qprop", "qmil"):
        v = getattr(args, f"{tool}_exe")
        if v:
            path, _ = settings.find_tool(tool, v)
            if path is None:
                sys.exit(f"{v} is not a file.")
            updates[f"{tool}_exe"] = str(path)
    if args.pythrust_data_dir:
        updates["pythrust_data_dir"] = args.pythrust_data_dir
    if args.outputs_dir:
        updates["outputs_dir"] = args.outputs_dir
    if updates:
        settings.save_settings(updates)
        print(f"Saved to {settings.SETTINGS_FILE}:")
        for k, v in updates.items():
            print(f"  {k} = {v}")
    else:
        print("Nothing to save. Pass --qprop-exe / --qmil-exe / --pythrust-data-dir / --outputs-dir.")
    from .doctor import run_doctor
    return run_doctor(settings.default_config())


def do_motors(args, cfg, dirs):
    from .motors import generate_motors, save_motors
    dirs.make()
    motors = generate_motors(cfg, args.count)
    save_motors(motors, dirs.motors_json)
    print(f"Wrote {len(motors)} motors to {dirs.motors_json}")


def do_props(args, cfg, dirs):
    from .props import generate_props
    dirs.make()
    n = generate_props(cfg, _tool(args, "qmil"), args.count, dirs.props_dir, dirs.propgen_dir,
                       getattr(args, "design_rpm", 6000.0))
    if n == 0:
        sys.exit("QMIL produced no props - run: python -m pipeline doctor")


def do_sweep(args, cfg, dirs):
    from .sweep import run_sweep, write_pivots
    dirs.make()
    df = run_sweep(getattr(args, "motors_file", None) or dirs.motors_json,
                   getattr(args, "props_dir", None) or dirs.props_dir,
                   _tool(args, "qprop"), cfg, dirs.qprop_dir, dirs.results_csv)
    write_pivots(df, dirs.pivots_dir)


def _load(args, dirs):
    from .results import load_results
    return load_results(dirs.results_csv, dirs.props_dir, max_amps=args.max_amps,
                        min_thrust_lbf=args.min_thrust_lbf, vendor=getattr(args, "vendor", "google"))


def do_plot(args, cfg, dirs):
    from . import plots
    from .links import load_motor_urls
    df = _load(args, dirs)
    df = plots.add_link_columns(df, args.link_to, getattr(args, "vendor", "google"),
                                load_motor_urls(getattr(args, "motors_file", None) or dirs.motors_json),
                                getattr(args, "cells", 4))
    g = dirs.graphs_dir; g.mkdir(parents=True, exist_ok=True)
    plots.plot_scatter(df, args.min_thrust_lbf, args.max_amps, g / "scatter_thrust.png", g / "scatter_thrust.svg")
    plots.plot_lines(df, args.min_thrust_lbf, g / "thrust_vs_prop_lines.png")
    cols = [c for c in ("motor", "kv", "prop", "prop_label", "pitch_in", "takeoff_thrust_lbf", "climb_thrust_lbf",
                        "takeoff_amps", "climb_amps", "feasible", "qualifies", "prop_url", "motor_url", "node_url") if c in df]
    df[cols].to_csv(g / "node_links.csv", index=False)
    df[df["qualifies"]].sort_values("kv")[cols].to_csv(g / "qualifying_combos.csv", index=False)
    plots.write_links_html(df, g / "links.html", args.min_thrust_lbf, args.max_amps)
    if args.heatmaps:
        plots.plot_heatmaps(df, g / "heatmaps")
    nq = int(df["qualifies"].sum())
    print(f"{nq}/{len(df)} combos reach {args.min_thrust_lbf:g} lbf per motor at takeoff and climb within {args.max_amps:g} A.")
    print(f"Wrote scatter_thrust.png/.svg, thrust_vs_prop_lines.png, node_links.csv, qualifying_combos.csv, links.html in {g}")
    if "pitch_in" not in df.columns:
        print("  note: no prop files found, so the scatter x axis is the prop index, not pitch.")


def do_match(args, cfg, dirs):
    import pandas as pd
    df = _load(args, dirs)
    if "prop_label" not in df.columns:
        sys.exit(f"No prop files in {dirs.props_dir} - run: python -m pipeline props")
    use = df if args.all_props else df[df["qualifies"]]
    if use.empty:
        sys.exit("No qualifying combos. Loosen --max-amps / --min-thrust-lbf, or use --all-props.")
    g = (use.groupby("prop").agg(combos=("motor", "count"), best_takeoff_lbf=("takeoff_thrust_lbf", "max"),
                                  lowest_kv=("kv", "min"), highest_kv=("kv", "max"),
                                  designed_pitch_in=("pitch_in", "first"), diameter_in=("diameter_in", "first"),
                                  closest_real_prop=("prop_label", "first"), real_pitch_in=("real_pitch_in", "first"),
                                  pitch_gap_in=("pitch_gap_in", "first"), series=("real_series", "first"),
                                  other_options=("alternatives", "first"), buy_link=("prop_url", "first"))
         .reset_index().sort_values("designed_pitch_in"))
    out = dirs.graphs_dir; out.mkdir(parents=True, exist_ok=True)
    g.to_csv(out / "real_prop_matches.csv", index=False)
    pd.set_option("display.width", 220); pd.set_option("display.max_columns", None)
    print(g.drop(columns=["buy_link"]).round(2).to_string(index=False))
    far = g[g["pitch_gap_in"] > 0.5]
    if len(far):
        print(f"\nNote: {len(far)} design(s) have no real prop within 0.5 in of pitch - the match is loose.")
    print("\nMatching is by diameter and pitch only (chord/twist not compared); verify on a thrust stand.")
    print(f"Wrote {out / 'real_prop_matches.csv'}")


def cmd_bench(args):
    from .bench import run_bench
    import pandas as pd
    dirs = settings.run_dirs(args.name).make()
    rms = [float(x) for x in args.rm.split(",")]
    df = run_bench(_tool(args, "qprop"), dirs.root / "bench_runs", diameter_in=args.diameter, kv=args.kv,
                   rm_list=rms, i0=args.i0, volts=args.volts, esc_eff=args.esc_eff,
                   measured_lbf=args.measured_lbf, measured_amps=args.measured_amps,
                   measured_watts=args.measured_watts,
                   blades=[int(b) for b in args.blades.split(",")],
                   pitches=[float(x) for x in args.pitch.split(",")] if args.pitch else None)
    df.to_csv(dirs.root / "bench_candidates.csv", index=False)
    pd.set_option("display.width", 220); pd.set_option("display.max_columns", None)
    print(f"Motor {args.kv:g} Kv, {args.volts:g} V loaded, {args.diameter:g} in props; R tried: {rms}, Io {args.i0:g} A")
    print(df.head(args.top).round(2).to_string(index=False))
    print("\nApproximate blades (nominal pitch, generic chord); R and Io are guesses. Use this to see which props "
          "are PLAUSIBLE, then confirm on the stand. Wrote " + str(dirs.root / "bench_candidates.csv"))


def do_analyze(args, cfg, dirs):
    from . import plots
    from .analysis import Assumptions, analyze_top
    import pandas as pd
    df = _load(args, dirs)
    a = Assumptions(args.ld_ratio, args.cruise_speed, args.usable_fraction, args.esc_efficiency,
                    args.max_speed, args.speed_step)
    res, curves = analyze_top(df, cfg, _tool(args, "qprop"), dirs.qprop_dir, a, args.top, args.rank_by)
    if res.empty:
        sys.exit(f"No combo passes <= {args.max_amps:g} A and >= {args.min_thrust_lbf:g} lbf. "
                 f"Loosen --max-amps or --min-thrust-lbf.")
    out = dirs.performance_dir; out.mkdir(parents=True, exist_ok=True)
    res.to_csv(out / "top_candidates_performance.csv", index=False)
    plots.plot_thrust_curves(curves, out / "thrust_vs_airspeed.png", a)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", None)
    print(res.drop(columns=["prop_url"], errors="ignore").round(2).to_string(index=False))
    print("\nPer-motor columns are for ONE motor; battery columns are for the whole aircraft.")
    print("Not modeled: SAE power limiter, battery sag, heating, real airframe drag. L/D and cruise speed are assumptions.")
    print(f"Wrote {out}")


def do_chain(args, cfg, dirs):
    from .chain import run_chain
    dirs.make()
    df = run_chain(cfg, qmil_exe=_tool(args, "qmil"), qprop_exe=_tool(args, "qprop"),
                   data_dir=settings.pythrust_data_dir(), workdir=dirs.root / "chain_runs", max_amps=args.max_amps)
    out = dirs.root / "chain_results.csv"
    df.to_csv(out, index=False)
    print(df.round(2).drop(columns=["prop_file"]).to_string(index=False))
    print(f"\nSaved {out}")
    return df


def do_validate(args, cfg, dirs):
    from .validate import compare
    df = do_chain(args, cfg, dirs)
    bench = args.bench or settings.PROJECT_ROOT / "data" / "benchmark_telemetry.csv"
    merged, stats = compare(df, bench, args.kv_tol)
    print(merged.round(3).to_string(index=False)); print(stats.to_string(index=False))
    merged.to_csv(dirs.root / "validation.csv", index=False)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "setup":
            return cmd_setup(args)
        if args.cmd == "bench":
            cmd_bench(args); return 0
        cfg_path, name, dirs = _ctx(args)
        if args.cmd == "doctor":
            from .doctor import run_doctor
            return run_doctor(cfg_path, args.qprop_exe, args.qmil_exe)
        cfg = load_validated(cfg_path)
        print(f"Config: {cfg_path}   Run: outputs/{name}/")
        if args.cmd == "run":
            args.motors_file = args.props_dir = None; args.design_rpm = 6000.0
            args.vendor = "google"; args.cells = 4; args.heatmaps = False
            args.rank_by = "thrust"; args.ld_ratio = 8.0; args.cruise_speed = 15.0
            args.usable_fraction = 0.8; args.esc_efficiency = 0.95; args.max_speed = 40.0; args.speed_step = 2.0
            for fn in (do_motors, do_props, do_sweep, do_plot, do_analyze):
                fn(args, cfg, dirs)
        else:
            {"motors": do_motors, "props": do_props, "sweep": do_sweep, "plot": do_plot,
             "analyze": do_analyze, "match": do_match, "chain": do_chain, "validate": do_validate}[args.cmd](args, cfg, dirs)
        return 0
    except ImportError as exc:
        print(f"\nERROR: missing Python package ({exc}).\nInstall it (pip install -r requirements.txt; "
              f"pythrust: run 'pip install -e .' in your PyThrust folder) or run: python -m pipeline doctor",
              file=sys.stderr)
        return 2
    except (settings.ToolNotFound, FileNotFoundError, KeyError, ValueError) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())