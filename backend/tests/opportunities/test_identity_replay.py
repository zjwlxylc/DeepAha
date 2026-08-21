from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from deepaha.contracts.phase3 import (
    OpportunityIdentityActionType,
    OpportunityIdentityMemberRole,
)
from deepaha.opportunities.identity import (
    IdentityActionRecord,
    IdentityMemberRecord,
    IdentityReplayError,
    replay_identity_state,
    resolve_canonical_opportunity_id,
)

NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
SOURCE_ID = UUID("019b0000-0000-7000-8000-000000000001")
TARGET_ID = UUID("019b0000-0000-7000-8000-000000000002")
THIRD_ID = UUID("019b0000-0000-7000-8000-000000000003")
PARENT_ID = UUID("019b0000-0000-7000-8000-000000000004")
CHILD_ONE_ID = UUID("019b0000-0000-7000-8000-000000000005")
CHILD_TWO_ID = UUID("019b0000-0000-7000-8000-000000000006")
MERGE_ID = UUID("019b0000-0000-7000-8000-000000000010")
MERGE_TWO_ID = UUID("019b0000-0000-7000-8000-000000000011")
MERGE_REVERSAL_ID = UUID("019b0000-0000-7000-8000-000000000012")
SPLIT_ID = UUID("019b0000-0000-7000-8000-000000000013")
SPLIT_REVERSAL_ID = UUID("019b0000-0000-7000-8000-000000000014")


def member(opportunity_id: UUID, role: OpportunityIdentityMemberRole) -> IdentityMemberRecord:
    return IdentityMemberRecord(opportunity_id=opportunity_id, role=role)


def action(
    *,
    action_id: UUID,
    action_type: OpportunityIdentityActionType,
    members: tuple[IdentityMemberRecord, ...],
    occurred_at: datetime,
    reversal_of_action_id: UUID | None = None,
) -> IdentityActionRecord:
    return IdentityActionRecord(
        action_id=action_id,
        action_type=action_type,
        members=members,
        reversal_of_action_id=reversal_of_action_id,
        actor="phase3-synthetic-test",
        reason="synthetic identity correction",
        source_document_id=None,
        source_evidence_ref_id=None,
        occurred_at=occurred_at,
    )


def merge_action(
    *,
    action_id: UUID = MERGE_ID,
    source_id: UUID = SOURCE_ID,
    target_id: UUID = TARGET_ID,
    occurred_at: datetime = NOW,
) -> IdentityActionRecord:
    return action(
        action_id=action_id,
        action_type=OpportunityIdentityActionType.MERGE,
        members=(
            member(source_id, OpportunityIdentityMemberRole.SOURCE),
            member(target_id, OpportunityIdentityMemberRole.TARGET),
        ),
        occurred_at=occurred_at,
    )


def merge_reversal(
    *,
    action_id: UUID = MERGE_REVERSAL_ID,
    original: IdentityActionRecord | None = None,
) -> IdentityActionRecord:
    original = original or merge_action()
    return action(
        action_id=action_id,
        action_type=OpportunityIdentityActionType.MERGE_REVERSAL,
        members=original.members,
        reversal_of_action_id=original.action_id,
        occurred_at=original.occurred_at + timedelta(minutes=1),
    )


def split_action() -> IdentityActionRecord:
    return action(
        action_id=SPLIT_ID,
        action_type=OpportunityIdentityActionType.SPLIT,
        members=(
            member(PARENT_ID, OpportunityIdentityMemberRole.PARENT),
            member(CHILD_ONE_ID, OpportunityIdentityMemberRole.CHILD),
            member(CHILD_TWO_ID, OpportunityIdentityMemberRole.CHILD),
        ),
        occurred_at=NOW,
    )


def split_reversal() -> IdentityActionRecord:
    original = split_action()
    return action(
        action_id=SPLIT_REVERSAL_ID,
        action_type=OpportunityIdentityActionType.SPLIT_REVERSAL,
        members=original.members,
        reversal_of_action_id=original.action_id,
        occurred_at=NOW + timedelta(minutes=1),
    )


def test_merge_reversal_restores_source_public_identity_without_deleting_history() -> None:
    merged = replay_identity_state((merge_action(),))
    reversed_state = replay_identity_state((merge_action(), merge_reversal()))

    assert merged.canonical_by_opportunity[SOURCE_ID] == TARGET_ID
    assert resolve_canonical_opportunity_id(merged, SOURCE_ID) == TARGET_ID
    assert reversed_state.canonical_by_opportunity[SOURCE_ID] == SOURCE_ID
    assert reversed_state.active_action_ids == frozenset()


