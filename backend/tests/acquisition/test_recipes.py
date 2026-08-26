import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from deepaha.acquisition.contracts import SourceRecipeManifest
from deepaha.acquisition.recipes import (
    RecipePolicyMismatch,
    load_recipe_manifest,
    validate_recipe_against_endpoint,
)
from deepaha.sources.registry import load_registry_manifest

FIXTURES = Path(__file__).parents[1] / "fixtures" / "acquisition"
VALID = FIXTURES / "recipes-valid.json"
INVALID = FIXTURES / "recipes-invalid.json"
REGISTRY = Path(__file__).parents[1] / "fixtures" / "sources" / "registry-valid.json"
PRODUCTION = Path(__file__).parents[3] / "config" / "acquisition" / "recipes.v1.json"


def valid_payload() -> dict[str, object]:
    value: object = json.loads(VALID.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def first_recipe(payload: dict[str, object]) -> dict[str, object]:
    recipes = payload["recipes"]
    assert isinstance(recipes, list)
    recipe = recipes[0]
    assert isinstance(recipe, dict)
    return recipe


def write_payload(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_recipe_manifest_accepts_strict_versioned_json() -> None:
    manifest = load_recipe_manifest(VALID)

    assert manifest.schema_version == "1.0.0"
    assert len(manifest.recipes) == 1
    recipe = manifest.recipes[0]
    assert recipe.usage_role == "PRIMARY_EVIDENCE"
    assert recipe.endpoint_policy_version == "2026-08-21.1"
    assert recipe.allowed_hosts == ("notices.example.gov",)
    assert [step.strategy.value for step in recipe.fetch_plan] == ["STATIC_HTTP"]
    assert recipe.discovery.detail_limit == 20
    assert recipe.health.zero_discovery_grace_runs == 1


def test_production_manifest_tracks_only_qualified_platform_candidates() -> None:
    manifest = load_recipe_manifest(PRODUCTION)
    assert len(manifest.recipes) == 20
    assert sum(recipe.active for recipe in manifest.recipes) == 8
    assert {step.strategy.value for recipe in manifest.recipes for step in recipe.fetch_plan} == {
        "STATIC_HTTP",
        "OFFICIAL_ALTERNATIVE",
    }
    assert all(
        recipe.opportunity_type_hint is not None for recipe in manifest.recipes if recipe.active
    )


def test_recipe_rejects_unknown_opportunity_type_hint() -> None:
    payload = valid_payload()
    first_recipe(payload)["opportunity_type_hint"] = "MODEL_INFERRED_TYPE"

    with pytest.raises(ValidationError):
        SourceRecipeManifest.model_validate(payload)


def test_recipe_loader_rejects_utf8_bom_and_secrets_or_executable_keys(tmp_path: Path) -> None:
    bom = tmp_path / "bom.json"
    bom.write_bytes(b"\xef\xbb\xbf" + VALID.read_bytes())
    with pytest.raises(ValueError, match="UTF-8 BOM"):
        load_recipe_manifest(bom)

    with pytest.raises(ValidationError):
        load_recipe_manifest(INVALID)

    for forbidden_key in ("headers", "credentials", "plugin_path", "python_callable"):
        payload = valid_payload()
        first_recipe(payload)[forbidden_key] = "forbidden"
        path = tmp_path / f"{forbidden_key}.json"
        write_payload(path, payload)
        with pytest.raises(ValidationError):
            load_recipe_manifest(path)


def test_manifest_rejects_duplicate_recipe_identity_and_endpoint_version() -> None:
    payload = valid_payload()
    recipes = payload["recipes"]
    assert isinstance(recipes, list)
    recipes.append(deepcopy(recipes[0]))

    with pytest.raises(ValidationError, match="duplicate"):
        SourceRecipeManifest.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("maximum_requests", 26),
        ("maximum_elapsed_seconds", 301),
        ("fetch_plan", []),
        (
            "fetch_plan",
            [{"strategy": "STATIC_HTTP", "fallback_on": ["CAPTCHA_REQUIRED"]}],
        ),
    ],
)
def test_recipe_rejects_unbounded_or_unsafe_fetch_plan(field: str, value: object) -> None:
    payload = valid_payload()
    first_recipe(payload)[field] = value
    with pytest.raises(ValidationError):
        SourceRecipeManifest.model_validate(payload)


