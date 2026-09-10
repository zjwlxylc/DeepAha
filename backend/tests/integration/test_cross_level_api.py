"""Real API/service/PG roundtrip with synthetic sources and reviewer identity."""

import json
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI

from deepaha.api.investigations import get_investigation_store
from deepaha.api.local_human_test import require_local_test_principal
from deepaha.investigations.applicability import read_rule_applicability, save_rule_applicability
from deepaha.investigations.cross_level_preview import preview_cross_level
from deepaha.investigations.group_applicability import read_group_rule_applicability
from deepaha.investigations.group_applicability_decisions import save_group_applicability
from tests.api.test_investigations import make_client
from tests.integration.test_cross_level_preview import all_levels, approve_announcement
from tests.integration.test_group_applicability_decisions import command as group_command
from tests.integration.test_investigation_rule_applicability import command as ann_command
from tests.integration.test_investigation_store import StoreHarness, _files, harness

__all__ = ["harness"]
pytestmark = pytest.mark.integration


@pytest.mark.parametrize("with_float", [False, True])
def test_current_cross_level_api_roundtrip(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, with_float: bool
) -> None:
    h = harness
    if with_float:

        def float_files(task_id: UUID) -> tuple[dict[str, bytes], dict[str, bytes]]:
            files, artifacts = _files(task_id)
            opportunities = json.loads(files["opportunities.json"])
            evidence = json.loads(files["evidence.json"])
            # Retain numeric representation in an unresolved raw row. Do not turn
            # this unknown locator into mechanically verified evidence.
            opportunities["units"][0]["unit_level"][1]["evidence"][0]["locator"]["weight"] = 1.0
            group_rows = [f for f in evidence["facts_flat"] if f["entity_id"] == "unit"]
            group_rows[1]["evidence"][0]["locator"]["weight"] = 1.0
            files["opportunities.json"] = json.dumps(opportunities).encode()
            files["evidence.json"] = json.dumps(evidence).encode()
            return files, artifacts

        monkeypatch.setattr("tests.integration.test_investigation_facts._files", float_files)
    task, plan, source, candidate = all_levels(h, monkeypatch)
    ann, ann_candidate = approve_announcement(h, task, plan)
    av = read_rule_applicability(h.store, task, plan, ann, ann_candidate, h.principal)
    save_rule_applicability(h.store, task, ann_command(av), h.principal, "ann-applies")
    gv = read_group_rule_applicability(h.store, task, plan, source, candidate, h.principal)
    save_group_applicability(
        h.store, task, group_command(gv, "DOES_NOT_APPLY"), h.principal, "exclude"
    )
    expected = preview_cross_level(h.store, task, plan, h.principal)
    client, _ = make_client(tmp_path)
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_investigation_store] = lambda: h.store
    app.dependency_overrides[require_local_test_principal] = lambda: h.principal
    with client:
        response = client.get(
            f"/api/v1/local-human-test/investigations/{task}/unit-plans/{plan}/cross-level-preview"
        )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == expected
    (tmp_path / "cross-level-fixture.json").write_text(
        json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8"
    )
