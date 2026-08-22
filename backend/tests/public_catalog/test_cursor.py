from datetime import UTC, date, datetime

import pytest

from deepaha.public_catalog.cursor import InvalidCursor, decode_cursor, encode_cursor
from deepaha.public_catalog.schemas import PublicOpportunitySort
from tests.public_catalog.support import load_phase5_fixture, stable_uuid7


def test_fixture_manifest_and_deterministic_ids_are_reproducible() -> None:
    fixture = load_phase5_fixture()

    assert len(fixture.items) == 3
    assert stable_uuid7("alpha:opportunity") == stable_uuid7("alpha:opportunity")
    assert stable_uuid7("alpha:opportunity").version == 7


@pytest.mark.parametrize(
    ("sort", "key"),
    [
        (PublicOpportunitySort.PUBLISHED_DESC, datetime(2026, 8, 20, tzinfo=UTC)),
        (PublicOpportunitySort.DEADLINE_ASC, date(2026, 9, 12)),
    ],
)
def test_cursor_round_trips_with_sort_binding(
    sort: PublicOpportunitySort,
    key: date | datetime,
) -> None:
    cursor = encode_cursor(sort, key, "opp_0123456789abcdef0123456789abcdef")

    decoded = decode_cursor(cursor, sort)

    assert decoded.sort is sort
    assert decoded.key == key
    assert decoded.public_id == "opp_0123456789abcdef0123456789abcdef"


@pytest.mark.parametrize(
    "cursor",
    [
        "not-base64!",
        "e30",
        "eyJ2IjoxLCJzb3J0IjoiUFVCTElTSEVEX0RFU0MiLCJrZXkiOiJub3QtYS1kYXRlIiwicHVibGljX2lkIjoieCJ9",
        "eyJ2IjoxLCJzb3J0IjoiUFVCTElTSEVEX0RFU0MiLCJrZXkiOiIyMDI2LTA4LTIwVDAxOjAwOjAwWiIsInB1YmxpY19pZCI6IngiLCJleHRyYSI6MX0",
    ],
)
def test_cursor_rejects_malformed_or_extra_payload(cursor: str) -> None:
    with pytest.raises(InvalidCursor):
        decode_cursor(cursor, PublicOpportunitySort.PUBLISHED_DESC)


def test_cursor_rejects_a_different_selected_sort() -> None:
    cursor = encode_cursor(
        PublicOpportunitySort.PUBLISHED_DESC,
        datetime(2026, 8, 20, tzinfo=UTC),
        "opp_0123456789abcdef0123456789abcdef",
    )

    with pytest.raises(InvalidCursor, match="sort"):
        decode_cursor(cursor, PublicOpportunitySort.DEADLINE_ASC)
