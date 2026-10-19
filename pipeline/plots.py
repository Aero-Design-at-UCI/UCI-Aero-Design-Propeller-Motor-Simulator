"""Plots. Thrust is always in lbf. Scatter x axis = geometric prop pitch (in).

Colour: Kv uses ONE sequential blue ramp (light = low Kv, dark = high Kv).
Infeasible points are drawn as grey crosses AND listed in the legend, so meaning
never rests on colour alone. SVG output makes every dot a clickable link.
"""
from __future__ import annotations

from html import escape
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

from . import links

KV_CMAP = LinearSegmentedColormap.from_list("kv_blue", ["#cfe0f5", "#2a78d6", "#0b2f66"])
INK, MUTED, GRID, BAD = "#0b0b0b", "#52514e", "#e6e5e1", "#8a8985"


def _style(ax):
    ax.grid(color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=9)


def add_link_columns(df, link_to="prop", vendor="google", motor_urls=None, cells=4):
    """Adds motor_url and node_url columns (what each dot links to)."""
    df = df.copy()
    motor_urls = motor_urls or {}
    df["motor_url"] = [motor_urls.get(m) or links.motor_search_url(kv, cells, vendor)
                       for m, kv in zip(df["motor"], df["kv"])]
    if link_to == "motor" or "prop_url" not in df.columns:
        df["node_url"] = df["motor_url"]
    else:
        df["node_url"] = df["prop_url"].fillna(df["motor_url"])
    return df


def plot_scatter(df, min_lbf, max_amps, out_png, out_svg=None):
    """Two panels (takeoff, climb): thrust per motor (lbf) vs prop pitch, coloured by Kv."""
    xcol = "pitch_in" if "pitch_in" in df.columns else None
    d = df.copy()
    d["_x"] = d[xcol] if xcol else d["prop"].str.extract(r"(\d+)")[0].astype(float)
    xlabel = ("Geometric prop pitch at 75% radius (in)" if xcol else "Prop index")
    kmin, kmax = float(d["kv"].min()), float(d["kv"].max())
    norm = plt.Normalize(kmin, kmax if kmax > kmin else kmin + 1)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), sharey=True)
    for ax, cond, title in zip(axes, ("takeoff", "climb"), ("Takeoff (static)", "Climb")):
        ycol = f"{cond}_thrust_lbf"
        ok = d[d[f"{cond}_feasible"] & d[ycol].notna()]
        bad = d[~d[f"{cond}_feasible"] & d[ycol].notna()]
        sc = ax.scatter(ok["_x"], ok[ycol], c=ok["kv"], cmap=KV_CMAP, norm=norm, s=34,
                        edgecolors="white", linewidths=0.6, zorder=3, label=f"within {max_amps:g} A")
        if "node_url" in ok:
            sc.set_urls(list(ok["node_url"]))
        if len(bad):
            bx = ax.scatter(bad["_x"], bad[ycol], marker="x", s=30, color=BAD, linewidths=1.0,
                            zorder=2, label=f"over {max_amps:g} A or windmilling")
            if "node_url" in bad:
                bx.set_urls(list(bad["node_url"]))
        if min_lbf > 0:
            ax.axhline(min_lbf, color=INK, linestyle="--", linewidth=1.1, zorder=1)
            ax.text(0.99, min_lbf, f"{min_lbf:g} lbf required", transform=ax.get_yaxis_transform(),
                    va="bottom", ha="right", fontsize=9, color=INK,
                    bbox=dict(facecolor="white", edgecolor="none", pad=1.5, alpha=0.9), zorder=4)
        ax.set_title(title, loc="left", fontsize=11, color=INK)
        ax.set_xlabel(xlabel, color=MUTED)
        _style(ax)
    axes[0].set_ylabel("Thrust per motor (lbf)", color=MUTED)
    from matplotlib.lines import Line2D
    axes[0].legend(handles=[
        Line2D([], [], marker="o", linestyle="", color="#2a78d6", markeredgecolor="white", label=f"within {max_amps:g} A (colour = Kv)"),
        Line2D([], [], marker="x", linestyle="", color=BAD, label=f"over {max_amps:g} A or windmilling")],
        loc="upper left", fontsize=8, frameon=False)
    cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=KV_CMAP), ax=axes, pad=0.02)
    cb.set_label("Motor Kv (RPM/V)", color=MUTED)
    n_q = int(d["qualifies"].sum()) if "qualifies" in d else 0
    fig.suptitle(f"Thrust per motor vs prop pitch - {n_q}/{len(d)} combos meet "
                 f"{min_lbf:g} lbf at both points within {max_amps:g} A"
                 + ("  (click a dot in the SVG to open its link)" if out_svg else ""),
                 x=0.01, ha="left", fontsize=11, color=INK)
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    if out_svg:
        fig.savefig(out_svg, bbox_inches="tight")
    plt.close(fig)


def plot_lines(df, min_lbf, out_png):
    """Thrust vs prop, one thin line per Kv (sequential ramp)."""
    kvs = sorted(df["kv"].unique())
    order = sorted(df["prop"].unique())
    fig, axes = plt.subplots(2, 1, figsize=(9, 8), sharex=True)
    for ax, cond, lab in zip(axes, ("takeoff", "climb"), ("Takeoff thrust per motor (lbf)", "Climb thrust per motor (lbf)")):
        for i, kv in enumerate(kvs):
            s = df[df["kv"] == kv].set_index("prop").reindex(order)
            ax.plot(order, s[f"{cond}_thrust_lbf"], color=KV_CMAP(i / max(len(kvs) - 1, 1)), linewidth=1.2)
        if min_lbf > 0:
            ax.axhline(min_lbf, color=INK, linestyle="--", linewidth=1.1)
        ax.set_ylabel(lab, color=MUTED)
        _style(ax)
    plt.setp(axes[-1].get_xticklabels(), rotation=60, ha="right")
    axes[-1].set_xlabel("Prop design (p00 = lowest design thrust / pitch ... highest)", color=MUTED)
    fig.colorbar(plt.cm.ScalarMappable(norm=plt.Normalize(min(kvs), max(kvs)), cmap=KV_CMAP),
                 ax=axes, label="Motor Kv (RPM/V)")
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)


