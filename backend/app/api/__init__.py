"""
API Routes Module
"""

from flask import Blueprint

# graph now lives in app/controllers/ (graph slice).
simulation_bp = Blueprint('simulation', __name__)
# report now lives in app/controllers/ (report slice).
config_bp = Blueprint('config', __name__)
panel_bp = Blueprint('panel', __name__)
# billing now lives in app/controllers/ (billing slice).
context_bp = Blueprint('context', __name__)
# account and waitlist now live in app/controllers/ (signup slice).

from .research import research_bp
from . import simulation  # noqa: E402, F401
from . import config  # noqa: E402, F401
from . import panel  # noqa: E402, F401
from . import context  # noqa: E402, F401

