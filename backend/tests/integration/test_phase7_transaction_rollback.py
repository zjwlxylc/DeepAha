from typing import cast

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.feedback.models import (
    FeedbackEventModel,
    FeedbackEvidenceLinkModel,
    FeedbackIdempotencyRecordModel,
)
from deepaha.feedback.schemas import FeedbackSubmissionWrite
from deepaha.feedback.service import FeedbackService
from deepaha.personal.auth import Principal
from deepaha.review.models import FeedbackReviewCaseSnapshotModel
from tests.feedback.support import (
    NOW,
    load_phase7_feedback_fixture,
    persist_feedback_prerequisites,
    protected_fact_counts,
    protected_fact_digest,
    submission_body,
)

pytestmark = pytest.mark.integration


class CommitFailureSession(Session):
    def commit(self) -> None:
        raise RuntimeError("synthetic commit failure")


def test_feedback_submit_rolls_back_every_phase7_row_on_commit_failure(
    migrated_engine: Engine,
) -> None:
    fixture = load_phase7_feedback_fixture()
    with Session(migrated_engine) as session:
        owner, _ = persist_feedback_prerequisites(session)
        before_digest = protected_fact_digest(session)
        before_counts = protected_fact_counts(session)
        session.commit()
    failing_factory = cast(
        sessionmaker[Session],
        sessionmaker(
            bind=migrated_engine,
            class_=CommitFailureSession,
            expire_on_commit=False,
        ),
    )
    service = FeedbackService(session_factory=failing_factory, now_factory=lambda: NOW)

    with pytest.raises(RuntimeError, match="synthetic commit failure"):
        service.submit(
            Principal(user_id=owner.user_id),
            owner.opportunity_public_id,
            FeedbackSubmissionWrite.model_validate(
                submission_body(
                    owner,
                    user_statement=fixture.feedback.user_statement,
                    initial_evidence_ref_ids=[owner.evidence_ref_id],
                )
            ),
            idempotency_key="phase7-rollback-submit-0001",
        )

    with Session(migrated_engine) as session:
        assert protected_fact_digest(session) == before_digest
        assert protected_fact_counts(session) == before_counts
        for model in (
            FeedbackEventModel,
            FeedbackEvidenceLinkModel,
            FeedbackIdempotencyRecordModel,
            FeedbackReviewCaseSnapshotModel,
        ):
            assert session.scalar(select(func.count()).select_from(model)) == 0