HEATMAPS = [
    ("takeoff_thrust_lbf", "Takeoff thrust per motor (lbf)", "Blues", "takeoff_feasible"),
    ("climb_thrust_lbf", "Climb thrust per motor (lbf)", "Blues", "climb_feasible"),
    ("takeoff_amps", "Takeoff current per motor (A)", "Oranges", "takeoff_feasible"),
    ("climb_amps", "Climb current per motor (A)", "Oranges", "climb_feasible"),
    ("takeoff_eff_pct", "Takeoff motor efficiency (%)", "Greens", "takeoff_feasible"),
    ("climb_eff_pct", "Climb motor efficiency (%)", "Greens", "climb_feasible"),
]


def plot_heatmaps(df, out_dir):
    """One heatmap per metric (motors by Kv on y, props on x); infeasible cells hatched with X."""
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for col, title, cmap, feas in HEATMAPS:
        piv = df.pivot(index="kv", columns="prop", values=col).sort_index()
        fp = df.pivot(index="kv", columns="prop", values=feas).reindex(index=piv.index, columns=piv.columns)
        fig, ax = plt.subplots(figsize=(max(8, 0.34 * piv.shape[1]), max(6, 0.28 * piv.shape[0])))
        im = ax.imshow(piv.values.astype(float), aspect="auto", cmap=cmap, origin="lower")
        for (i, j), ok in np.ndenumerate(fp.values.astype(bool)):
            if not ok:
                ax.text(j, i, "x", ha="center", va="center", fontsize=7, color=BAD)
        ax.set_xticks(range(piv.shape[1])); ax.set_xticklabels(piv.columns, rotation=90, fontsize=7)
        ax.set_yticks(range(piv.shape[0])); ax.set_yticklabels([f"{k:.0f}" for k in piv.index], fontsize=7)
        ax.set_xlabel("Prop"); ax.set_ylabel("Motor Kv (RPM/V)")
        ax.set_title(title + "   (x = infeasible)", loc="left", fontsize=11)
        fig.colorbar(im, ax=ax)
        path = out_dir / f"heatmap_{col}.png"
        fig.savefig(path, dpi=140, bbox_inches="tight"); plt.close(fig)
        written.append(path)
    return written


def plot_thrust_curves(curves, out_png, a):
    """Total aircraft thrust vs airspeed (lbf) with the assumed drag curve."""
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for i, c in enumerate(curves):
        ax.plot(c["v"], [t * 0.224809 for t in c["t"]], linewidth=1.4, color=plt.cm.tab10(i % 10), label=c["label"])
    if curves:
        ax.plot(curves[0]["v"], [t * 0.224809 for t in curves[0]["drag"]], "--", color=INK, linewidth=1.5,
                label=f"assumed drag (L/D {a.ld_ratio:g}, cruise {a.cruise_speed:g} m/s)")
    ax.axhline(0, color=MUTED, linewidth=0.6)
    ax.set_xlabel("Airspeed (m/s)", color=MUTED); ax.set_ylabel("Total thrust, full throttle (lbf)", color=MUTED)
    ax.set_title("Where a curve meets the dashed drag line is that design's max level speed", loc="left", fontsize=11)
    ax.legend(fontsize=7, frameon=False, ncol=2); _style(ax)
    fig.savefig(out_png, dpi=150, bbox_inches="tight"); plt.close(fig)


def write_links_html(df, path, min_lbf, max_amps):
    """Clickable table of every qualifying combo with prop and motor shopping links."""
    q = df[df["qualifies"]].sort_values("takeoff_thrust_N", ascending=False)
    rows = []
    for _, r in q.iterrows():
        rows.append(
            f"<tr><td>{escape(r['motor'])}</td><td>{r['kv']:.0f}</td><td>{escape(r['prop'])}</td>"
            f"<td>{escape(str(r.get('prop_label', '')))}</td><td>{r.get('pitch_gap_in', float('nan')):.2f}</td><td>{r['takeoff_thrust_lbf']:.2f}</td>"
            f"<td>{r['climb_thrust_lbf']:.2f}</td><td>{r['takeoff_amps']:.1f}</td>"
            f"<td><a href='{escape(str(r.get('prop_url', '')))}'>prop search</a></td>"
            f"<td><a href='{escape(r['motor_url'])}'>motor</a></td></tr>")
    html = f"""<!doctype html><meta charset="utf-8"><title>Qualifying combos</title>
<style>body{{font:14px system-ui;margin:24px;color:#0b0b0b}}table{{border-collapse:collapse}}
td,th{{padding:4px 10px;border-bottom:1px solid #ddd;text-align:left}}th{{color:#52514e}}</style>
<h2>{len(q)} combos reach {min_lbf:g} lbf per motor at takeoff and climb within {max_amps:g} A</h2>
<p>The QMIL blade itself is not for sale. Each is matched to the real APC model at the same diameter with the closest pitch (pitch only; chord/twist not compared). Links are searches, not verified product pages.</p>
<table><tr><th>Motor</th><th>Kv</th><th>Prop</th><th>Closest real APC prop</th><th>Pitch gap (in)</th><th>T/O lbf</th><th>Climb lbf</th><th>T/O A</th><th></th><th></th></tr>
{''.join(rows)}</table>"""
    Path(path).write_text(html, encoding="utf-8")
