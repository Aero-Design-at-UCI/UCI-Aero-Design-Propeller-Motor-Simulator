from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import matplotlib
import pandas as pd

matplotlib.use("Agg")

from pipeline import plots
from pipeline.cli import do_plot
from pipeline.settings import RunDirs


class PlotTests(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame(
            {
                "motor": ["m1", "m2"],
                "kv": [700.0, 900.0],
                "prop": ["p00", "p01"],
                "pitch_in": [4.0, 5.0],
                "takeoff_thrust_lbf": [10.0, 8.0],
                "climb_thrust_lbf": [9.5, 7.5],
                "takeoff_amps": [40.0, 65.0],
                "climb_amps": [35.0, 55.0],
                "takeoff_eff_pct": [80.0, 75.0],
                "climb_eff_pct": [82.0, 77.0],
                "takeoff_feasible": [True, False],
                "climb_feasible": [True, True],
                "qualifies": [True, False],
                "node_url": ["https://example.com/1", "https://example.com/2"],
            }
        )

    def tearDown(self):
        import matplotlib.pyplot as plt

        plt.close("all")

    def test_figure_builders_return_figures_without_writing_files(self):
        scatter = plots.plot_scatter(self.df, 9.0, 60.0)
        lines = plots.plot_lines(self.df, 9.0)
        heatmaps = plots.plot_heatmaps(self.df)

        self.assertEqual(3, len(scatter.axes))
        self.assertEqual(3, len(lines.axes))
        self.assertEqual(len(plots.HEATMAPS), len(heatmaps))
        self.assertTrue(all(name.startswith("heatmap_") for name, _ in heatmaps))

    def test_save_figure_exports_requested_path(self):
        fig = plots.plot_scatter(self.df, 9.0, 60.0)
        # Keep the temporary export inside the repository so this also runs in
        # restricted CI/agent environments whose system temp folder is read-only.
        with TemporaryDirectory(dir=Path.cwd()) as tmp:
            target = Path(tmp) / "nested" / "scatter.png"
            result = plots.save_figure(fig, target)
            self.assertEqual(target, result)
            self.assertGreater(target.stat().st_size, 0)

    def test_cli_plot_exports_all_report_artifacts(self):
        raw = pd.DataFrame(
            {
                "motor": ["m1", "m2"],
                "kv": [700.0, 900.0],
                "prop": ["p00", "p01"],
                "takeoff_thrust_N": [44.4822, 35.5858],
                "climb_thrust_N": [42.2579, 33.3616],
                "takeoff_amps": [40.0, 65.0],
                "climb_amps": [35.0, 55.0],
                "takeoff_eff_pct": [80.0, 75.0],
                "climb_eff_pct": [82.0, 77.0],
            }
        )
        args = SimpleNamespace(
            max_amps=60.0,
            min_thrust_lbf=9.0,
            link_to="prop",
            vendor="google",
            motors_file=None,
            cells=4,
            heatmaps=True,
        )
        with TemporaryDirectory(dir=Path.cwd()) as tmp:
            dirs = RunDirs("test", Path(tmp))
            raw.to_csv(dirs.results_csv, index=False)
            do_plot(args, None, dirs)

            expected = [
                "scatter_thrust.png",
                "scatter_thrust.svg",
                "thrust_vs_prop_lines.png",
                "node_links.csv",
                "qualifying_combos.csv",
                "links.html",
            ]
            for name in expected:
                self.assertGreater((dirs.graphs_dir / name).stat().st_size, 0)
            self.assertEqual(
                len(plots.HEATMAPS),
                len(list((dirs.graphs_dir / "heatmaps").glob("*.png"))),
            )


if __name__ == "__main__":
    unittest.main()
