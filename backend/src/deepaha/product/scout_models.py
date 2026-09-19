"""Additive research intake tables; official Source identity remains in sources."""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base, now, uid

class ScoutBatch(Base):
    __tablename__ = 'product_scout_batches'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    package_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    bundle_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(200))
    format: Mapped[str] = mapped_column(String(100), default='UNKNOWN')
    status: Mapped[str] = mapped_column(String(20), default='PREPARING')
    actor: Mapped[str] = mapped_column(String(80))
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    projection: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    receipt: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ScoutRun(Base):
    __tablename__ = 'product_scout_runs'
    __table_args__ = (UniqueConstraint('epoch', 'namespace', 'run_key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    epoch: Mapped[str] = mapped_column(String(36))
    namespace: Mapped[str] = mapped_column(String(80))
    run_key: Mapped[str] = mapped_column(String(120))
    sha256: Mapped[str] = mapped_column(String(64))
    batch_id: Mapped[str] = mapped_column(ForeignKey('product_scout_batches.id'))
    payload: Mapped[dict] = mapped_column(JSON)

class ScoutCandidate(Base):
    __tablename__ = 'product_scout_candidates'
    __table_args__ = (UniqueConstraint('epoch', 'namespace', 'candidate_key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    epoch: Mapped[str] = mapped_column(String(36))
    namespace: Mapped[str] = mapped_column(String(80))
    candidate_key: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ScoutObservation(Base):
    __tablename__ = 'product_scout_observations'
    __table_args__ = (UniqueConstraint('batch_id', 'review_source_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    batch_id: Mapped[str] = mapped_column(ForeignKey('product_scout_batches.id'), index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey('product_scout_candidates.id'), index=True)
    review_source_id: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(24))
    payload: Mapped[dict] = mapped_column(JSON)
    conflict: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ScoutBinding(Base):
    __tablename__ = 'product_scout_bindings'
    candidate_id: Mapped[str] = mapped_column(ForeignKey('product_scout_candidates.id'), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey('sources.source_id'))
    observation_id: Mapped[str] = mapped_column(ForeignKey('product_scout_observations.id'))
    brief_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

class ScoutEvent(Base):
    __tablename__ = 'product_scout_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    batch_id: Mapped[str] = mapped_column(ForeignKey('product_scout_batches.id'), index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey('product_scout_candidates.id'))
    type: Mapped[str] = mapped_column(String(48))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ScoutApproval(Base):
    __tablename__ = 'product_scout_approvals'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    request_key: Mapped[str] = mapped_column(String(128), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(80))
    receipt: Mapped[dict] = mapped_column(JSON)

class TaskSourceContext(Base):
    __tablename__ = 'product_task_source_contexts'
    task_id: Mapped[str] = mapped_column(ForeignKey('product_tasks.id'), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

SCOUT_TABLE_NAMES={m.__tablename__ for m in (ScoutBatch,ScoutRun,ScoutCandidate,ScoutObservation,ScoutBinding,ScoutEvent,ScoutApproval,TaskSourceContext)}
