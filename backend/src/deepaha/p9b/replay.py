from dataclasses import dataclass

from deepaha.p9b.hashing import model_request_hash


class ReplayVerificationError(ValueError):
    pass


@dataclass(frozen=True)
class ReplayCheckpoint:
    checkpoint_name: str
    canonical_payload: object
    observed_hash: str
    predecessor_hash: str | None


@dataclass(frozen=True)
class ReplayReport:
    checkpoint_count: int
    terminal_hash: str | None
    status: str


def replay_checkpoints(checkpoints: tuple[ReplayCheckpoint, ...]) -> ReplayReport:
    predecessor: str | None = None
    for checkpoint in checkpoints:
        if checkpoint.predecessor_hash != predecessor:
            raise ReplayVerificationError("replay predecessor lineage mismatch")
        expected = model_request_hash(
            {
                "checkpoint_name": checkpoint.checkpoint_name,
                "canonical_payload": checkpoint.canonical_payload,
                "predecessor_hash": predecessor,
            }
        )
        if checkpoint.observed_hash != expected:
            raise ReplayVerificationError("replay checkpoint hash mismatch")
        predecessor = expected
    return ReplayReport(len(checkpoints), predecessor, "PASS")


__all__ = [
    "ReplayCheckpoint",
    "ReplayReport",
    "ReplayVerificationError",
    "replay_checkpoints",
]
