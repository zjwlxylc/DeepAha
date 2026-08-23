import json
from fnmatch import fnmatchcase
from pathlib import Path
from urllib.parse import urlsplit

from deepaha.acquisition.contracts import FetchStrategy, SourceRecipe, SourceRecipeManifest
from deepaha.contracts.phase1 import SourceSchema, SourceTier
from deepaha.contracts.phase2 import BrowserPolicy, SourceEndpointSchema


class RecipePolicyMismatch(RuntimeError):
    def __init__(self) -> None:
        self.code = "RECIPE_POLICY_MISMATCH"
        super().__init__(self.code)


def load_recipe_manifest(path: Path) -> SourceRecipeManifest:
    content = path.read_bytes()
    if content.startswith(b"\xef\xbb\xbf"):
        raise ValueError("Recipe manifest must not contain a UTF-8 BOM")
    payload: object = json.loads(content.decode("utf-8", errors="strict"))
    return SourceRecipeManifest.model_validate(payload)


def validate_recipe_against_endpoint(
    recipe: SourceRecipe,
    source: SourceSchema,
    endpoint: SourceEndpointSchema,
) -> None:
    strategies = {step.strategy for step in recipe.fetch_plan}
    consistent = (
        recipe.source_id == source.source_id == endpoint.source_id
        and recipe.endpoint_id == endpoint.endpoint_id
        and recipe.endpoint_policy_version == endpoint.policy_version
        and recipe.allowed_hosts == endpoint.allowed_hosts
        and recipe.expected_media_types == endpoint.expected_media_types
        and recipe_allows_url(recipe, str(endpoint.url))
        and recipe.active
        and source.active
        and endpoint.active
        and (recipe.usage_role != "PRIMARY_EVIDENCE" or source.tier is SourceTier.OFFICIAL_PRIMARY)
        and (
            FetchStrategy.BROWSER not in strategies
            or endpoint.browser_policy is BrowserPolicy.FALLBACK
        )
    )
    if not consistent:
        raise RecipePolicyMismatch


def recipe_allows_url(recipe: SourceRecipe, url: str) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    return (
        parsed.scheme.lower() in {"http", "https"}
        and parsed.username is None
        and parsed.password is None
        and host in recipe.allowed_hosts
        and any(fnmatchcase(parsed.path or "/", pattern) for pattern in recipe.allowed_url_patterns)
    )


__all__ = [
    "RecipePolicyMismatch",
    "load_recipe_manifest",
    "recipe_allows_url",
    "validate_recipe_against_endpoint",
]
