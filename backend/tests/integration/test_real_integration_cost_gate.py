import json
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from deepaha.acquisition.health import get_integration_cost_gate
from deepaha.acquisition.health_evidence import (
    AcquisitionEvidenceService,
    RecordIntegrationEvidenceCommand,
)
from deepaha.acquisition.recipes import load_recipe_manifest
from deepaha.sources.registry import import_registry, load_registry_manifest

pytestmark = pytest.mark.integration
ROOT = Path(__file__).parents[3]
EVIDENCE = ROOT / "config" / "acquisition" / "integration-evidence.v1.json"
RECIPES = ROOT / "config" / "acquisition" / "recipes.v1.json"
REGISTRY = ROOT / "config" / "sources" / "phase2-official-endpoints.json"


def test_first_five_real_sources_pass_persisted_integration_cost_gate(
    migrated_engine: Engine,
) -> None:
    payload: dict[str, object] = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert set(payload) == {"schema_version", "line_count_method", "entries"}
    assert payload["schema_version"] == "1.0.0"
    assert payload["line_count_method"] == "canonical-json-indent-2"
    raw_entries = payload["entries"]
    assert isinstance(raw_entries, list)
    commands = tuple(RecordIntegrationEvidenceCommand.model_validate(item) for item in raw_entries)
    assert len(commands) == 5
    assert len({command.source_id for command in commands}) == 5
    assert all(command.source_specific_production_loc == 0 for command in commands)
    assert all(command.browser_request_count == 0 for command in commands)
    assert all(command.manual_request_count == 0 for command in commands)

    recipes = {recipe.recipe_id: recipe for recipe in load_recipe_manifest(RECIPES).recipes}
    for command in commands:
        recipe = recipes[command.recipe_id]
        assert recipe.active
        assert recipe.source_id == command.source_id
        assert recipe.endpoint_id == command.endpoint_id
        canonical_lines = len(
            json.dumps(
                recipe.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            ).splitlines()
        )
        assert canonical_lines == command.recipe_line_count

    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    with factory.begin() as session:
        import_registry(session, load_registry_manifest(REGISTRY))
    service = AcquisitionEvidenceService(factory)
    for command in commands:
        service.record_integration(command)

    gate = get_integration_cost_gate(factory)

    assert gate.status == "PASS"
    assert gate.sample_count == 5
    assert gate.existing_fetcher_reuse_count == 4
    assert gate.recipe_or_thin_count == 3
    assert gate.core_schema_change_count == 0
    assert gate.existing_fetcher_reuse_ratio == pytest.approx(0.8)
    assert gate.recipe_or_thin_ratio == pytest.approx(0.6)
