"""Portable current models; sources/opportunities keep the established identity tables.
No candidate facts are promoted into legacy VerifiedFact or RuleSet records.
"""
from datetime import datetime, timezone
import secrets
import time
import uuid
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now(): return datetime.now(timezone.utc)

def uid():
    # RFC 9562 UUIDv7, compatible with Python 3.13 and legacy PostgreSQL uuidv7 checks.
    ms = time.time_ns() // 1_000_000
    v = (ms << 80) | (7 << 76) | (secrets.randbits(12) << 64) | (2 << 62) | secrets.randbits(62)
    return str(uuid.UUID(int=v))

class Base(DeclarativeBase): pass

class Meta(Base):
    __tablename__='product_meta'
    key: Mapped[str]=mapped_column(String(80),primary_key=True)
    value: Mapped[str]=mapped_column(Text)

class Account(Base):
    __tablename__='product_accounts'
    id: Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uid)
    username: Mapped[str]=mapped_column(String(80),unique=True)
    password_hash: Mapped[str]=mapped_column(Text)
    roles: Mapped[list]=mapped_column(JSON)
    active: Mapped[bool]=mapped_column(Boolean,default=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class LoginSession(Base):
    __tablename__='product_sessions'
    token_hash: Mapped[str]=mapped_column(String(64),primary_key=True)
    account_id: Mapped[str]=mapped_column(ForeignKey('product_accounts.id'),index=True)
    csrf_hash: Mapped[str]=mapped_column(String(64))
    expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool]=mapped_column(Boolean,default=False)

class LoginAttempt(Base):
    __tablename__='product_login_attempts'
    key: Mapped[str]=mapped_column(String(64),primary_key=True)
    count: Mapped[int]=mapped_column(Integer,default=0)
    since: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class Invitation(Base):
    __tablename__='product_invitations'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    code_hash: Mapped[str]=mapped_column(String(64),unique=True)
    label: Mapped[str]=mapped_column(String(120))
    max_uses: Mapped[int]=mapped_column(Integer)
    used_count: Mapped[int]=mapped_column(Integer,default=0)
    expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool]=mapped_column(Boolean,default=False)
    created_by: Mapped[str]=mapped_column(String(80))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class InvitationRedemption(Base):
    __tablename__='product_invitation_redemptions'
    account_id: Mapped[str]=mapped_column(ForeignKey('product_accounts.id'),primary_key=True)
    invitation_id: Mapped[str]=mapped_column(ForeignKey('product_invitations.id'),index=True)
    notice_version: Mapped[str]=mapped_column(String(64))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class PasswordReset(Base):
    __tablename__='product_password_resets'
    token_hash: Mapped[str]=mapped_column(String(64),primary_key=True)
    account_id: Mapped[str]=mapped_column(ForeignKey('product_accounts.id'),index=True)
    expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    used: Mapped[bool]=mapped_column(Boolean,default=False)

ACCESS_TABLE_NAMES={'product_invitations','product_invitation_redemptions','product_password_resets'}

