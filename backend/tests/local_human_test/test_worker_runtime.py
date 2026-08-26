from uuid import UUID

import pytest

from deepaha.local_human_test.contracts import ItemStatus, RunMode
from deepaha.local_human_test.worker import RoutedHumanTestItem, RoutedHumanTestItemProcessor

ITEM_ID = UUID("019d0000-0000-7000-8000-000000000701")


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
