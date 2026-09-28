"""Setting up a panel session: what gets pitched, to how many, and to whom.

Session creation is LLM-free. The cast, grant detection and budget tiers are all
computed from real persona data; this module only decides the inputs:

  * a pointer's required slots must be filled before a junk seed is run
  * an assembled seed stands in for the pitch when none was typed
  * the free plan caps the cast, the paid plan does not
  * the audience is routed from the seed when the caller did not pick one

No Flask. The caller passes the user id, since only a request knows who is asking.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger
from . import billing_service, panel_service, pointers

logger = get_logger("fub.panel_session")

#: Free plan cast cap. Paid may go up to panel_service.MAX_CAST_SIZE.
FREE_CAST_CAP = 12

#: Panels have one path. The pitch itself decides what applies (a stated price turns on
#: affordability), so there is no policy/product guess to get wrong. A 50/50 keyword
#: tie used to run a priced clinic offer as "policy" and silently drop every income
#: band. Old sessions keep their stored mode and render as before.
PANEL_MODE = "panel"


class MissingSlots(ValueError):
    """A pointer was chosen but its required slots are not filled."""

    def __init__(self, missing: List[str]):
        self.missing = missing
        super().__init__(f"Missing required field(s): {', '.join(missing)}")


def _cast_size(requested: Any, user_id: Optional[str]) -> int:
    """The cast size this caller is allowed. Free plans are capped."""
    if billing_service.get_entitlement(user_id).get('plan') == 'paid':
        return requested
    try:
        return min(int(requested), FREE_CAST_CAP)
    except (ValueError, TypeError):
        return FREE_CAST_CAP


def _audience(data: Dict[str, Any], pointer: Optional[str],
              pitched: str) -> Optional[List[str]]:
    """Which groups to mix. An explicit choice always wins over routing."""
    segments = data.get('segments')
    if not segments and data.get('segment'):
        segments = [data.get('segment')]
    # A described audience is the room already; routing the pitch to keyword
    # groups on top would re-split it (and could leave no one who is both).
    described = data.get('audience') or {}
    if pointer and not segments and not (described.get('facts') or described.get('provinces')):
        segments = pointers.route_segments(pointer, pitched) or None
    return segments


def create(data: Dict[str, Any], user_id: Optional[str]) -> Dict[str, Any]:
    """Create a panel session and count it against the caller's quota.

    Raises MissingSlots when a pointer's required fields are blank. `panel_service`
    raises ValueError/RuntimeError for an unusable request, which the caller answers
    with a 400.
    """
    pointer = data.get('pointer')
    slots = data.get('slots') or {}
    if pointer:
        missing = pointers.missing_required(pointer, slots)
        if missing:
            raise MissingSlots(missing)

    # An assembled seed stands in for the pitch when none was sent; an explicit
    # pitch always wins.
    pitched = (data.get('pitch') or '').strip()
    if pointer and not pitched:
        pitched = pointers.assemble_seed(pointer, slots)

    segments = _audience(data, pointer, pitched)
    meta = panel_service.create_session(
        pitch=pitched,
        mode=PANEL_MODE,
        n=_cast_size(data.get('n', panel_service.DEFAULT_CAST_SIZE), user_id),
        province=data.get('province'),
        seed=data.get('seed'),
        segment=segments[0] if len(segments or []) == 1 else None,
        segments=segments,
        budget_tiers=data.get('budget_tiers'),
        attitudes=data.get('attitudes'),
        audience=data.get('audience'),
        user_id=user_id,
        pointer=pointer,
        slots=slots if pointer else None,
    )
    # No-op on paid, and when billing is off.
    billing_service.increment_panel_used(user_id)
    return meta
