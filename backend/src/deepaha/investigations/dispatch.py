"""Turn a persisted operator intent into one bounded WMA execution.

This module holds the dispatch decision as pure, injectable logic so it can be
unit-tested without a database, a remote SDK or a real claim. It never retries a
prompt: a recovery candidate only ever downloads already-created remote material.
"""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from deepaha.investigations.cli import execute_registered
from deepaha.investigations.contracts import InvestigationError
from deepaha.investigations.local_config import LocalWmaConfigStore
from deepaha.investigations.store import InvestigationStore
from deepaha.investigations.wma import DirectWmaClient, DirectWmaError, WmaBinding

DISPATCH_INTERVAL_SECONDS = 5

ClientFactory = Callable[[WmaBinding], DirectWmaClient]


def build_execution(
    binding: WmaBinding, task_id: UUID, created_by: UUID, *, recover: bool
) -> dict[str, object]:
    """Mirror ``cli``'s live execution shape, but sourced from persisted intent.

    ``operator_id`` is the task creator and ``authorization_reference`` is the
    durable intent, so the dispatch is traceable without a CLI invocation. A
    recovery run carries ``prompt_limit=0`` and only-download evidence.
    """
    return {
        "mode": "LIVE",
        "provider": "WMA",
        "model_id": None,
        "monetary_cost": None,
        "cost_status": "UNREPORTED_BY_PROVIDER",
        "operator_id": str(created_by),
        "authorization_reference": f"persistent-dispatch:{task_id}",
        "agent_id": binding.agent_id,
        "source_app": binding.source_app,
        "sdk": "codebuddy-cloud-agent-sdk==0.3.4",
        "manifest_version": "1.0",
        "agent_release_reference": None,
        "agent_release_evidence": "RECOVERY_ONLY" if recover else "PENDING",
        "money_cap_enforced": False,
        "prompt_limit": 0 if recover else 1,
    }


def should_clear_intent(resulting_status: str, kind: str) -> bool:
    """Only a still-``QUEUED`` new dispatch means the attempt failed pre-claim."""
    return kind == "NEW" and resulting_status == "QUEUED"


async def dispatch_candidate(
    store: InvestigationStore,
    config: LocalWmaConfigStore,
    client_factory: ClientFactory,
    candidate: dict[str, Any],
) -> None:
    """Run one candidate once. Pre-claim failure clears a new task's intent."""
    intent = candidate.get("dispatch_intent")
    if not isinstance(intent, dict) or not intent.get("configuration_revision"):
        return
    try:
        _revision, binding = config.load(intent["configuration_revision"])
    except InvestigationError as error:
        store.finish_dispatch(candidate["task_id"], intent["intent_id"], error.code)
        return
    try:
        client = client_factory(binding)
    except DirectWmaError as error:
        if candidate["kind"] == "NEW":
            store.cancel_dispatch(candidate["task_id"], error.code)
        store.finish_dispatch(candidate["task_id"], intent["intent_id"], error.code)
        return
    recover = candidate["kind"] == "RECOVER"
    execution = build_execution(
        binding, candidate["task_id"], UUID(intent["operator_id"]), recover=recover
    )
    try:
        await execute_registered(store, client, candidate["task_id"], execution, recover=recover)
    except BaseException as error:
        # Decide from the persisted outcome, never by guessing where it failed.
        try:
            view = store.get(candidate["task_id"])
        except Exception:
            view = {}
        if should_clear_intent(str(view.get("status", "")), candidate["kind"]):
            store.cancel_dispatch(
                candidate["task_id"],
                getattr(error, "code", "INVESTIGATION_DEPENDENCY_FAILED"),
            )
    finally:
        store.finish_dispatch(candidate["task_id"], intent["intent_id"])
