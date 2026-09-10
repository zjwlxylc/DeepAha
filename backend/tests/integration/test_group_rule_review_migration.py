import json
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

from deepaha.investigations.group_rule_review import prepare_group_rule_review
from deepaha.local_human_test.review import build_rule_payload
from tests.integration.test_group_rule_review import ready
from tests.integration.test_investigation_store import StoreHarness, harness

pytestmark = pytest.mark.integration
__all__ = ["harness"]


def test_migration_round_trip_and_models(migrated_engine: Engine) -> None:
    config = Config("alembic.ini")
    command.downgrade(config, "20260910_0047")
    command.upgrade(config, "head")
    command.check(config)


def test_review_history_prevents_downgrade(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, fact, request = ready(harness, monkeypatch)
    prepare_group_rule_review(harness.store, task, fact, request, harness.principal)
    with pytest.raises(RuntimeError, match="GROUP_RULE_HISTORY_DOWNGRADE_REFUSED"):
        command.downgrade(Config("alembic.ini"), "20260910_0047")


@pytest.mark.parametrize(
    "field,key,value",
    [
        ("education_requirements", "minimum_level", "MASTER"),
        ("education_requirements", "minimum_level", None),
        ("education_requirements", "minimum_level", 1),
        ("education_requirements", "minimum_level", "UNKNOWN"),
        ("major_requirements", "allowed_codes", ["b", "a", "汉", "😀"]),
        ("major_requirements", "allowed_codes", ["a", "a"]),
        ("major_requirements", "allowed_codes", []),
        ("major_requirements", "allowed_codes", [1]),
        ("major_requirements", "allowed_codes", ["\t"]),
        ("major_requirements", "allowed_codes", ["\u00a0"]),
        ("major_requirements", "allowed_codes", "a"),
        ("credential_requirements", "required_certificates", ["c2", "c1"]),
        ("household_registration_requirements", "allowed_regions", ["浙江"]),
        ("applicant_scope", "student_statuses", ["GRADUATED"]),
        ("age_requirements", "birth_date_between", ["1990-01-01", "2000-01-01"]),
        ("age_requirements", "birth_date_between", ["1990-01-01", "1990-01-01"]),
        ("age_requirements", "birth_date_between", ["\t", "2000-01-01"]),
        ("age_requirements", "birth_date_between", ["1990-01-01"]),
        ("title", "name", "Metadata"),
    ],
)
def test_sql_deriver_matches_python(
    migrated_engine: Engine, field: str, key: str, value: Any
) -> None:
    norm = {key: value}
    expected = build_rule_payload(field_name=field, normalized_value=norm)
    with migrated_engine.connect() as connection:
        actual = connection.scalar(
            text("SELECT investigation_group_rule_payload(:field,CAST(:norm AS jsonb),'test')"),
            {"field": field, "norm": json.dumps(norm)},
        )
    assert actual == (
        expected.model_dump(mode="json") | {"code": "group-preview-test"} if expected else None
    )
