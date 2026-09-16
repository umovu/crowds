"""Controllers: thin Flask routes.

A controller reads the request, calls one service, and turns the answer into JSON.
It holds no rules and touches no storage (see tests/test_layers.py).

    view -> controller -> service -> repository
                  |           |
                  +-- model --+

Routes still living in app/api/ are being moved here one slice at a time.
"""

from flask import Blueprint

signup_bp = Blueprint('signup', __name__)
account_bp = Blueprint('account', __name__)
billing_bp = Blueprint('billing', __name__)
#: Registered at /api/research, so the persona URLs are unchanged.
persona_bp = Blueprint('persona', __name__)

from . import signup_controller  # noqa: E402, F401
from . import account_controller  # noqa: E402, F401
from . import billing_controller  # noqa: E402, F401
from . import persona_controller  # noqa: E402, F401
