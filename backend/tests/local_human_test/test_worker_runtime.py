import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import create_engine

from deepaha.core.settings import Settings
from deepaha.local_human_test import runtime
from deepaha.local_human_test.contracts import ItemStatus, RunMode
from deepaha.local_human_test.worker import RoutedHumanTestItem, RoutedHumanTestItemProcessor

ITEM_ID = UUID("019d0000-0000-7000-8000-000000000701")


def test_worker_runtime_registers_all_local_run_foreign_key_targets() -> None:
    backend_root = Path(__file__).parents[2]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(backend_root / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import deepaha.local_human_test.runtime; "
                "from deepaha.local_human_test.models import "
                "LocalHumanTestItem, LocalHumanTestRun; "
                "[foreign_key.column for table in "
                "(LocalHumanTestRun.__table__, LocalHumanTestItem.__table__) "
                "for foreign_key in table.foreign_keys]"
            ),
        ],
        cwd=backend_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_live_acquisition_html_parser_emits_p9b_document_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_parsers: list[object] = []
    real_document_service = runtime.DocumentService

    class CapturingDocumentService(real_document_service):
        def __init__(self, **kwargs: object) -> None:
            captured_parsers.extend(kwargs["parsers"])  # type: ignore[arg-type]
            super().__init__(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(runtime, "DocumentService", CapturingDocumentService)
    monkeypatch.setattr(runtime, "get_engine", lambda _settings: create_engine("sqlite://"))
    worker = runtime.build_human_test_worker(
        Settings(
            environment="development",
            local_human_test_enabled=True,
            local_human_test_root=tmp_path,
            local_human_test_bind_host="127.0.0.1",
            database_url="postgresql+psycopg://unused.invalid/deepaha",
        )
    )
    acquisition = worker._processor._acquisition  # type: ignore[attr-defined]
    acquisition._live_runner_factory(lambda: None)  # type: ignore[attr-defined]
    html_parser = next(
        parser for parser in captured_parsers if parser.supports("text/html")  # type: ignore[attr-defined]
    )
    content = b"<html><body><main><p>Official opportunity notice</p></main></body></html>"

    parsed = html_parser.parse(  # type: ignore[attr-defined]
        content,
        artifact_sha256=sha256(content).hexdigest(),
    )

    assert parsed.blocks


class Acquisition:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, RunMode, str]] = []

    def acquire(self, item_id: UUID, mode: RunMode, *, worker_id: str) -> object:
        self.calls.append((item_id, mode, worker_id))
        return object()


class Extraction:
    def __init__(self) -> None:
        self.calls: list[UUID] = []

    def extract(self, item_id: UUID) -> object:
        self.calls.append(item_id)
        return object()


def test_processor_routes_created_item_to_governed_acquisition() -> None:
    acquisition = Acquisition()
    extraction = Extraction()
    processor = RoutedHumanTestItemProcessor(
        item_loader=lambda _item_id: RoutedHumanTestItem(
            status=ItemStatus.CREATED,
            mode=RunMode.LIVE_OFFICIAL,
        ),
        acquisition=acquisition,
        extraction_factory=lambda _item_id: extraction,
        worker_id="local-worker",
    )

    processor.process(ITEM_ID)

    assert acquisition.calls == [(ITEM_ID, RunMode.LIVE_OFFICIAL, "local-worker")]
    assert extraction.calls == []


def test_processor_routes_extracting_item_to_fresh_provider_bound_extractor() -> None:
    acquisition = Acquisition()
    first = Extraction()
    second = Extraction()
    extractors = iter((first, second))
    processor = RoutedHumanTestItemProcessor(
        item_loader=lambda _item_id: RoutedHumanTestItem(
            status=ItemStatus.EXTRACTING,
            mode=RunMode.LIVE_OFFICIAL,
        ),
        acquisition=acquisition,
        extraction_factory=lambda _item_id: next(extractors),
        worker_id="local-worker",
    )

    processor.process(ITEM_ID)
    processor.process(ITEM_ID)

    assert acquisition.calls == []
    assert first.calls == [ITEM_ID]
    assert second.calls == [ITEM_ID]


def test_processor_refuses_human_owned_stage() -> None:
    processor = RoutedHumanTestItemProcessor(
        item_loader=lambda _item_id: RoutedHumanTestItem(
            status=ItemStatus.BOOTSTRAP_REVIEW,
            mode=RunMode.LIVE_OFFICIAL,
        ),
        acquisition=Acquisition(),
        extraction_factory=lambda _item_id: Extraction(),
        worker_id="local-worker",
    )

    with pytest.raises(RuntimeError, match="ITEM_STAGE_NOT_WORKER_OWNED"):
        processor.process(ITEM_ID)
