from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from deepaha.investigations.queue_query import QueueQuery, read_queue


@pytest.mark.parametrize("cursor", ["not base64", "W10=", "e30=", "bnVsbA==", "////"])
def test_invalid_cursor_never_queries(cursor: str) -> None:
    store = Mock()
    with pytest.raises(ValueError, match="INVALID_QUEUE_CURSOR"):
        read_queue(store, QueueQuery(cursor=cursor))
    store.factory.assert_not_called()


@pytest.mark.parametrize(
    "values",
    [{"limit": 0}, {"limit": 101}, {"status": "fake"}, {"q": "x" * 201}, {"source": "fake"}],
)
def test_query_bounds(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        QueueQuery.model_validate(values)
