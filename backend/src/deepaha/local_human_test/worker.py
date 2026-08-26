from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from deepaha.local_human_test.contracts import ItemStatus, RunMode
from deepaha.local_human_test.runs import HumanTestRunService

LOGGER = logging.getLogger(__name__)


class HumanTestItemProcessor(Protocol):
    def process(self, item_id: UUID) -> None: ...


@dataclass(frozen=True, slots=True)
class RoutedHumanTestItem:
    status: ItemStatus
    mode: RunMode


class HumanTestAcquisitionProcessor(Protocol):
    def acquire(
        self,
        item_id: UUID,
        mode: RunMode,
        *,
        worker_id: str,
    ) -> object: ...


class HumanTestExtractionProcessor(Protocol):
    def extract(self, item_id: UUID) -> object: ...


class RoutedHumanTestItemProcessor:
    def __init__(
        self,
        *,
        item_loader: Callable[[UUID], RoutedHumanTestItem],
        acquisition: HumanTestAcquisitionProcessor,
        extraction_factory: Callable[[UUID], HumanTestExtractionProcessor],
        worker_id: str,
    ) -> None:
        self._item_loader = item_loader
        self._acquisition = acquisition
        self._extraction_factory = extraction_factory
        self._worker_id = worker_id

    def process(self, item_id: UUID) -> None:
        item = self._item_loader(item_id)
        if item.status in {ItemStatus.CREATED, ItemStatus.ACQUIRING}:
            self._acquisition.acquire(
                item_id,
                item.mode,
                worker_id=self._worker_id,
            )
            return
        if item.status is ItemStatus.EXTRACTING:
            self._extraction_factory(item_id).extract(item_id)
            return
        raise RuntimeError("ITEM_STAGE_NOT_WORKER_OWNED")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class HumanTestWorker:
    def __init__(
        self,
        *,
        service: HumanTestRunService,
        processor: HumanTestItemProcessor,
        worker_id: str,
        clock: Callable[[], datetime] = _utc_now,
        logger: logging.Logger = LOGGER,
    ) -> None:
        self._service = service
        self._processor = processor
        self._worker_id = worker_id
        self._clock = clock
        self._logger = logger

    def run_once(self) -> bool:
        claim = self._service.claim_next(self._worker_id, now=self._clock())
        if claim is None:
            return False
        try:
            self._processor.process(claim.item_id)
        except Exception:
            self._logger.exception(
                "local human-test item processing interrupted item_id=%s "
                "code=WORKER_PROCESSING_INTERRUPTED",
                claim.item_id,
            )
            return True
        self._service.release_lease(
            claim.run_id,
            self._worker_id,
            now=self._clock(),
        )
        return True


__all__ = [
    "HumanTestItemProcessor",
    "HumanTestWorker",
    "RoutedHumanTestItem",
    "RoutedHumanTestItemProcessor",
]
