"""
API Routes Module
"""

from flask import Blueprint

# graph now lives in app/controllers/ (graph slice).
simulation_bp = Blueprint('simulation', __name__)

# Everything else now lives in app/controllers/: graph, report, billing, account,
# waitlist, research, config, context and panel. Simulation is the last one here.
from . import simulation  # noqa: E402, F401