def test_discovery_shape_is_consistent_with_kind_and_limits() -> None:
    payload = valid_payload()
    recipe = first_recipe(payload)
    discovery = recipe["discovery"]
    assert isinstance(discovery, dict)
    discovery["kind"] = "NONE"

    with pytest.raises(ValidationError):
        SourceRecipeManifest.model_validate(payload)


def test_recipe_replays_registered_endpoint_policy_without_changing_source_tier() -> None:
    recipe = load_recipe_manifest(VALID).recipes[0]
    registry = load_registry_manifest(REGISTRY).sources[0]

    validate_recipe_against_endpoint(recipe, registry.source, registry.endpoints[0])

    assert registry.source.tier == "OFFICIAL_PRIMARY"
    assert recipe.usage_role == "PRIMARY_EVIDENCE"


def test_primary_evidence_role_requires_official_primary_source() -> None:
    recipe = load_recipe_manifest(VALID).recipes[0]
    registry = load_registry_manifest(REGISTRY).sources[0]
    secondary = registry.source.model_copy(update={"tier": "TRUSTED_SECONDARY"})

    with pytest.raises(RecipePolicyMismatch, match="RECIPE_POLICY_MISMATCH"):
        validate_recipe_against_endpoint(recipe, secondary, registry.endpoints[0])


def test_browser_strategy_requires_endpoint_fallback_policy() -> None:
    payload = valid_payload()
    first_recipe(payload)["fetch_plan"] = [{"strategy": "BROWSER", "fallback_on": []}]
    recipe = SourceRecipeManifest.model_validate(payload).recipes[0]
    registry = load_registry_manifest(REGISTRY).sources[0]

    with pytest.raises(RecipePolicyMismatch, match="RECIPE_POLICY_MISMATCH"):
        validate_recipe_against_endpoint(recipe, registry.source, registry.endpoints[0])


def test_recipe_endpoint_identity_and_active_state_are_mandatory() -> None:
    recipe = load_recipe_manifest(VALID).recipes[0]
    registry = load_registry_manifest(REGISTRY).sources[0]
    inactive = registry.endpoints[0].model_copy(update={"active": False})

    with pytest.raises(RecipePolicyMismatch, match="RECIPE_POLICY_MISMATCH"):
        validate_recipe_against_endpoint(recipe, registry.source, inactive)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("endpoint_policy_version", "different-policy"),
        ("allowed_hosts", ["other.example.gov"]),
        ("expected_media_types", ["application/xhtml+xml"]),
        ("allowed_url_patterns", ["/notice/*"]),
    ],
)
def test_recipe_must_exactly_replay_endpoint_policy(
    field: str,
    value: object,
) -> None:
    payload = valid_payload()
    first_recipe(payload)[field] = value
    recipe = SourceRecipeManifest.model_validate(payload).recipes[0]
    registry = load_registry_manifest(REGISTRY).sources[0]

    with pytest.raises(RecipePolicyMismatch, match="RECIPE_POLICY_MISMATCH"):
        validate_recipe_against_endpoint(recipe, registry.source, registry.endpoints[0])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("zero_discovery_grace_runs", 11),
        ("consecutive_failure_limit", 0),
        ("selector_drift_grace_runs", 11),
    ],
)
def test_health_thresholds_are_finite(field: str, value: object) -> None:
    payload = valid_payload()
    health = first_recipe(payload)["health"]
    assert isinstance(health, dict)
    health[field] = value

    with pytest.raises(ValidationError):
        SourceRecipeManifest.model_validate(payload)


def test_allowed_url_patterns_are_path_only_and_media_shape_matches_discovery() -> None:
    payload = valid_payload()
    first_recipe(payload)["allowed_url_patterns"] = ["https://notices.example.gov/*"]
    with pytest.raises(ValidationError, match="path-only"):
        SourceRecipeManifest.model_validate(payload)

    payload = valid_payload()
    first_recipe(payload)["expected_media_types"] = ["application/json"]
    with pytest.raises(ValidationError, match="HTML discovery"):
        SourceRecipeManifest.model_validate(payload)
