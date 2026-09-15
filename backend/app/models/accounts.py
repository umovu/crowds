"""Accounts and billing: the Supabase tables and the run log.

Python data models (Pydantic). The source of truth for these files in app/data/model,
which scripts/export_data_models.py writes from the classes. Generated once from the
JSON with every value copied, then maintained here.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Dict, List, Literal, Optional

from pydantic import ConfigDict, Field, RootModel

from .base import DataModel, SqliteModel


class Subscription(DataModel):
    """One row per user: the plan and the free-tier counters. Billing source of truth. The backend writes with the service key; a user can only read their own row."""
    MODEL_NAME: ClassVar[str] = 'subscription'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'kind': 'table',
         'table': 'public.subscriptions',
         'sql': 'backend/supabase/subscriptions.sql',
         'about': 'One row per user: the plan and the free-tier counters. Billing source of truth. The '
                  'backend writes with the service key; a user can only read their own row.',
         'written_by': ['app/billing.py (_create_default, increment_panel_used, increment_sim_used, '
                        'set_plan)',
                        'api/billing.py (Paystack webhook, cancel)',
                        'trigger handle_new_user_subscription'],
         'read_by': ['app/billing.py (get_entitlement, get_customer_code, get_user_by_customer)'],
         'rules': ['plan is free or paid (database check).',
                   'Counters never go below zero.',
                   'paystack_subscription_code and current_period_end exist but the backend never '
                   'writes them; updated_at has no trigger.']}
    user_id: str = Field(pattern='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', json_schema_extra={'db': 'uuid', 'when': 'always'})
    plan: Literal['free', 'paid'] = Field(json_schema_extra={'db': 'text', 'when': 'always'})
    status: Literal['active', 'cancelled'] = Field(json_schema_extra={'db': 'text', 'when': 'always'})
    panel_used: int = Field(ge=0, json_schema_extra={'db': 'integer', 'when': 'always'})
    sim_used: int = Field(ge=0, json_schema_extra={'db': 'integer', 'when': 'always'})
    paystack_customer_code: Optional[str] = Field(json_schema_extra={'db': 'text', 'when': 'always'})
    paystack_subscription_code: Optional[str] = Field(json_schema_extra={'db': 'text', 'when': 'always'})
    current_period_end: Optional[str] = Field(json_schema_extra={'db': 'timestamptz', 'when': 'always'})
    created_at: str = Field(json_schema_extra={'db': 'timestamptz', 'when': 'always'})
    updated_at: str = Field(json_schema_extra={'db': 'timestamptz', 'when': 'always'})


class Profile(DataModel):
    """One row per account and whether the operator approved it. The waitlist gate reads approved on every API call."""
    MODEL_NAME: ClassVar[str] = 'profile'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'kind': 'table',
         'table': 'public.profiles',
         'sql': 'backend/supabase/profiles.sql',
         'about': 'One row per account and whether the operator approved it. The waitlist gate reads '
                  'approved on every API call.',
         'written_by': ['trigger handle_new_user',
                        'app/approval.py (_create_pending, approve, claim_notification)',
                        'trigger profiles_stamp_approved'],
         'read_by': ['app/approval.py (is_approved, get_profile)', 'api/waitlist.py (_is_approved)'],
         'rules': ['approved_at is stamped by a trigger when approved flips on; the backend never '
                   'writes it.']}
    id: str = Field(pattern='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', json_schema_extra={'db': 'uuid', 'when': 'always'})
    email: Optional[str] = Field(json_schema_extra={'db': 'text', 'when': 'always'})
    full_name: Optional[str] = Field(json_schema_extra={'db': 'text', 'when': 'always'})
    approved: bool = Field(json_schema_extra={'db': 'boolean', 'when': 'always'})
    requested_at: str = Field(json_schema_extra={'db': 'timestamptz', 'when': 'always'})
    approved_at: Optional[str] = Field(json_schema_extra={'db': 'timestamptz', 'when': 'always'})
    notified_at: Optional[str] = Field(json_schema_extra={'db': 'timestamptz',
         'when': 'always',
         'note': "The backend sends 'now()' once, guarded by notified_at is null."})


class WaitlistRequest(DataModel):
    """A stranger asking for access. The operator marks it invited; sign-up triggers then let that email in."""
    MODEL_NAME: ClassVar[str] = 'waitlist_request'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'kind': 'table',
         'table': 'public.waitlist_requests',
         'sql': 'backend/supabase/waitlist_requests.sql',
         'about': 'A stranger asking for access. The operator marks it invited; sign-up triggers then '
                  'let that email in.',
         'written_by': ['api/waitlist.py (_store)',
                        'operator in the dashboard',
                        'trigger enforce_invite_only',
                        'trigger waitlist_requests_stamp_invited'],
         'read_by': ['triggers handle_new_user and enforce_invite_only']}
    id: str = Field(json_schema_extra={'db': 'uuid', 'when': 'always'})
    email: str = Field(pattern='^[^@\\sA-Z]+@[^@\\s.A-Z]+\\.[^@\\sA-Z]{2,}$', json_schema_extra={'db': 'text', 'when': 'always', 'note': 'Lower-case, validated by the route; unique.'})
    full_name: Optional[str] = Field(max_length=120, json_schema_extra={'db': 'text', 'when': 'always'})
    note: Optional[str] = Field(max_length=1000, json_schema_extra={'db': 'text', 'when': 'always'})
    status: Literal['pending', 'invited'] = Field(json_schema_extra={'db': 'text', 'when': 'always'})
    created_at: str = Field(json_schema_extra={'db': 'timestamptz', 'when': 'always'})
    invited_at: Optional[str] = Field(json_schema_extra={'db': 'timestamptz', 'when': 'always'})


class AccessControl(DataModel):
    """A single row holding the invite-only switch, read by the enforce_invite_only sign-up trigger."""
    MODEL_NAME: ClassVar[str] = 'access_control'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'kind': 'table',
         'table': 'public.access_control',
         'sql': 'backend/supabase/access_control.sql',
         'about': 'A single row holding the invite-only switch, read by the enforce_invite_only '
                  'sign-up trigger.',
         'written_by': ['operator in the dashboard'],
         'read_by': ['trigger enforce_invite_only']}
    id: Literal[True] = Field(json_schema_extra={'db': 'boolean',
         'when': 'always',
         'note': 'Primary key fixed at true, so only one row can exist.'})
    invite_only: bool = Field(json_schema_extra={'db': 'boolean', 'when': 'always'})
    updated_at: str = Field(json_schema_extra={'db': 'timestamptz', 'when': 'always'})


class OperatorContext(DataModel):
    """One saved 'about my business' block per user. In local dev the same bodies live in DATA_ROOT/operator_context.json as {user_id: body}."""
    MODEL_NAME: ClassVar[str] = 'operator_context'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'kind': 'table',
         'table': 'public.operator_context',
         'sql': 'backend/supabase/operator_context.sql',
         'about': "One saved 'about my business' block per user. In local dev the same bodies live in "
                  'DATA_ROOT/operator_context.json as {user_id: body}.',
         'written_by': ['services/operator_context.py (save_operator_context)'],
         'read_by': ['services/operator_context.py (get_operator_context)',
                     'panel_service.create_session',
                     'mode_specs.build_operator_context_block'],
         'rules': ['Not yet created on the hosted project (2026-09-14): hosted saves fail and reads '
                   'return empty.'],
         'local_file': {'path': 'DATA_ROOT/operator_context.json',
                        'values': {'type': 'string', 'max_length': 1500}}}
    user_id: str = Field(json_schema_extra={'db': 'uuid', 'when': 'always'})
    body: str = Field(max_length=1500, json_schema_extra={'db': 'text', 'when': 'always'})
    updated_at: Optional[str] = Field(json_schema_extra={'db': 'timestamptz', 'when': 'always'})


class RunEvent(DataModel):
    """Run metadata, never run content: one row when a panel or sim starts, one when it ends. Written to DATA_ROOT/run_events.jsonl always, and mirrored to Supabase when configured."""
    MODEL_NAME: ClassVar[str] = 'run_event'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'kind': 'table',
         'table': 'public.run_events',
         'sql': 'backend/supabase/run_events.sql',
         'about': 'Run metadata, never run content: one row when a panel or sim starts, one when it '
                  'ends. Written to DATA_ROOT/run_events.jsonl always, and mirrored to Supabase when '
                  'configured.',
         'written_by': ['services/run_events.py (record, record_start, record_end)'],
         'read_by': ['services/run_events.py (totals)', 'run_events_by_user view'],
         'rules': ['Only the allow-listed scalar fields in run_events.ALLOWED_FIELDS, plus ts; no free '
                   'text ever.',
                   'Strings are capped at 64 characters.',
                   'Not yet created on the hosted project (2026-09-14): only the local file is written '
                   'there.']}
    id: int = Field(default=None, json_schema_extra={'db': 'bigint identity', 'when': 'optional', 'note': 'Database only; local lines have none.'})
    ts: str = Field(json_schema_extra={'db': 'timestamptz', 'when': 'always'})
    event: Literal['start', 'end'] = Field(json_schema_extra={'db': 'text', 'when': 'always'})
    run_id: str = Field(default=None, max_length=64, json_schema_extra={'db': 'text', 'when': 'optional'})
    user_id: str = Field(default=None, max_length=64, json_schema_extra={'db': 'uuid', 'when': 'optional', 'note': "A uuid when hosted; 'dev' locally with auth off."})
    run_type: Literal['panel', 'simulation'] = Field(default=None, json_schema_extra={'db': 'text', 'when': 'optional'})
    mode: Literal['panel', 'product', 'policy'] = Field(default=None, json_schema_extra={'db': 'text', 'when': 'optional'})
    crowd_size: int = Field(default=None, ge=0, json_schema_extra={'db': 'int', 'when': 'optional'})
    duration_seconds: float = Field(default=None, ge=0, json_schema_extra={'db': 'numeric', 'when': 'optional'})
    status: Literal['started', 'ok', 'failed'] = Field(default=None, json_schema_extra={'db': 'text', 'when': 'optional'})
    error_code: str = Field(default=None, max_length=64, json_schema_extra={'db': 'text', 'when': 'optional'})
    model: str = Field(default=None, max_length=64, json_schema_extra={'db': 'text', 'when': 'optional'})
    prompt_tokens: int = Field(default=None, ge=0, json_schema_extra={'db': 'int', 'when': 'optional'})
    completion_tokens: int = Field(default=None, ge=0, json_schema_extra={'db': 'int', 'when': 'optional'})
    total_tokens: int = Field(default=None, ge=0, json_schema_extra={'db': 'int', 'when': 'optional'})
    cost_usd: float = Field(default=None, ge=0, json_schema_extra={'db': 'numeric', 'when': 'optional'})


#: Model name (app/data/model/<name>.json) -> class.
MODELS = {
    'subscription': Subscription,
    'profile': Profile,
    'waitlist_request': WaitlistRequest,
    'access_control': AccessControl,
    'operator_context': OperatorContext,
    'run_event': RunEvent,
}
