"""
API Routes Module
"""

from flask import Blueprint

# graph now lives in app/controllers/ (graph slice).
simulation_bp = Blueprint('simulation', __name__)
panel_bp = Blueprint('panel', __name__)

# Everything else now lives in app/controllers/: graph, report, billing, account,
# waitlist, research, config and context. These two are the last routes left here.
from . import simulation  # noqa: E402, F401
from . import panel  # noqa: E402, F401

