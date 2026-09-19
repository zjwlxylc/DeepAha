"""Narrow integration boundary for the existing DeepAha authority service.

The importer is NOT allowed to invent Source IDs or enable production by itself.
Host adapters must run source approvals in the SAME transaction as the import,
check current authorization/version, and return verified status/actual Source ID.
No commit/rollback or network calls inside approve_in_transaction.
"""
from typing import Protocol
from .errors import ImporterError


class AuthorityPort(Protocol):
    supports_approval: bool

    def resolve(self, tx, principal, system_source_id: str) -> dict | None:
        """Actual existing source status, or None. Must respect tenant/actor scope."""
        ...

    def approve_in_transaction(self, tx, principal, source_records: list[dict]) -> dict[str, dict]:
        """Map asset_id to {system_source_id, approval_status, collection_enabled}.
        Must not overwrite currently effective Brief until explicitly approved.
        """
        ...


class NoProductionAuthority:
    supports_approval = False

    def resolve(self, tx, principal, system_source_id):
        return None

    def approve_in_transaction(self, tx, principal, source_records):
        raise ImporterError('APPROVAL_NOT_CONNECTED', '正式来源批准尚未接入；不会冒充已启用 WMA。', 409)
