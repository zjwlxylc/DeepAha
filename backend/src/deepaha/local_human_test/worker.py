from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from deepaha.local_human_test.runs import HumanTestRunService

LOGGER = logging.getLogger(__name__)


class HumanTestItemProcessor(Protocol):
    def process(self, item_id: UUID) -> None: ...


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


__all__ = ["HumanTestItemProcessor", "HumanTestWorker"]
