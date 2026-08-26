from pathlib import Path

from deepaha.acquisition.recipes import load_recipe_manifest
from deepaha.local_human_test.bootstrap import build_active_recipe_views
from deepaha.sources.registry import load_registry_manifest

ROOT = Path(__file__).parents[3]
RECIPES = ROOT / "config" / "acquisition" / "recipes.v1.json"
REGISTRY = ROOT / "config" / "sources" / "phase2-official-endpoints.json"


def test_active_recipe_views_are_governed_and_safe_for_the_console() -> None:
    recipes = load_recipe_manifest(RECIPES).recipes
    registry = load_registry_manifest(REGISTRY)

    views = build_active_recipe_views(recipes, registry)

    assert len(views) == 8
    assert all(view.opportunity_type_hint is not None for view in views)
    assert all(view.official_host in view.allowed_hosts for view in views)
    assert all(view.maximum_requests <= 9 for view in views)
    assert all(view.verified_at.tzinfo is not None for view in views)
    assert "api_key" not in repr(views).lower()
