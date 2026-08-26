"""public_official_training_policy_repair

Revision ID: 20260826_0033
Revises: 20260826_0032
Create Date: 2026-08-26 20:00:00
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "20260826_0033"
down_revision: str | None = "20260826_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ATTEMPT_SIGNATURE = "p9b_guard_model_call_attempt()"
_ATTEMPT_LEGACY = "NOT policy.training_use"
_ATTEMPT_PUBLIC_OFFICIAL = (
    "(NOT policy.training_use OR policy.allowed_classifications = "
    "ARRAY['PUBLIC_OFFICIAL_GENERAL']::text[])"
)
_AUTHORITY_SIGNATURE = "p9b_egress_decision_authorized_at(uuid,timestamptz)"
_AUTHORITY_LEGACY = "NOT provider_policy.training_use"
_AUTHORITY_PUBLIC_OFFICIAL = (
    "(NOT provider_policy.training_use OR "
    "provider_policy.allowed_classifications = "
    "ARRAY['PUBLIC_OFFICIAL_GENERAL']::text[])"
)


def upgrade() -> None:
    _replace_condition(
        _ATTEMPT_SIGNATURE,
        current=_ATTEMPT_LEGACY,
        replacement=_ATTEMPT_PUBLIC_OFFICIAL,
    )
    _replace_condition(
        _AUTHORITY_SIGNATURE,
        current=_AUTHORITY_LEGACY,
        replacement=_AUTHORITY_PUBLIC_OFFICIAL,
    )


def downgrade() -> None:
    _replace_condition(
        _ATTEMPT_SIGNATURE,
        current=_ATTEMPT_PUBLIC_OFFICIAL,
        replacement=_ATTEMPT_LEGACY,
    )
    _replace_condition(
        _AUTHORITY_SIGNATURE,
        current=_AUTHORITY_PUBLIC_OFFICIAL,
        replacement=_AUTHORITY_LEGACY,
    )


def _replace_condition(signature: str, *, current: str, replacement: str) -> None:
    connection = op.get_bind()
    definition = connection.scalar(
        text("select pg_get_functiondef(to_regprocedure(:signature))"),
        {"signature": signature},
    )
    if not isinstance(definition, str):
        raise RuntimeError(f"P9B policy function is missing: {signature}")
    if replacement in definition:
        return
    if current not in definition:
        raise RuntimeError(f"P9B policy function shape is unsupported: {signature}")
    connection.exec_driver_sql(
        definition.replace(current, replacement).replace("%", "%%")
    )
