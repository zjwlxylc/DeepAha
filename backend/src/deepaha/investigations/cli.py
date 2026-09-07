"""Explicit local operator entry point. Registration never invokes a cloud agent."""

import argparse
import asyncio
import json
from uuid import UUID

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.orm import Session

from deepaha.artifacts.local_file import LocalFileObjectStore
from deepaha.core.settings import Settings
from deepaha.db.session import get_engine, session_factory
from deepaha.investigations.contracts import InvestigationError
from deepaha.investigations.runner import execute_investigation
from deepaha.investigations.store import InvestigationStore
from deepaha.investigations.wma import DirectWmaClient, WmaBinding
from deepaha.review.auth import (
    OPPORTUNITY_FACT_VALIDATION_PURPOSE,
    ReviewerRole,
    require_reviewer_authority,
    resolve_reviewer_principal,
)


class WmaEnvironment(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEEPAHA_WMA_", extra="ignore")
    live_enabled: bool = False
    api_key: SecretStr | None = None
    agent_id: str = ""
    source_app: str = ""
    manifest_version: str = "1.0"
    reviewer_token: SecretStr | None = None


def require_local_ready(settings: Settings, config: WmaEnvironment) -> None:
    if (
        settings.environment != "development"
        or not settings.local_human_test_enabled
        or settings.local_human_test_root is None
        or settings.local_human_test_bind_host not in ("localhost", "127.0.0.1", "::1")
        or config.reviewer_token is None
    ):
        raise InvestigationError("LOCAL_WMA_PREFLIGHT_INCOMPLETE")


def require_live_ready(settings: Settings, config: WmaEnvironment) -> None:
    require_local_ready(settings, config)
    if (
        not config.live_enabled
        or config.api_key is None
        or not config.agent_id
        or not config.source_app
    ):
        raise InvestigationError("LIVE_WMA_PREFLIGHT_INCOMPLETE")


async def inspect_agent(client: DirectWmaClient) -> dict[str, object]:
    try:
        return await client.inspect_release()
    finally:
        await client.aclose()


async def execute_registered(
    store: InvestigationStore,
    client: DirectWmaClient,
    task_id: UUID,
    execution: dict[str, object],
    *,
    recover: bool = False,
) -> None:
    try:
        if not recover:
            release = await client.inspect_release()
            execution = execution | {
                "published_release": release,
                "agent_release_evidence": "CONTROL_PLANE",
            }
    except BaseException:
        try:
            async with asyncio.timeout(5):
                await client.aclose()
        except BaseException:
            pass
        raise
    # The runner owns connection cleanup from this point, including claim failure.
    await execute_investigation(store, client, task_id, execution, recover=recover)


def main() -> int:
    parser = argparse.ArgumentParser(description="DeepAha bounded Direct WMA intake")
    parser.add_argument(
        "operation", choices=("preflight", "inspect-agent", "run", "recover", "show")
    )
    parser.add_argument("task_id", nargs="?", type=UUID)
    parser.add_argument("--authorization-reference")
    parser.add_argument("--agent-release-reference")
    args = parser.parse_args()
    try:
        settings, config = Settings(), WmaEnvironment()
        if args.operation == "preflight":
            print(
                json.dumps(
                    {
                        "local_enabled": settings.local_human_test_enabled,
                        "local_root_configured": settings.local_human_test_root is not None,
                        "database_configured": settings.database_url is not None,
                        "live_enabled": config.live_enabled,
                        "api_key_present": config.api_key is not None,
                        "agent_id_present": bool(config.agent_id),
                        "source_app_present": bool(config.source_app),
                        "operator_token_present": config.reviewer_token is not None,
                        "money_cap_enforced": False,
                        "prompt_limit_per_run": 1,
                        "published_binding_required": True,
                    }
                )
            )
            return 0
        if args.operation == "inspect-agent":
            if config.api_key is None or not config.agent_id or not config.source_app:
                raise InvestigationError("WMA_INSPECTION_CONFIG_REQUIRED")
            client = DirectWmaClient(
                WmaBinding(
                    config.api_key, config.agent_id, config.source_app, config.manifest_version
                )
            )
            print(json.dumps(asyncio.run(inspect_agent(client)), ensure_ascii=False))
            return 0
        if args.task_id is None:
            raise InvestigationError("TASK_ID_REQUIRED")
        require_local_ready(settings, config)
        if settings.local_human_test_root is None or config.reviewer_token is None:
            raise InvestigationError("LIVE_WMA_PREFLIGHT_INCOMPLETE")
        engine = get_engine(settings)
        try:
            with Session(engine) as session:
                principal = resolve_reviewer_principal(
                    f"Bearer {config.reviewer_token.get_secret_value()}", session, settings
                )
                require_reviewer_authority(
                    principal, ReviewerRole.LOCAL_TEST_OPERATOR, OPPORTUNITY_FACT_VALIDATION_PURPOSE
                )
                if principal.synthetic:
                    raise InvestigationError("REAL_OPERATOR_REQUIRED")
            store = InvestigationStore(
                session_factory(engine),
                LocalFileObjectStore(
                    root=settings.local_human_test_root / "investigation-objects",
                    bucket="deepaha-investigations",
                ),
            )
            if args.operation == "show":
                print(json.dumps(store.get(args.task_id), ensure_ascii=False))
                return 0
            require_live_ready(settings, config)
            if (
                not args.authorization_reference
                or len(args.authorization_reference) > 256
                or (args.agent_release_reference and len(args.agent_release_reference) > 256)
            ):
                raise InvestigationError("CALL_AUTHORIZATION_REFERENCE_REQUIRED")
            if config.api_key is None:
                raise InvestigationError("LIVE_WMA_PREFLIGHT_INCOMPLETE")
            execution: dict[str, object] = {
                "mode": "LIVE",
                "provider": "WMA",
                "model_id": None,
                "monetary_cost": None,
                "cost_status": "UNREPORTED_BY_PROVIDER",
                "operator_id": str(principal.reviewer_id),
                "authorization_reference": args.authorization_reference,
                "agent_id": config.agent_id,
                "source_app": config.source_app,
                "sdk": "codebuddy-cloud-agent-sdk==0.3.4",
                "manifest_version": config.manifest_version,
                "agent_release_reference": args.agent_release_reference,
                "agent_release_evidence": "RECOVERY_ONLY"
                if args.operation == "recover"
                else "PENDING",
                "money_cap_enforced": False,
                "prompt_limit": 0 if args.operation == "recover" else 1,
            }
            client = DirectWmaClient(
                WmaBinding(
                    config.api_key, config.agent_id, config.source_app, config.manifest_version
                )
            )
            asyncio.run(
                execute_registered(
                    store, client, args.task_id, execution, recover=args.operation == "recover"
                )
            )
            task = store.get(args.task_id)
            print(
                json.dumps(
                    {
                        key: task[key]
                        for key in ("task_id", "status", "error_code", "delivery_hash", "issues")
                    }
                )
            )
            return 0
        finally:
            engine.dispose()
    except Exception as error:
        # Never print SDK exception text, environment values or authentication material.
        print(json.dumps({"error_code": getattr(error, "code", "INVESTIGATION_COMMAND_FAILED")}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
