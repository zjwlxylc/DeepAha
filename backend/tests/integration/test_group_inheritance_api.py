import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from deepaha.investigations.contracts import digest
from deepaha.investigations.group_applicability import read_group_rule_applicability
from deepaha.investigations.group_applicability_decisions import save_group_applicability
from deepaha.investigations.group_inheritance import preview_group_inheritance
from deepaha.investigations.group_inheritance_contracts import GroupInheritancePreview
from tests.api.test_investigations import make_client
from tests.integration.test_group_applicability_decisions import command
from tests.integration.test_group_rule_applicability import prepared
from tests.integration.test_investigation_store import StoreHarness, harness

__all__ = ["harness"]
pytestmark = pytest.mark.integration


def test_actual_preview_roundtrip_and_rehashed_tampering(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    h = harness
    args = prepared(h, monkeypatch)
    view = read_group_rule_applicability(h.store, *args, h.principal)
    save_group_applicability(h.store, args[0], command(view), h.principal, "preview-api")
    result = preview_group_inheritance(h.store, args[0], args[1], h.principal)
    (tmp_path / "group-inheritance.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    assert GroupInheritancePreview.model_validate(result).model_dump(mode="json") == result
    client, _ = make_client(tmp_path)
    monkeypatch.setattr(
        "deepaha.investigations.group_inheritance.preview_group_inheritance", lambda *a: result
    )
    with client:
        response = client.get(
            f"/api/v1/local-human-test/investigations/{args[0]}/unit-plans/{args[1]}/group-inheritance-preview"
        )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == result
    (tmp_path / "group-inheritance.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for change in ("omit", "exclude", "base", "history", "qualification"):
        bad = deepcopy(result)
        if change == "omit":
            bad["snapshot"]["group_conditions"].pop()
        if change == "exclude":
            bad["snapshot"]["group_conditions"][1]["disposition"] = "EXCLUDE"
        if change == "base":
            bad["snapshot"]["base_v2"]["context"]["check_id"] = str(args[0])
        if change == "history":
            next(
                iter(bad["dependencies"]["group_source"]["applicability_histories"].values())
            ).clear()
        if change == "qualification":
            bad["snapshot"]["overall_qualification"] = "ELIGIBLE"
        bad["dependencies_hash"] = digest(bad["dependencies"])
        bad["snapshot_hash"] = digest(bad["snapshot"])
        with pytest.raises(ValidationError):
            GroupInheritancePreview.model_validate(bad)