class Source(Base):
    __tablename__='sources'
    source_id: Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uid)
    public_id: Mapped[str]=mapped_column(String(36),unique=True)
    canonical_url: Mapped[str]=mapped_column(Text,unique=True)
    authority_name: Mapped[str]=mapped_column(Text)
    tier: Mapped[str]=mapped_column(String(32),default='OFFICIAL_PRIMARY')
    jurisdiction: Mapped[str|None]=mapped_column(Text,nullable=True)
    active: Mapped[bool]=mapped_column(Boolean,default=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class SourceProfile(Base):
    __tablename__='product_source_profiles'
    source_id: Mapped[str]=mapped_column(ForeignKey('sources.source_id'),primary_key=True)
    allowed_hosts: Mapped[list]=mapped_column(JSON,default=list)
    brief: Mapped[str]=mapped_column(Text,default='')
    policy_version: Mapped[int]=mapped_column(Integer,default=1)
    scheduling_enabled: Mapped[bool]=mapped_column(Boolean,default=True)
    interval_hours: Mapped[int]=mapped_column(Integer,default=0)
    last_success: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    last_failure: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    next_due: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    research_asset: Mapped[dict]=mapped_column(JSON,default=dict)

class Opportunity(Base):
    __tablename__='opportunities'
    opportunity_id: Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uid)
    public_id: Mapped[str]=mapped_column(String(36),unique=True)
    type: Mapped[str]=mapped_column(String(64),default='YOUTH_DEVELOPMENT_PROGRAM')
    canonical_title: Mapped[str]=mapped_column(Text)
    issuer_name: Mapped[str]=mapped_column(Text)
    jurisdiction: Mapped[str|None]=mapped_column(Text,nullable=True)
    current_version: Mapped[int|None]=mapped_column(Integer,nullable=True)
    status: Mapped[str]=mapped_column(String(32),default='UNKNOWN')
    publication_status: Mapped[str]=mapped_column(String(32),default='INTERNAL')
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class Identity(Base):
    __tablename__='product_opportunity_identity'
    __table_args__=(UniqueConstraint('source_id','source_key'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    source_id: Mapped[str]=mapped_column(ForeignKey('sources.source_id'))
    source_key: Mapped[str]=mapped_column(String(64))
    opportunity_id: Mapped[str]=mapped_column(ForeignKey('opportunities.opportunity_id'))

class Snapshot(Base):
    __tablename__='product_result_snapshots'
    __table_args__=(UniqueConstraint('source_id','digest'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    source_id: Mapped[str]=mapped_column(ForeignKey('sources.source_id'))
    digest: Mapped[str]=mapped_column(String(64))
    manifest: Mapped[dict]=mapped_column(JSON)
    task_id: Mapped[str|None]=mapped_column(String(36),nullable=True)
    received_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class Revision(Base):
    __tablename__='product_overview_revisions'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    snapshot_id: Mapped[str]=mapped_column(ForeignKey('product_result_snapshots.id'),unique=True)
    preview_hash: Mapped[str]=mapped_column(String(64))
    content: Mapped[dict]=mapped_column(JSON)
    status: Mapped[str]=mapped_column(String(32),default='PENDING',index=True)
    can_approve: Mapped[bool]=mapped_column(Boolean)
    policy_version: Mapped[int]=mapped_column(Integer)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class Decision(Base):
    __tablename__='product_overview_decisions'
    __table_args__=(UniqueConstraint('reviewer_id','request_key'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    revision_id: Mapped[str]=mapped_column(ForeignKey('product_overview_revisions.id'),unique=True)
    reviewer_id: Mapped[str]=mapped_column(ForeignKey('product_accounts.id'))
    request_key: Mapped[str]=mapped_column(String(128))
    decision: Mapped[str]=mapped_column(String(16))
    preview_hash: Mapped[str]=mapped_column(String(64))
    note: Mapped[str]=mapped_column(Text,default='')
    receipt: Mapped[dict]=mapped_column(JSON)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class Publication(Base):
    __tablename__='product_overview_publications'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    opportunity_id: Mapped[str]=mapped_column(ForeignKey('opportunities.opportunity_id'),index=True)
    decision_id: Mapped[str]=mapped_column(ForeignKey('product_overview_decisions.id'))
    revision_id: Mapped[str]=mapped_column(ForeignKey('product_overview_revisions.id'))
    content: Mapped[dict]=mapped_column(JSON)
    status: Mapped[str]=mapped_column(String(32),default='CURRENT',index=True)
    invalidated_fields: Mapped[list]=mapped_column(JSON,default=list)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class Task(Base):
    __tablename__='product_tasks'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    source_id: Mapped[str]=mapped_column(ForeignKey('sources.source_id'))
    creator_id: Mapped[str]=mapped_column(ForeignKey('product_accounts.id'))
    notice_url: Mapped[str]=mapped_column(Text)
    status: Mapped[str]=mapped_column(String(32),default='QUEUED',index=True)
    kind: Mapped[str]=mapped_column(String(32),default='INVESTIGATE')
    instruction: Mapped[str]=mapped_column(Text,default='')
    runtime_id: Mapped[str|None]=mapped_column(String(128),nullable=True)
    session_id: Mapped[str|None]=mapped_column(String(128),nullable=True)
    workspace: Mapped[str]=mapped_column(Text,default='')
    remote_binding: Mapped[dict]=mapped_column(JSON,default=dict)
    stage: Mapped[str]=mapped_column(String(32),default='WAITING')
    error_code: Mapped[str|None]=mapped_column(String(128),nullable=True)
    budget_seconds: Mapped[int]=mapped_column(Integer,default=1200)
    attempts: Mapped[int]=mapped_column(Integer,default=0)
    revision_id: Mapped[str|None]=mapped_column(String(36),nullable=True)
    files: Mapped[dict]=mapped_column(JSON,default=dict)
    request_key: Mapped[str]=mapped_column(String(128),unique=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class Profile(Base):
    __tablename__='product_profiles'
    account_id: Mapped[str]=mapped_column(ForeignKey('product_accounts.id'),primary_key=True)
    data: Mapped[dict]=mapped_column(JSON,default=dict)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class Action(Base):
    __tablename__='product_actions'
    __table_args__=(UniqueConstraint('account_id','opportunity_id'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    account_id: Mapped[str]=mapped_column(ForeignKey('product_accounts.id'),index=True)
    opportunity_id: Mapped[str]=mapped_column(ForeignKey('opportunities.opportunity_id'))
    status: Mapped[str]=mapped_column(String(32),default='SAVED')
    note: Mapped[str]=mapped_column(Text,default='')
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class Feedback(Base):
    __tablename__='product_feedback'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    account_id: Mapped[str]=mapped_column(ForeignKey('product_accounts.id'),index=True)
    opportunity_id: Mapped[str]=mapped_column(ForeignKey('opportunities.opportunity_id'))
    data: Mapped[dict]=mapped_column(JSON)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class Notice(Base):
    __tablename__='product_notices'
    __table_args__=(UniqueConstraint('account_id','dedupe_key'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    account_id: Mapped[str]=mapped_column(ForeignKey('product_accounts.id'),index=True)
    opportunity_id: Mapped[str|None]=mapped_column(ForeignKey('opportunities.opportunity_id'),nullable=True)
    publication_id: Mapped[str|None]=mapped_column(String(36),nullable=True)
    title: Mapped[str]=mapped_column(Text)
    body: Mapped[str]=mapped_column(Text)
    kind: Mapped[str]=mapped_column(String(32),default='CHANGE')
    dedupe_key: Mapped[str]=mapped_column(String(160))
    due_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    state: Mapped[str]=mapped_column(String(24),default='UNREAD')
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)


class OpportunityUnit(Base):
    __tablename__='product_opportunity_units'
    __table_args__=(UniqueConstraint('opportunity_id','stable_key'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    opportunity_id: Mapped[str]=mapped_column(ForeignKey('opportunities.opportunity_id'),index=True)
    public_id: Mapped[str]=mapped_column(String(48),unique=True,index=True)
    stable_key: Mapped[str]=mapped_column(String(512))
    kind: Mapped[str]=mapped_column(String(32))
    name: Mapped[str]=mapped_column(Text)
    code: Mapped[str]=mapped_column(String(120),default='')
    parent_id: Mapped[str|None]=mapped_column(ForeignKey('product_opportunity_units.id'),nullable=True)
    identity_strength: Mapped[str]=mapped_column(String(24),default='WEAK')
    source_path: Mapped[str]=mapped_column(Text,default='')
    first_revision_id: Mapped[str]=mapped_column(String(36))
    current_revision_id: Mapped[str]=mapped_column(String(36))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class CatalogTarget(Base):
    __tablename__='product_catalog_targets'
    __table_args__=(UniqueConstraint('publication_id','public_id'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    public_id: Mapped[str]=mapped_column(String(48),index=True)
    opportunity_id: Mapped[str]=mapped_column(ForeignKey('opportunities.opportunity_id'),index=True)
    unit_id: Mapped[str|None]=mapped_column(ForeignKey('product_opportunity_units.id'),nullable=True,index=True)
    publication_id: Mapped[str]=mapped_column(ForeignKey('product_overview_publications.id'),index=True)
    revision_id: Mapped[str]=mapped_column(ForeignKey('product_overview_revisions.id'),index=True)
    content: Mapped[dict]=mapped_column(JSON)
    status: Mapped[str]=mapped_column(String(32),default='CURRENT',index=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class TargetAction(Base):
    __tablename__='product_target_actions'
    __table_args__=(UniqueConstraint('account_id','target_public_id'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    account_id: Mapped[str]=mapped_column(ForeignKey('product_accounts.id'),index=True)
    target_public_id: Mapped[str]=mapped_column(String(48),index=True)
    opportunity_id: Mapped[str]=mapped_column(ForeignKey('opportunities.opportunity_id'),index=True)
    status: Mapped[str]=mapped_column(String(32),default='SAVED')
    note: Mapped[str]=mapped_column(Text,default='')
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class TargetFeedback(Base):
    __tablename__='product_target_feedback'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    account_id: Mapped[str]=mapped_column(ForeignKey('product_accounts.id'),index=True)
    target_public_id: Mapped[str]=mapped_column(String(48),index=True)
    opportunity_id: Mapped[str]=mapped_column(ForeignKey('opportunities.opportunity_id'),index=True)
    data: Mapped[dict]=mapped_column(JSON)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)



class TargetActionEvent(Base):
    __tablename__='product_target_action_events'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    account_id: Mapped[str]=mapped_column(ForeignKey('product_accounts.id'),index=True)
    target_public_id: Mapped[str]=mapped_column(String(48),index=True)
    opportunity_id: Mapped[str]=mapped_column(ForeignKey('opportunities.opportunity_id'),index=True)
    from_status: Mapped[str|None]=mapped_column(String(32),nullable=True)
    to_status: Mapped[str]=mapped_column(String(32))
    note: Mapped[str]=mapped_column(Text,default='')
    event_type: Mapped[str]=mapped_column(String(32),default='STATUS')
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,index=True)

class FeedbackCandidate(Base):
    __tablename__='product_feedback_candidates'
    __table_args__=(UniqueConstraint('feedback_id'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    feedback_id: Mapped[str]=mapped_column(ForeignKey('product_target_feedback.id'),index=True)
    target_public_id: Mapped[str]=mapped_column(String(48),index=True)
    opportunity_id: Mapped[str]=mapped_column(ForeignKey('opportunities.opportunity_id'),index=True)
    candidate_kind: Mapped[str]=mapped_column(String(32),default='USER_FEEDBACK')
    state: Mapped[str]=mapped_column(String(24),default='CANDIDATE',index=True)
    data: Mapped[dict]=mapped_column(JSON)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,index=True)

class TargetNotice(Base):
    __tablename__='product_target_notices'
    __table_args__=(UniqueConstraint('account_id','dedupe_key'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    account_id: Mapped[str]=mapped_column(ForeignKey('product_accounts.id'),index=True)
    target_public_id: Mapped[str]=mapped_column(String(48),index=True)
    opportunity_id: Mapped[str]=mapped_column(ForeignKey('opportunities.opportunity_id'),index=True)
    catalog_target_id: Mapped[str|None]=mapped_column(String(36),nullable=True)
    title: Mapped[str]=mapped_column(Text)
    body: Mapped[str]=mapped_column(Text)
    kind: Mapped[str]=mapped_column(String(32),default='CHANGE')
    dedupe_key: Mapped[str]=mapped_column(String(160))
    due_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    state: Mapped[str]=mapped_column(String(24),default='UNREAD')
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class Audit(Base):
    __tablename__='product_audit'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    actor: Mapped[str]=mapped_column(String(80))
    action: Mapped[str]=mapped_column(String(80))
    target: Mapped[str]=mapped_column(String(128))
    summary: Mapped[str]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class ImportRecord(Base):
    __tablename__='product_import_records'
    digest: Mapped[str]=mapped_column(String(64),primary_key=True)
    actor: Mapped[str]=mapped_column(String(80))
    asset: Mapped[dict]=mapped_column(JSON)
    receipt: Mapped[dict]=mapped_column(JSON)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

# SG7 Opportunity Lab tables are intentionally isolated from production facts,
# review decisions and qualification rules. Lab records can measure the current
# product but can never publish or approve an Opportunity.
class LabGoldCase(Base):
    __tablename__='product_lab_gold_cases'
    __table_args__=(UniqueConstraint('catalog_target_id','split','truth_origin'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    catalog_target_id: Mapped[str]=mapped_column(ForeignKey('product_catalog_targets.id'),index=True)
    target_public_id: Mapped[str]=mapped_column(String(48),index=True)
    opportunity_id: Mapped[str]=mapped_column(ForeignKey('opportunities.opportunity_id'),index=True)
    publication_id: Mapped[str]=mapped_column(String(36),index=True)
    revision_id: Mapped[str]=mapped_column(String(36),index=True)
    snapshot_hash: Mapped[str]=mapped_column(String(64))
    snapshot: Mapped[dict]=mapped_column(JSON)
    split: Mapped[str]=mapped_column(String(32),default='CALIBRATION',index=True)
    truth_origin: Mapped[str]=mapped_column(String(40),default='ENGINEERING_FIXTURE',index=True)
    annotation: Mapped[dict]=mapped_column(JSON,default=dict)
    attestation_ref: Mapped[str|None]=mapped_column(String(160),nullable=True)
    state: Mapped[str]=mapped_column(String(24),default='DRAFT',index=True)
    created_by: Mapped[str]=mapped_column(ForeignKey('product_accounts.id'))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,index=True)
    locked_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    retired_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)

class LabTwin(Base):
    __tablename__='product_lab_twins'
    __table_args__=(UniqueConstraint('twin_key','version'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    twin_key: Mapped[str]=mapped_column(String(64),index=True)
    version: Mapped[int]=mapped_column(Integer,default=1)
    label: Mapped[str]=mapped_column(String(160))
    archetype: Mapped[str]=mapped_column(String(64),index=True)
    profile: Mapped[dict]=mapped_column(JSON)
    profile_hash: Mapped[str]=mapped_column(String(64))
    active: Mapped[bool]=mapped_column(Boolean,default=True,index=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,index=True)

class LabPairTruth(Base):
    __tablename__='product_lab_pair_truths'
    __table_args__=(UniqueConstraint('gold_case_id','twin_id'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    gold_case_id: Mapped[str]=mapped_column(ForeignKey('product_lab_gold_cases.id'),index=True)
    twin_id: Mapped[str]=mapped_column(ForeignKey('product_lab_twins.id'),index=True)
    expected_eligibility: Mapped[str|None]=mapped_column(String(32),nullable=True)
    expected_recommendation: Mapped[str|None]=mapped_column(String(24),nullable=True)
    truth_origin: Mapped[str]=mapped_column(String(40),default='OPERATOR_ANNOTATED',index=True)
    attestation_ref: Mapped[str|None]=mapped_column(String(160),nullable=True)
    note: Mapped[str]=mapped_column(Text,default='')
    state: Mapped[str]=mapped_column(String(24),default='LOCKED',index=True)
    created_by: Mapped[str]=mapped_column(ForeignKey('product_accounts.id'))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,index=True)

class LabRun(Base):
    __tablename__='product_lab_runs'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    kind: Mapped[str]=mapped_column(String(32),index=True)
    status: Mapped[str]=mapped_column(String(24),default='RUNNING',index=True)
    label: Mapped[str]=mapped_column(String(200),default='')
    manifest: Mapped[dict]=mapped_column(JSON,default=dict)
    metrics: Mapped[dict]=mapped_column(JSON,default=dict)
    created_by: Mapped[str]=mapped_column(ForeignKey('product_accounts.id'))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,index=True)
    finished_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)

class LabRunResult(Base):
    __tablename__='product_lab_run_results'
    __table_args__=(UniqueConstraint('run_id','twin_id','catalog_target_id'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    run_id: Mapped[str]=mapped_column(ForeignKey('product_lab_runs.id'),index=True)
    twin_id: Mapped[str]=mapped_column(ForeignKey('product_lab_twins.id'),index=True)
    gold_case_id: Mapped[str|None]=mapped_column(ForeignKey('product_lab_gold_cases.id'),nullable=True,index=True)
    catalog_target_id: Mapped[str]=mapped_column(ForeignKey('product_catalog_targets.id'),index=True)
    target_public_id: Mapped[str]=mapped_column(String(48),index=True)
    eligibility_status: Mapped[str]=mapped_column(String(32),index=True)
    qualification_gate: Mapped[str]=mapped_column(String(32),default='NORMAL')
    priority_band: Mapped[str]=mapped_column(String(32),default='EXPLORE')
    expected_eligibility: Mapped[str|None]=mapped_column(String(32),nullable=True)
    expected_recommendation: Mapped[str|None]=mapped_column(String(24),nullable=True)
    truth_origin: Mapped[str|None]=mapped_column(String(40),nullable=True)
    correct: Mapped[bool|None]=mapped_column(Boolean,nullable=True)
    recommendation_correct: Mapped[bool|None]=mapped_column(Boolean,nullable=True)
    detail: Mapped[dict]=mapped_column(JSON,default=dict)

class LabEnrollment(Base):
    __tablename__='product_lab_enrollments'
    account_id: Mapped[str]=mapped_column(ForeignKey('product_accounts.id'),primary_key=True)
    status: Mapped[str]=mapped_column(String(24),default='ACTIVE',index=True)
    cohort: Mapped[str]=mapped_column(String(64),default='FOUNDING_USER_V1')
    consent_version: Mapped[str]=mapped_column(String(64),default='sg7-opportunity-lab-v1')
    joined_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,index=True)
    withdrawn_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)

class LabExposure(Base):
    __tablename__='product_lab_exposures'
    __table_args__=(UniqueConstraint('account_id','target_public_id','publication_id'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    account_id: Mapped[str]=mapped_column(ForeignKey('product_accounts.id'),index=True)
    target_public_id: Mapped[str]=mapped_column(String(48),index=True)
    publication_id: Mapped[str]=mapped_column(String(36),index=True)
    catalog_target_id: Mapped[str]=mapped_column(String(36),index=True)
    first_seen_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,index=True)

LAB_TABLE_NAMES={
    'product_lab_gold_cases','product_lab_pair_truths','product_lab_twins','product_lab_runs','product_lab_run_results',
    'product_lab_enrollments','product_lab_exposures',
}


# Experience extension tables are additive: no columns or facts in legacy tables change.
class ProfileRevision(Base):
    __tablename__='product_profile_revisions'
    account_id: Mapped[str]=mapped_column(ForeignKey('product_accounts.id'),primary_key=True)
    version: Mapped[int]=mapped_column(Integer,default=0)

class PreparationItem(Base):
    __tablename__='product_preparation_items'
    __table_args__=(UniqueConstraint('account_id','request_key'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    account_id: Mapped[str]=mapped_column(ForeignKey('product_accounts.id'),index=True)
    target_public_id: Mapped[str]=mapped_column(String(64),index=True)
    text: Mapped[str]=mapped_column(String(500))
    done: Mapped[bool]=mapped_column(Boolean,default=False)
    origin: Mapped[str]=mapped_column(String(32),default='USER')
    publication_id: Mapped[str]=mapped_column(String(64))
    field_id: Mapped[str|None]=mapped_column(String(128),nullable=True)
    request_key: Mapped[str]=mapped_column(String(128))
    version: Mapped[int]=mapped_column(Integer,default=1)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

EXPERIENCE_TABLE_NAMES={'product_profile_revisions','product_preparation_items'}


class DispatchPolicy(Base):
    __tablename__='product_dispatch_policies'
    connection_ref: Mapped[str]=mapped_column(String(48),primary_key=True)
    version: Mapped[int]=mapped_column(Integer,default=0)
    mode: Mapped[str]=mapped_column(String(16),default='SERIAL')
    max_concurrent: Mapped[int]=mapped_column(Integer,default=1)
    domain_limit: Mapped[int]=mapped_column(Integer,default=1)
    queue_limit: Mapped[int]=mapped_column(Integer,default=20)
    task_budget_seconds: Mapped[int]=mapped_column(Integer,default=1200)
    new_dispatch_enabled: Mapped[bool]=mapped_column(Boolean,default=True)
    observed_fingerprint: Mapped[str]=mapped_column(String(64),default='')
    published_model: Mapped[str]=mapped_column(String(256),default='')
    release_evidence: Mapped[dict]=mapped_column(JSON,default=dict)
    inspected_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)

class DispatchValidation(Base):
    __tablename__='product_dispatch_validations'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    connection_ref: Mapped[str]=mapped_column(String(48),index=True)
    binding_fingerprint: Mapped[str]=mapped_column(String(64))
    parallel: Mapped[int]=mapped_column(Integer)
    origin: Mapped[str]=mapped_column(String(16))
    passed: Mapped[bool]=mapped_column(Boolean,default=False)
    report_sha256: Mapped[str]=mapped_column(String(64))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class TaskDispatch(Base):
    __tablename__='product_task_dispatches'
    task_id: Mapped[str]=mapped_column(ForeignKey('product_tasks.id'),primary_key=True)
    connection_ref: Mapped[str]=mapped_column(String(48),default='default',index=True)
    binding_fingerprint: Mapped[str]=mapped_column(String(64),default='')
    model_name: Mapped[str]=mapped_column(String(256),default='')
    policy_snapshot: Mapped[dict]=mapped_column(JSON,default=dict)
    lease_owner: Mapped[str|None]=mapped_column(String(128),nullable=True)
    lease_expires_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    prompt_started: Mapped[bool]=mapped_column(Boolean,default=False)
    remote_pending: Mapped[bool]=mapped_column(Boolean,default=False)

EXPERIENCE_TABLE_NAMES |= {'product_dispatch_policies','product_dispatch_validations','product_task_dispatches'}