def test_split_reversal_removes_active_children_but_preserves_child_identities() -> None:
    state = replay_identity_state((split_action(), split_reversal()))

    assert PARENT_ID not in state.split_children_by_parent
    assert state.canonical_by_opportunity[CHILD_ONE_ID] == CHILD_ONE_ID
    assert state.canonical_by_opportunity[CHILD_TWO_ID] == CHILD_TWO_ID


def test_replay_is_deterministic_for_any_input_order() -> None:
    first = merge_action()
    second = merge_action(
        action_id=MERGE_TWO_ID,
        source_id=TARGET_ID,
        target_id=THIRD_ID,
        occurred_at=NOW + timedelta(seconds=1),
    )

    forward = replay_identity_state((first, second))
    reverse = replay_identity_state((second, first))

    assert forward == reverse
    assert resolve_canonical_opportunity_id(forward, SOURCE_ID) == THIRD_ID


def test_replay_rejects_merge_cycle() -> None:
    cycle = merge_action(
        action_id=MERGE_TWO_ID,
        source_id=TARGET_ID,
        target_id=SOURCE_ID,
        occurred_at=NOW + timedelta(seconds=1),
    )

    with pytest.raises(IdentityReplayError, match="cycle"):
        replay_identity_state((merge_action(), cycle))


def test_replay_rejects_multiple_active_targets_for_one_source() -> None:
    competing = merge_action(
        action_id=MERGE_TWO_ID,
        source_id=SOURCE_ID,
        target_id=THIRD_ID,
        occurred_at=NOW + timedelta(seconds=1),
    )

    with pytest.raises(IdentityReplayError, match="multiple active targets"):
        replay_identity_state((merge_action(), competing))


def test_replay_rejects_duplicate_reversal() -> None:
    duplicate = merge_reversal(action_id=SPLIT_REVERSAL_ID)

    with pytest.raises(IdentityReplayError, match="already reversed"):
        replay_identity_state((merge_action(), merge_reversal(), duplicate))


def test_replay_rejects_reversal_of_reversal() -> None:
    original_reversal = merge_reversal()
    invalid = action(
        action_id=SPLIT_REVERSAL_ID,
        action_type=OpportunityIdentityActionType.MERGE_REVERSAL,
        members=original_reversal.members,
        reversal_of_action_id=original_reversal.action_id,
        occurred_at=NOW + timedelta(minutes=2),
    )

    with pytest.raises(IdentityReplayError, match="reversal of a reversal"):
        replay_identity_state((merge_action(), original_reversal, invalid))


def test_replay_rejects_wrong_reversal_type() -> None:
    invalid = action(
        action_id=MERGE_REVERSAL_ID,
        action_type=OpportunityIdentityActionType.SPLIT_REVERSAL,
        members=split_action().members,
        reversal_of_action_id=MERGE_ID,
        occurred_at=NOW + timedelta(minutes=1),
    )

    with pytest.raises(IdentityReplayError, match="type"):
        replay_identity_state((merge_action(), invalid))


def test_replay_rejects_reversal_member_mismatch() -> None:
    invalid = replace(
        merge_reversal(),
        members=(
            member(THIRD_ID, OpportunityIdentityMemberRole.SOURCE),
            member(TARGET_ID, OpportunityIdentityMemberRole.TARGET),
        ),
    )

    with pytest.raises(IdentityReplayError, match="members"):
        replay_identity_state((merge_action(), invalid))


def test_replay_rejects_duplicate_action_id_even_when_timestamps_differ() -> None:
    duplicate = merge_action(occurred_at=NOW + timedelta(minutes=1))

    with pytest.raises(IdentityReplayError, match="duplicate action"):
        replay_identity_state((merge_action(), duplicate))


def test_replay_rejects_reversal_ordered_before_original() -> None:
    original = merge_action(occurred_at=NOW + timedelta(minutes=1))
    reversal = replace(merge_reversal(original=original), occurred_at=NOW)

    with pytest.raises(IdentityReplayError, match="after original"):
        replay_identity_state((original, reversal))


def test_replay_rejects_multiple_active_splits_for_one_parent() -> None:
    second = action(
        action_id=MERGE_TWO_ID,
        action_type=OpportunityIdentityActionType.SPLIT,
        members=(
            member(PARENT_ID, OpportunityIdentityMemberRole.PARENT),
            member(SOURCE_ID, OpportunityIdentityMemberRole.CHILD),
            member(TARGET_ID, OpportunityIdentityMemberRole.CHILD),
        ),
        occurred_at=NOW + timedelta(seconds=1),
    )

    with pytest.raises(IdentityReplayError, match="multiple active splits"):
        replay_identity_state((split_action(), second))
