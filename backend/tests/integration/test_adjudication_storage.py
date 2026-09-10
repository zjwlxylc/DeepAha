"""Transaction-local prototype of exact text plus generated PostgreSQL projection."""

from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from deepaha.investigations.adjudication_storage import freeze_adjudication, thaw_adjudication
from deepaha.investigations.contracts import digest
from tests.investigations.test_cross_level_adjudication import package

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("number", [1.0, -0.0, 1e-7, 1e20, 1e308, 9007199254740993])
def test_exact_text_roundtrip_with_generated_jsonb(migrated_engine: Engine, number: Any) -> None:
    value = package()
    value["decisions"] = []
    value["proposal"]["evidence"][0]["locator"]["probe"] = number
    value["proposal"]["reason"] = "保留原文\n🎓e\u0301\u00a0"
    saved = freeze_adjudication(value)
    with migrated_engine.begin() as c:
        c.execute(
            text("""CREATE TEMP TABLE frozen_review_probe (
            payload_text text NOT NULL,
            payload_sha256 text NOT NULL CHECK (
                payload_sha256 = encode(sha256(convert_to(payload_text,'UTF8')),'hex')),
            projection jsonb GENERATED ALWAYS AS (payload_text::jsonb) STORED
        ) ON COMMIT DROP""")
        )
        c.execute(
            text("INSERT INTO frozen_review_probe(payload_text,payload_sha256) VALUES (:p,:h)"),
            {"p": saved.payload_text, "h": saved.payload_sha256},
        )
        row = c.execute(
            text("SELECT payload_text,payload_sha256,projection FROM frozen_review_probe")
        ).one()
        restored = thaw_adjudication(
            {
                "storage_version": saved.storage_version,
                "payload_text": row.payload_text,
                "payload_sha256": row.payload_sha256,
            },
            expected_payload_sha256=digest(value),
        )
        assert digest(restored) == digest(value)
        assert row.projection["proposal"]["proposal_id"] == value["proposal"]["proposal_id"]
        # A projection cannot be independently replaced by a caller.
        with pytest.raises(DBAPIError), c.begin_nested():
            c.execute(text("UPDATE frozen_review_probe SET projection='{}'::jsonb"))
        # Text changes without the matching byte hash are refused by PostgreSQL.
        with pytest.raises(DBAPIError), c.begin_nested():
            c.execute(text("UPDATE frozen_review_probe SET payload_text='{}'"))


def test_unrepresentable_jsonb_value_is_rejected_without_rewriting(migrated_engine: Engine) -> None:
    value = package()
    value["decisions"] = []
    value["proposal"]["reason"] = "原文包含\u0000特殊字符"
    saved = freeze_adjudication(value)
    with migrated_engine.begin() as c:
        c.execute(
            text("""CREATE TEMP TABLE frozen_review_probe (
            payload_text text NOT NULL,
            projection jsonb GENERATED ALWAYS AS (payload_text::jsonb) STORED
        ) ON COMMIT DROP""")
        )
        with pytest.raises(DBAPIError), c.begin_nested():
            c.execute(
                text("INSERT INTO frozen_review_probe(payload_text) VALUES (:p)"),
                {"p": saved.payload_text},
            )
        assert c.scalar(text("SELECT count(*) FROM frozen_review_probe")) == 0
        assert saved.payload_sha256 == digest(value)
