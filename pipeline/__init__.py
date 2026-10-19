"""PyThrust -> QMIL -> QPROP propulsion design pipeline (SAE Aero Design)."""
import os

# OpenMDAO writes a "<script>_out" report folder every time a Problem is created.
# Stage 1 creates one Problem per solve, which is how a project ends up with dozens
# of main*_out folders. Reports are not needed here, so switch them off globally.
os.environ.setdefault("OPENMDAO_REPORTS", "0")

__version__ = "1.0.0"
