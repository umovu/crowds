"""
API Routes Module
"""

from flask import Blueprint

graph_bp = Blueprint('graph', __name__)
simulation_bp = Blueprint('simulation', __name__)
report_bp = Blueprint('report', __name__)
config_bp = Blueprint('config', __name__)
panel_bp = Blueprint('panel', __name__)
billing_bp = Blueprint('billing', __name__)

from .research import research_bp
from . import graph  # noqa: E402, F401
from . import simulation  # noqa: E402, F401
from . import report  # noqa: E402, F401
from . import config  # noqa: E402, F401
from . import panel  # noqa: E402, F401
from . import billing  # noqa: E402, F401

