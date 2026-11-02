"""Interactive result plots for VS Code's native Python/Jupyter viewer.

Open this file in VS Code, select the project's virtual environment, edit the
settings in the first cell if needed, then choose "Run All Cells". Each figure
appears inline and can be opened in VS Code's plot viewer.
"""

# %% Plot settings
from IPython.display import display
import matplotlib.pyplot as plt

from pipeline import plots, settings
from pipeline.links import load_motor_urls
from pipeline.results import load_results

RUN_NAME = "2motor"
MAX_AMPS = 60.0
MIN_THRUST_LBF = 9.0
LINK_TO = "prop"  # "prop" or "motor"
VENDOR = "google"  # "google" or "amazon"
BATTERY_CELLS = 4
SHOW_HEATMAPS = False


# %% Load the existing sweep (this does not rerun QPROP)
dirs = settings.run_dirs(RUN_NAME)
results = load_results(
    dirs.results_csv,
    dirs.props_dir,
    max_amps=MAX_AMPS,
    min_thrust_lbf=MIN_THRUST_LBF,
    vendor=VENDOR,
)
results = plots.add_link_columns(
    results,
    LINK_TO,
    VENDOR,
    load_motor_urls(dirs.motors_json),
    BATTERY_CELLS,
)
print(
    f"Loaded {len(results)} combinations from {dirs.results_csv}; "
    f"{int(results['qualifies'].sum())} qualify."
)


# %% Thrust scatter
scatter = plots.plot_scatter(results, MIN_THRUST_LBF, MAX_AMPS)
display(scatter)
plt.close(scatter)


# %% Thrust lines
lines = plots.plot_lines(results, MIN_THRUST_LBF)
display(lines)
plt.close(lines)


# %% Optional metric heatmaps
if SHOW_HEATMAPS:
    for name, figure in plots.plot_heatmaps(results):
        print(name)
        display(figure)
        plt.close(figure)
else:
    print("Set SHOW_HEATMAPS = True in the first cell to render metric heatmaps.")
