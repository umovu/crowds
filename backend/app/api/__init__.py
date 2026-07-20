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


# ── Ownership enforcement ───────────────────────────────────────────────────
# Applied at the blueprint level rather than per-handler so that a route added
# later is guarded by default: any view whose URL carries <simulation_id> or
# <session_id> is ownership-checked before the handler runs. Routes that take
# the id in the JSON body instead check explicitly inside the handler.
def _guard_simulation_routes():
    from flask import request
    from ..authz import check_simulation

    sim_id = (request.view_args or {}).get('simulation_id')
    if sim_id:
        return check_simulation(sim_id)

    if request.method in ('POST', 'PUT', 'PATCH'):
        # Many sim routes (/start, /stop, /interview*, /env-status, /prepare…)
        # take the id in the JSON body instead of the URL. get_json is cached by
        # Flask, so reading it here costs the handler nothing.
        body = request.get_json(silent=True)
        if isinstance(body, dict):
            body_id = body.get('simulation_id') or body.get('new_simulation_id')
            if body_id:
                # missing_ok: /prepare/status is polled before the sim exists.
                return check_simulation(body_id, missing_ok=True)
    return None


def _guard_panel_routes():
    from flask import request
    from ..authz import check_panel_session

    session_id = (request.view_args or {}).get('session_id')
    if session_id:
        return check_panel_session(session_id)
    return None


simulation_bp.before_request(_guard_simulation_routes)
panel_bp.before_request(_guard_panel_routes)

from .research import research_bp
from . import graph  # noqa: E402, F401
from . import simulation  # noqa: E402, F401
from . import report  # noqa: E402, F401
from . import config  # noqa: E402, F401
from . import panel  # noqa: E402, F401
from . import billing  # noqa: E402, F401

