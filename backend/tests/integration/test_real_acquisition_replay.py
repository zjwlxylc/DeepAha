import os
from pathlib import Path

import pytest

from deepaha.acquisition.recipes import load_recipe_manifest
from deepaha.acquisition.replay import (
    ControlledDirectoryStore,
    ReplayBinding,
    ReplayRunner,
    ReplayStatus,
    load_replay_manifest,
)
from deepaha.acquisition.validation import ContentValidator
from deepaha.artifacts.s3 import S3ObjectStore
from deepaha.core.settings import Settings
from deepaha.documents.html import LxmlHtmlParser
from deepaha.documents.pdf import PypdfDocumentParser
from deepaha.documents.spreadsheet import OpenpyxlSpreadsheetParser

pytestmark = pytest.mark.integration
ROOT = Path(__file__).parents[3]
MANIFEST = ROOT / "config" / "acquisition" / "real-source-corpus.v1.json"
RECIPES = ROOT / "config" / "acquisition" / "recipes.v1.json"


def test_controlled_real_corpus_replays_or_reports_explicit_blocked(tmp_path: Path) -> None:
    manifest = load_replay_manifest(MANIFEST)
    recipes = {recipe.recipe_id: recipe for recipe in load_recipe_manifest(RECIPES).recipes}
    configured_root = os.environ.get("DEEPAHA_REAL_SOURCE_CORPUS_ROOT")
    configured_backend = os.environ.get("DEEPAHA_REAL_SOURCE_CORPUS_BACKEND")
    if configured_backend == "s3":
        object_store = S3ObjectStore(Settings())
    else:
        corpus_root = Path(configured_root) if configured_root else tmp_path / "corpus-not-mounted"
        object_store = ControlledDirectoryStore(corpus_root)
    runner = ReplayRunner(
        object_store=object_store,
        validator=ContentValidator(),
        parsers=(LxmlHtmlParser(), PypdfDocumentParser(), OpenpyxlSpreadsheetParser()),
        fetcher_versions={
            "deepaha-http": "0.2.0",
            "deepaha-static-http": "1.0.0",
            "deepaha-official-alternative": "1.0.0",
        },
    )

    results = [
        runner.run(
            entry=entry,
            recipe=recipes[entry.recipe_id],
            binding=ReplayBinding(entry.source_id, entry.endpoint_id, entry.artifact_id),
        )
        for entry in manifest.entries
    ]

    if configured_root is None and configured_backend is None:
        assert results
        assert {result.status for result in results} == {ReplayStatus.BLOCKED}
        assert {result.error_code for result in results} == {"REPLAY_OBJECT_MISSING"}
    else:
        assert results
        failures = {
            str(entry.entry_id): result.error_code
            for entry, result in zip(manifest.entries, results, strict=True)
            if result.status is not ReplayStatus.PASSED
        }
        assert not failures, failures
        assert all(result.result_sha256 for result in results)
