"""Accounts and billing: the Supabase tables and the run log.

Python data models (Pydantic). The source of truth for these files in app/data/model,
which scripts/export_data_models.py writes from the classes. Generated once from the
JSON with every value copied, then maintained here.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Dict, List, Literal, Optional

from pydantic import ConfigDict, Field, RootModel

from .base import DataModel, SqliteModel
from ._accounts_types import (AccessControlId, RunEventEvent, RunEventMode, RunEventRunType, 
    RunEventStatus, SubscriptionPlan, SubscriptionStatus, WaitlistRequestStatus)


class Subscription(DataModel):
    """One row per user: the plan and the free-tier counters. Billing source of truth. The backend writes with the service key; a user can only read their own row."""
    MODEL_NAME: ClassVar[str] = 'subscription'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1, 'kind': 'table', 'table': 'public.subscriptions'}
    user_id: str = Field(pattern='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', json_schema_extra={'db': 'uuid', 'when': 'always'})
    plan: SubscriptionPlan = Field(json_schema_extra={'db': 'text', 'when': 'always'})
    status: SubscriptionStatus = Field(json_schema_extra={'db': 'text', 'when': 'always'})
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
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1, 'kind': 'table', 'table': 'public.profiles'}
    id: str = Field(pattern='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', json_schema_extra={'db': 'uuid', 'when': 'always'})
    email: Optional[str] = Field(json_schema_extra={'db': 'text', 'when': 'always'})
    full_name: Optional[str] = Field(json_schema_extra={'db': 'text', 'when': 'always'})
    approved: bool = Field(json_schema_extra={'db': 'boolean', 'when': 'always'})
    requested_at: str = Field(json_schema_extra={'db': 'timestamptz', 'when': 'always'})
    approved_at: Optional[str] = Field(json_schema_extra={'db': 'timestamptz', 'when': 'always'})
    notified_at: Optional[str] = Field(json_schema_extra={'db': 'timestamptz', 'when': 'always'})


class WaitlistRequest(DataModel):
    """A stranger asking for access. The operator marks it invited; sign-up triggers then let that email in."""
    MODEL_NAME: ClassVar[str] = 'waitlist_request'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1, 'kind': 'table', 'table': 'public.waitlist_requests'}
    id: str = Field(json_schema_extra={'db': 'uuid', 'when': 'always'})
    email: str = Field(pattern='^[^@\\sA-Z]+@[^@\\s.A-Z]+\\.[^@\\sA-Z]{2,}$', json_schema_extra={'db': 'text', 'when': 'always'})
    full_name: Optional[str] = Field(max_length=120, json_schema_extra={'db': 'text', 'when': 'always'})
    note: Optional[str] = Field(max_length=1000, json_schema_extra={'db': 'text', 'when': 'always'})
    status: WaitlistRequestStatus = Field(json_schema_extra={'db': 'text', 'when': 'always'})
    created_at: str = Field(json_schema_extra={'db': 'timestamptz', 'when': 'always'})
    invited_at: Optional[str] = Field(json_schema_extra={'db': 'timestamptz', 'when': 'always'})


class AccessControl(DataModel):
    """A single row holding the invite-only switch, read by the enforce_invite_only sign-up trigger."""
    MODEL_NAME: ClassVar[str] = 'access_control'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1, 'kind': 'table', 'table': 'public.access_control'}
    id: AccessControlId = Field(json_schema_extra={'db': 'boolean', 'when': 'always'})
    invite_only: bool = Field(json_schema_extra={'db': 'boolean', 'when': 'always'})
    updated_at: str = Field(json_schema_extra={'db': 'timestamptz', 'when': 'always'})


class OperatorContext(DataModel):
    """One saved 'about my business' block per user. In local dev the same bodies live in DATA_ROOT/operator_context.json as {user_id: body}."""
    MODEL_NAME: ClassVar[str] = 'operator_context'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1, 'kind': 'table', 'table': 'public.operator_context'}
    user_id: str = Field(json_schema_extra={'db': 'uuid', 'when': 'always'})
    body: str = Field(max_length=1500, json_schema_extra={'db': 'text', 'when': 'always'})
    updated_at: Optional[str] = Field(json_schema_extra={'db': 'timestamptz', 'when': 'always'})


class RunEvent(DataModel):
    """Run metadata, never run content: one row when a panel or sim starts, one when it ends. Written to DATA_ROOT/run_events.jsonl always, and mirrored to Supabase when configured."""
    MODEL_NAME: ClassVar[str] = 'run_event'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1, 'kind': 'table', 'table': 'public.run_events'}
    id: int = Field(default=None, json_schema_extra={'db': 'bigint identity', 'when': 'optional'})
    ts: str = Field(json_schema_extra={'db': 'timestamptz', 'when': 'always'})
    event: RunEventEvent = Field(json_schema_extra={'db': 'text', 'when': 'always'})
    run_id: str = Field(default=None, max_length=64, json_schema_extra={'db': 'text', 'when': 'optional'})
    user_id: str = Field(default=None, max_length=64, json_schema_extra={'db': 'uuid', 'when': 'optional'})
    run_type: RunEventRunType = Field(default=None, json_schema_extra={'db': 'text', 'when': 'optional'})
    mode: RunEventMode = Field(default=None, json_schema_extra={'db': 'text', 'when': 'optional'})
    crowd_size: int = Field(default=None, ge=0, json_schema_extra={'db': 'int', 'when': 'optional'})
    duration_seconds: float = Field(default=None, ge=0, json_schema_extra={'db': 'numeric', 'when': 'optional'})
    status: RunEventStatus = Field(default=None, json_schema_extra={'db': 'text', 'when': 'optional'})
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
