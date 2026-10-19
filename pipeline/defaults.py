"""
defaults.py
============
Placeholder motor electrical parameters. These are NOT a real motor: replace
them (or pass a real motors JSON to `sweep`) once you have a datasheet.

DEFAULT_CURRENT_MAX_A is the per-motor current limit used as the default for
--max-amps everywhere, and as PyThrust's current_max_a in stage 1. It is only a
threshold: changing it never requires re-running QPROP.
"""

DEFAULT_RESISTANCE_OHM = 0.0258
DEFAULT_NO_LOAD_CURRENT_A = 1.3
DEFAULT_CURRENT_MAX_A = 60.0
DEFAULT_SYSTEM_RESISTANCE_OHM = 0.095
DEFAULT_RHO = 1.225
