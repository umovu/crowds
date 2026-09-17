"""Controllers: thin Flask routes.

A controller reads the request, calls one service, and turns the answer into JSON.
It holds no rules and touches no storage (see tests/test_layers.py).

    view -> controller -> service -> repository
                  |           |
                  +-- model --+

Every route lives here. app/api/ is gone.
"""

from flask import Blueprint

signup_bp = Blueprint('signup', __name__)
account_bp = Blueprint('account', __name__)
billing_bp = Blueprint('billing', __name__)
#: Registered at /api/research, so the persona URLs are unchanged.
persona_bp = Blueprint('persona', __name__)
graph_bp = Blueprint('graph', __name__)
report_bp = Blueprint('report', __name__)
research_bp = Blueprint('research', __name__)
config_bp = Blueprint('config', __name__)
context_bp = Blueprint('context', __name__)
panel_bp = Blueprint('panel', __name__)
simulation_bp = Blueprint('simulation', __name__)

from . import signup_controller  # noqa: E402, F401
from . import account_controller  # noqa: E402, F401
from . import billing_controller  # noqa: E402, F401
from . import persona_controller  # noqa: E402, F401
from . import graph_controller  # noqa: E402, F401
from . import report_controller  # noqa: E402, F401
from . import research_controller  # noqa: E402, F401
from . import config_controller  # noqa: E402, F401
from . import context_controller  # noqa: E402, F401
from . import panel_controller  # noqa: E402, F401
from . import simulation_controller  # noqa: E402, F401
