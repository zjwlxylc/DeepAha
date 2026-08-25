import pytest

from deepaha.p9b.hashing import model_request_hash
from deepaha.p9b.replay import (
    ReplayCheckpoint,
    ReplayVerificationError,
    replay_checkpoints,
)


def checkpoint(name: str, payload: object, predecessor: str | None) -> ReplayCheckpoint:
    observed = model_request_hash(
        {
            "checkpoint_name": name,
            "canonical_payload": payload,
            "predecessor_hash": predecessor,
        }
    )
    return ReplayCheckpoint(name, payload, observed, predecessor)


def test_replay_recomputes_ordered_provenance_chain() -> None:
    first = checkpoint("SourceBundle", {"revision": 1}, None)
    second = checkpoint("VerifiedFactSet", {"version": 1}, first.observed_hash)

    report = replay_checkpoints((first, second))

    assert report.status == "PASS"
    assert report.terminal_hash == second.observed_hash


def test_replay_fails_closed_on_hash_or_lineage_change() -> None:
    first = checkpoint("SourceBundle", {"revision": 1}, None)
    with pytest.raises(ReplayVerificationError, match="hash"):
        replay_checkpoints((ReplayCheckpoint("SourceBundle", {}, "a" * 64, None),))
    with pytest.raises(ReplayVerificationError, match="lineage"):
        replay_checkpoints((first, checkpoint("Fact", {}, None)))
