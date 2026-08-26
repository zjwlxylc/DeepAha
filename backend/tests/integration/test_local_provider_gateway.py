import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from deepaha.artifacts.local_file import LocalFileObjectStore
from deepaha.local_human_test.provider_config import ResolvedProviderConfig
from deepaha.p9b.gateway import GatewayExecutor
from deepaha.p9b.openai_compatible import (
    OpenAICompatibleProviderAdapter,
    ProviderHttpRequest,
    ProviderHttpResponse,
)
from tests.integration.p9b_gateway_support import GATEWAY_MESSAGES, seed_gateway_authority

pytestmark = pytest.mark.integration


@dataclass
class StaticProviderTransport:
    requests: list[ProviderHttpRequest] = field(default_factory=list)

    def send(self, request: ProviderHttpRequest) -> ProviderHttpResponse:
        self.requests.append(request)
        body = json.dumps(
            {
                "id": "chatcmpl_gateway_integration",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({"facts": [], "rules": [], "uncertainties": []}),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 8, "completion_tokens": 4},
            },
            separators=(",", ":"),
        ).encode()
        return ProviderHttpResponse(status_code=200, headers={}, body=body)


def test_real_adapter_is_dispatched_by_gateway_and_audited_to_internal_object(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with factory.begin() as session:
        authority = seed_gateway_authority(session, supports_idempotency=True)
    transport = StaticProviderTransport()
    store = LocalFileObjectStore(root=tmp_path, bucket="deepaha-model-audit")
    adapter = OpenAICompatibleProviderAdapter(
        config=ResolvedProviderConfig.model_validate(
            {
                "provider": authority.intent.provider,
                "base_url": "https://platform.example.invalid",
                "protocol": "openai_chat_completions",
                "model_id": authority.intent.model_id,
                "model_snapshot": authority.intent.model_snapshot,
                "api_key": SecretStr("synthetic-integration-key-not-real"),
            }
        ),
        object_store=store,
        transport=transport,
    )

    ledger = GatewayExecutor(session_factory=factory, adapter=adapter).execute(
        intent=authority.intent,
        messages=GATEWAY_MESSAGES,
    )

    assert ledger["status"] == "SUCCEEDED"
    assert len(transport.requests) == 1
    assert transport.requests[0].headers["Idempotency-Key"]
    with factory() as session:
        row = session.execute(
            text(
                "select raw_response_reference_kind, raw_response_storage_bucket, "
                "raw_response_object_key, raw_response_sha256, response_hash, "
                "parsed_result_hash from p9b_model_call_attempts "
                "where model_call_id = :model_call_id"
            ),
            {"model_call_id": authority.intent.model_call_id},
        ).one()
    assert row.raw_response_reference_kind == "INTERNAL_OBJECT"
    assert row.raw_response_storage_bucket == "deepaha-model-audit"
    assert row.raw_response_sha256 == row.response_hash
    assert row.parsed_result_hash is not None
    assert store.stat(key=cast(str, row.raw_response_object_key)).sha256 == (
        row.raw_response_sha256
    )
