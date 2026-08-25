import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from uuid import UUID, uuid7

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from deepaha.documents.models import EvidenceRef
from deepaha.p9b.models import (
    OpportunityUnit,
    OpportunityUnitAlias,
    OpportunityUnitLineageEvent,
    OpportunityUnitLineageEvidence,
    OpportunityUnitLineageMember,
    OpportunityUnitVersion,
    SourceBundleMember,
    SourceBundleRevision,
)


class UnitIdentityError(ValueError):
    pass


class UnitIdentityCollision(UnitIdentityError):
    pass


class UnitConcurrencyConflict(UnitIdentityError):
    pass


@dataclass(frozen=True)
class UnitSeed:
    current_unit_key: str
    unit_kind: str
    canonical_label: str
    identity_fingerprint: str


def normalize_unit_key(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip()).casefold()
    if not normalized:
        raise UnitIdentityError("unit key must not be empty")
    return normalized


def _terminal_fingerprint(
    *,
    prior_fingerprint: str,
    status: str,
    effective_at: datetime,
) -> str:
    return sha256(
        f"p9b-unit-terminal\0{prior_fingerprint}\0{status}\0{effective_at.isoformat()}".encode()
    ).hexdigest()


class OpportunityUnitService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_default_singleton(
        self,
        *,
        opportunity_id: UUID,
        opportunity_version: int,
        source_bundle_revision_id: UUID,
        effective_from: datetime,
        canonical_label: str,
        identity_fingerprint: str,
    ) -> OpportunityUnit:
        return self.create_unit(
            opportunity_id=opportunity_id,
            opportunity_version=opportunity_version,
            source_bundle_revision_id=source_bundle_revision_id,
            seed=UnitSeed(
                current_unit_key="__default_singleton__",
                unit_kind="DEFAULT_SINGLETON",
                canonical_label=canonical_label,
                identity_fingerprint=identity_fingerprint,
            ),
            effective_from=effective_from,
        )

    def create_unit(
        self,
        *,
        opportunity_id: UUID,
        opportunity_version: int,
        source_bundle_revision_id: UUID,
        seed: UnitSeed,
        effective_from: datetime,
    ) -> OpportunityUnit:
        normalized = self._validate_seed(seed)
        self._require_frozen_revision(
            source_bundle_revision_id,
            opportunity_id=opportunity_id,
            opportunity_version=opportunity_version,
        )
        collision = self._session.scalar(
            select(OpportunityUnit.opportunity_unit_id).where(
                OpportunityUnit.opportunity_id == opportunity_id,
                OpportunityUnit.normalized_current_unit_key == normalized,
                OpportunityUnit.retired_at.is_(None),
            )
        )
        if collision is not None:
            raise UnitIdentityCollision("active OpportunityUnit key collision")
        unit_id = uuid7()
        unit = OpportunityUnit(
            opportunity_unit_id=unit_id,
            public_id=f"unit_{unit_id.hex}",
            opportunity_id=opportunity_id,
            opportunity_version=opportunity_version,
            current_unit_key=seed.current_unit_key.strip(),
            normalized_current_unit_key=normalized,
            unit_kind=seed.unit_kind,
            lifecycle_status="ACTIVE",
            current_version_id=None,
            created_at=effective_from,
            retired_at=None,
        )
        self._session.add(unit)
        self._session.flush()
        version = self._new_version(
            unit=unit,
            opportunity_version=opportunity_version,
            source_bundle_revision_id=source_bundle_revision_id,
            effective_from=effective_from,
            effective_to=None,
            status="ACTIVE",
            canonical_label=seed.canonical_label,
            identity_fingerprint=seed.identity_fingerprint,
            supersedes_version_id=None,
        )
        unit.current_version_id = version.opportunity_unit_version_id
        evidence_ref_id = self._require_bundle_evidence(source_bundle_revision_id)
        self._session.add(
            OpportunityUnitAlias(
                alias_id=uuid7(),
                opportunity_id=unit.opportunity_id,
                opportunity_unit_id=unit.opportunity_unit_id,
                normalized_alias_key=unit.normalized_current_unit_key,
                display_alias_key=unit.current_unit_key,
                alias_kind="CURRENT",
                valid_from=effective_from,
                valid_to=None,
                evidence_ref_id=evidence_ref_id,
                source_bundle_revision_id=source_bundle_revision_id,
                created_at=effective_from,
            )
        )
        self._session.flush()
        return unit

    def append_version_cas(
        self,
        *,
        opportunity_unit_id: UUID,
        expected_current_version_id: UUID | None,
        opportunity_version: int,
        source_bundle_revision_id: UUID,
        effective_from: datetime,
        canonical_label: str,
        identity_fingerprint: str,
    ) -> OpportunityUnitVersion:
        unit = self._require_unit(opportunity_unit_id)
        if unit.current_version_id != expected_current_version_id:
            raise UnitConcurrencyConflict("OpportunityUnit current pointer changed")
        if unit.lifecycle_status != "ACTIVE":
            raise UnitIdentityError("cannot append an ACTIVE version to a retired unit")
        self._require_frozen_revision(
            source_bundle_revision_id,
            opportunity_id=unit.opportunity_id,
            opportunity_version=opportunity_version,
        )
        version = self._new_version(
            unit=unit,
            opportunity_version=opportunity_version,
            source_bundle_revision_id=source_bundle_revision_id,
            effective_from=effective_from,
            effective_to=None,
            status="ACTIVE",
            canonical_label=canonical_label,
            identity_fingerprint=identity_fingerprint,
            supersedes_version_id=expected_current_version_id,
        )
        updated_id = self._session.scalar(
            update(OpportunityUnit)
            .where(
                OpportunityUnit.opportunity_unit_id == opportunity_unit_id,
                OpportunityUnit.current_version_id == expected_current_version_id,
            )
            .values(
                current_version_id=version.opportunity_unit_version_id,
                opportunity_version=opportunity_version,
            )
            .returning(OpportunityUnit.opportunity_unit_id)
            .execution_options(synchronize_session=False)
        )
        if updated_id is None:
            raise UnitConcurrencyConflict("OpportunityUnit CAS update lost a race")
        self._session.flush()
        self._session.refresh(unit)
        return version

    def split_singleton(
        self,
        *,
        opportunity_unit_id: UUID,
        expected_current_version_id: UUID | None,
        source_bundle_revision_id: UUID,
        evidence_ref_ids: list[UUID],
        units: list[UnitSeed],
        effective_at: datetime,
        reason_code: str,
        actor_identity: str,
    ) -> tuple[OpportunityUnitLineageEvent, tuple[OpportunityUnit, ...]]:
        singleton = self._require_unit(opportunity_unit_id)
        if singleton.unit_kind != "DEFAULT_SINGLETON":
            raise UnitIdentityError("only a DEFAULT_SINGLETON can use singleton split")
        if singleton.current_version_id != expected_current_version_id:
            raise UnitConcurrencyConflict("OpportunityUnit current pointer changed")
        if len(units) < 2:
            raise UnitIdentityError("split requires at least two target units")
        if not reason_code.strip() or not actor_identity.strip():
            raise UnitIdentityError("split requires reason and accountable actor")
        self._require_evidence(evidence_ref_ids, source_bundle_revision_id)
        normalized_children = [self._validate_seed(seed) for seed in units]
        if len(set(normalized_children)) != len(normalized_children):
            raise UnitIdentityCollision("duplicate split child key")
        self._require_frozen_revision(
            source_bundle_revision_id,
            opportunity_id=singleton.opportunity_id,
            opportunity_version=singleton.opportunity_version,
        )
        collision = self._session.scalar(
            select(OpportunityUnit.opportunity_unit_id).where(
                OpportunityUnit.opportunity_id == singleton.opportunity_id,
                OpportunityUnit.normalized_current_unit_key.in_(normalized_children),
                OpportunityUnit.retired_at.is_(None),
                OpportunityUnit.opportunity_unit_id != singleton.opportunity_unit_id,
            )
        )
        if collision is not None:
            raise UnitIdentityCollision("split child collides with an active unit")
        source_version_id = singleton.current_version_id
        assert source_version_id is not None
        self._close_unit(
            singleton,
            expected_current_version_id=source_version_id,
            source_bundle_revision_id=source_bundle_revision_id,
            effective_at=effective_at,
            status="SUPERSEDED_BY_SEGMENTATION",
        )
        children = tuple(
            self.create_unit(
                opportunity_id=singleton.opportunity_id,
                opportunity_version=singleton.opportunity_version,
                source_bundle_revision_id=source_bundle_revision_id,
                seed=seed,
                effective_from=effective_at,
            )
            for seed in units
        )
        event = self._lineage_event(
            opportunity_id=singleton.opportunity_id,
            event_type="SPLIT",
            reverses_event_id=None,
            source_bundle_revision_id=source_bundle_revision_id,
            evidence_ref_ids=evidence_ref_ids,
            reason_code=reason_code,
            actor_identity=actor_identity,
            created_at=effective_at,
            sources=[(singleton.opportunity_unit_id, source_version_id)],
            targets=[
                (child.opportunity_unit_id, self._require_pointer(child)) for child in children
            ],
        )
        return event, children

    def merge_units(
        self,
        *,
        opportunity_unit_ids: list[UUID],
        source_bundle_revision_id: UUID,
        evidence_ref_ids: list[UUID],
        target: UnitSeed,
        effective_at: datetime,
        reason_code: str,
        actor_identity: str,
        reverses_split_event_id: UUID | None,
    ) -> tuple[OpportunityUnitLineageEvent, OpportunityUnit]:
        if len(set(opportunity_unit_ids)) < 2:
            raise UnitIdentityError("merge requires at least two distinct source units")
        if not reason_code.strip() or not actor_identity.strip():
            raise UnitIdentityError("merge requires reason and accountable actor")
        self._require_evidence(evidence_ref_ids, source_bundle_revision_id)
        sources = [self._require_unit(unit_id) for unit_id in opportunity_unit_ids]
        opportunity_ids = {unit.opportunity_id for unit in sources}
        opportunity_versions = {unit.opportunity_version for unit in sources}
        if (
            len(opportunity_ids) != 1
            or len(opportunity_versions) != 1
            or any(unit.lifecycle_status != "ACTIVE" for unit in sources)
        ):
            raise UnitIdentityError("merge sources must be active in one Opportunity")
        self._require_frozen_revision(
            source_bundle_revision_id,
            opportunity_id=sources[0].opportunity_id,
            opportunity_version=sources[0].opportunity_version,
        )
        source_ids = set(opportunity_unit_ids)
        normalized_target = self._validate_seed(target)
        collision = self._session.scalar(
            select(OpportunityUnit.opportunity_unit_id).where(
                OpportunityUnit.opportunity_id == sources[0].opportunity_id,
                OpportunityUnit.normalized_current_unit_key == normalized_target,
                OpportunityUnit.retired_at.is_(None),
                OpportunityUnit.opportunity_unit_id.not_in(source_ids),
            )
        )
        if collision is not None:
            raise UnitIdentityCollision("merge target collides with another active unit")

        original_id: UUID | None = None
        if reverses_split_event_id is not None:
            split = self._session.get(
                OpportunityUnitLineageEvent,
                reverses_split_event_id,
            )
            if split is None or split.event_type != "SPLIT":
                raise UnitIdentityError("reversal must reference an existing SPLIT")
            split_targets = set(
                self._session.scalars(
                    select(OpportunityUnitLineageMember.opportunity_unit_id).where(
                        OpportunityUnitLineageMember.lineage_event_id == reverses_split_event_id,
                        OpportunityUnitLineageMember.member_role == "TARGET",
                    )
                )
            )
            if split.opportunity_id != sources[0].opportunity_id or split_targets != source_ids:
                raise UnitIdentityError("reversal sources must exactly match SPLIT targets")
            original_id = self._session.scalar(
                select(OpportunityUnitLineageMember.opportunity_unit_id).where(
                    OpportunityUnitLineageMember.lineage_event_id == reverses_split_event_id,
                    OpportunityUnitLineageMember.member_role == "SOURCE",
                )
            )
            if original_id is None:
                raise UnitIdentityError("SPLIT has no original singleton source")
            original = self._require_unit(original_id)
            if original.unit_kind != "DEFAULT_SINGLETON" or original.lifecycle_status != "RETIRED":
                raise UnitIdentityError("SPLIT original singleton is not reusable")

        source_members = [
            (unit.opportunity_unit_id, self._require_pointer(unit)) for unit in sources
        ]
        for unit in sources:
            self._close_unit(
                unit,
                expected_current_version_id=self._require_pointer(unit),
                source_bundle_revision_id=source_bundle_revision_id,
                effective_at=effective_at,
                status="MERGED",
            )

        if reverses_split_event_id is None:
            merged = self.create_unit(
                opportunity_id=sources[0].opportunity_id,
                opportunity_version=sources[0].opportunity_version,
                source_bundle_revision_id=source_bundle_revision_id,
                seed=target,
                effective_from=effective_at,
            )
            event_type = "MERGE"
        else:
            assert original_id is not None
            merged = self._reactivate_original_singleton(
                self._require_unit(original_id),
                source_bundle_revision_id=source_bundle_revision_id,
                target=target,
                effective_at=effective_at,
            )
            event_type = "REVERSAL"

        event = self._lineage_event(
            opportunity_id=sources[0].opportunity_id,
            event_type=event_type,
            reverses_event_id=reverses_split_event_id,
            source_bundle_revision_id=source_bundle_revision_id,
            evidence_ref_ids=evidence_ref_ids,
            reason_code=reason_code,
            actor_identity=actor_identity,
            created_at=effective_at,
            sources=source_members,
            targets=[(merged.opportunity_unit_id, self._require_pointer(merged))],
        )
        return event, merged

    def rekey_unit(
        self,
        *,
        opportunity_unit_id: UUID,
        new_key: str,
        source_bundle_revision_id: UUID,
        evidence_ref_ids: list[UUID],
        confidence: str,
        effective_at: datetime,
        reason_code: str,
        actor_identity: str,
    ) -> OpportunityUnitLineageEvent:
        if confidence != "DETERMINISTIC":
            raise UnitIdentityCollision("UNCERTAIN re-key is fail closed")
        if not reason_code.strip() or not actor_identity.strip():
            raise UnitIdentityError("re-key requires reason and accountable actor")
        self._require_evidence(evidence_ref_ids, source_bundle_revision_id)
        unit = self._require_unit(opportunity_unit_id)
        normalized = normalize_unit_key(new_key)
        collision = self._session.scalar(
            select(OpportunityUnit.opportunity_unit_id).where(
                OpportunityUnit.opportunity_id == unit.opportunity_id,
                OpportunityUnit.normalized_current_unit_key == normalized,
                OpportunityUnit.retired_at.is_(None),
                OpportunityUnit.opportunity_unit_id != unit.opportunity_unit_id,
            )
        )
        if collision is not None:
            raise UnitIdentityCollision("re-key collides with another active unit")
        prior_version_id = self._require_pointer(unit)
        prior = self._session.get(OpportunityUnitVersion, prior_version_id)
        assert prior is not None
        self._close_current_alias(unit, effective_at=effective_at)
        appended = self.append_version_cas(
            opportunity_unit_id=unit.opportunity_unit_id,
            expected_current_version_id=prior_version_id,
            opportunity_version=prior.opportunity_version,
            source_bundle_revision_id=source_bundle_revision_id,
            effective_from=effective_at,
            canonical_label=prior.canonical_label,
            identity_fingerprint=sha256(
                f"p9b-unit-rekey\0{prior.identity_fingerprint}\0{normalized}".encode()
            ).hexdigest(),
        )
        unit.current_unit_key = new_key.strip()
        unit.normalized_current_unit_key = normalized
        self._session.flush()
        self._session.add(
            OpportunityUnitAlias(
                alias_id=uuid7(),
                opportunity_id=unit.opportunity_id,
                opportunity_unit_id=unit.opportunity_unit_id,
                normalized_alias_key=normalized,
                display_alias_key=new_key.strip(),
                alias_kind="CURRENT",
                valid_from=effective_at,
                valid_to=None,
                evidence_ref_id=evidence_ref_ids[0],
                source_bundle_revision_id=source_bundle_revision_id,
                created_at=effective_at,
            )
        )
        self._session.flush()
        return self._lineage_event(
            opportunity_id=unit.opportunity_id,
            event_type="REKEY",
            reverses_event_id=None,
            source_bundle_revision_id=source_bundle_revision_id,
            evidence_ref_ids=evidence_ref_ids,
            reason_code=reason_code,
            actor_identity=actor_identity,
            created_at=effective_at,
            sources=[(unit.opportunity_unit_id, prior_version_id)],
            targets=[(unit.opportunity_unit_id, appended.opportunity_unit_version_id)],
        )

    def _close_unit(
        self,
        unit: OpportunityUnit,
        *,
        expected_current_version_id: UUID,
        source_bundle_revision_id: UUID,
        effective_at: datetime,
        status: str,
    ) -> OpportunityUnitVersion:
        if unit.current_version_id != expected_current_version_id:
            raise UnitConcurrencyConflict("OpportunityUnit current pointer changed")
        prior = self._session.get(OpportunityUnitVersion, expected_current_version_id)
        if prior is None:
            raise UnitIdentityError("current UnitVersion does not exist")
        self._require_frozen_revision(
            source_bundle_revision_id,
            opportunity_id=unit.opportunity_id,
            opportunity_version=prior.opportunity_version,
        )
        terminal = self._new_version(
            unit=unit,
            opportunity_version=prior.opportunity_version,
            source_bundle_revision_id=source_bundle_revision_id,
            effective_from=prior.effective_from,
            effective_to=effective_at,
            status=status,
            canonical_label=prior.canonical_label,
            identity_fingerprint=_terminal_fingerprint(
                prior_fingerprint=prior.identity_fingerprint,
                status=status,
                effective_at=effective_at,
            ),
            supersedes_version_id=expected_current_version_id,
        )
        self._close_current_alias(unit, effective_at=effective_at)
        updated_id = self._session.scalar(
            update(OpportunityUnit)
            .where(
                OpportunityUnit.opportunity_unit_id == unit.opportunity_unit_id,
                OpportunityUnit.current_version_id == expected_current_version_id,
            )
            .values(
                current_version_id=terminal.opportunity_unit_version_id,
                opportunity_version=prior.opportunity_version,
                lifecycle_status="RETIRED",
                retired_at=effective_at,
            )
            .returning(OpportunityUnit.opportunity_unit_id)
            .execution_options(synchronize_session=False)
        )
        if updated_id is None:
            raise UnitConcurrencyConflict("OpportunityUnit CAS close lost a race")
        self._session.flush()
        self._session.refresh(unit)
        return terminal

    def _reactivate_original_singleton(
        self,
        unit: OpportunityUnit,
        *,
        source_bundle_revision_id: UUID,
        target: UnitSeed,
        effective_at: datetime,
    ) -> OpportunityUnit:
        if unit.unit_kind != "DEFAULT_SINGLETON" or unit.lifecycle_status != "RETIRED":
            raise UnitIdentityError("only the retired original singleton can be reused")
        prior_pointer = self._require_pointer(unit)
        version = self._new_version(
            unit=unit,
            opportunity_version=unit.opportunity_version,
            source_bundle_revision_id=source_bundle_revision_id,
            effective_from=effective_at,
            effective_to=None,
            status="ACTIVE",
            canonical_label=target.canonical_label,
            identity_fingerprint=target.identity_fingerprint,
            supersedes_version_id=prior_pointer,
        )
        unit.current_unit_key = target.current_unit_key.strip()
        unit.normalized_current_unit_key = normalize_unit_key(target.current_unit_key)
        unit.unit_kind = "DEFAULT_SINGLETON"
        unit.lifecycle_status = "ACTIVE"
        unit.retired_at = None
        unit.current_version_id = version.opportunity_unit_version_id
        self._session.flush()
        self._session.add(
            OpportunityUnitAlias(
                alias_id=uuid7(),
                opportunity_id=unit.opportunity_id,
                opportunity_unit_id=unit.opportunity_unit_id,
                normalized_alias_key=unit.normalized_current_unit_key,
                display_alias_key=unit.current_unit_key,
                alias_kind="CURRENT",
                valid_from=effective_at,
                valid_to=None,
                evidence_ref_id=self._require_bundle_evidence(source_bundle_revision_id),
                source_bundle_revision_id=source_bundle_revision_id,
                created_at=effective_at,
            )
        )
        self._session.flush()
        return unit

    def _new_version(
        self,
        *,
        unit: OpportunityUnit,
        opportunity_version: int,
        source_bundle_revision_id: UUID,
        effective_from: datetime,
        effective_to: datetime | None,
        status: str,
        canonical_label: str,
        identity_fingerprint: str,
        supersedes_version_id: UUID | None,
    ) -> OpportunityUnitVersion:
        version_number = (
            self._session.scalar(
                select(func.max(OpportunityUnitVersion.version)).where(
                    OpportunityUnitVersion.opportunity_unit_id == unit.opportunity_unit_id
                )
            )
            or 0
        ) + 1
        row = OpportunityUnitVersion(
            opportunity_unit_version_id=uuid7(),
            opportunity_unit_id=unit.opportunity_unit_id,
            opportunity_id=unit.opportunity_id,
            opportunity_version=opportunity_version,
            version=version_number,
            source_bundle_revision_id=source_bundle_revision_id,
            effective_from=effective_from,
            effective_to=effective_to,
            status=status,
            canonical_label=canonical_label,
            identity_fingerprint=identity_fingerprint,
            supersedes_version_id=supersedes_version_id,
            created_at=effective_to or effective_from,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def _lineage_event(
        self,
        *,
        opportunity_id: UUID,
        event_type: str,
        reverses_event_id: UUID | None,
        source_bundle_revision_id: UUID,
        evidence_ref_ids: list[UUID],
        reason_code: str,
        actor_identity: str,
        created_at: datetime,
        sources: list[tuple[UUID, UUID]],
        targets: list[tuple[UUID, UUID]],
    ) -> OpportunityUnitLineageEvent:
        event = OpportunityUnitLineageEvent(
            lineage_event_id=uuid7(),
            opportunity_id=opportunity_id,
            event_type=event_type,
            reverses_event_id=reverses_event_id,
            source_bundle_revision_id=source_bundle_revision_id,
            reason_code=reason_code,
            actor_identity=actor_identity,
            created_at=created_at,
        )
        self._session.add(event)
        self._session.flush()
        self._session.add_all(
            [
                OpportunityUnitLineageMember(
                    lineage_event_id=event.lineage_event_id,
                    opportunity_id=opportunity_id,
                    member_role=role,
                    opportunity_unit_id=unit_id,
                    opportunity_unit_version_id=version_id,
                )
                for role, members in (("SOURCE", sources), ("TARGET", targets))
                for unit_id, version_id in members
            ]
            + [
                OpportunityUnitLineageEvidence(
                    lineage_event_id=event.lineage_event_id,
                    evidence_ref_id=evidence_ref_id,
                )
                for evidence_ref_id in evidence_ref_ids
            ]
        )
        self._session.flush()
        return event

    def _require_frozen_revision(
        self,
        revision_id: UUID,
        *,
        opportunity_id: UUID,
        opportunity_version: int,
    ) -> SourceBundleRevision:
        revision = self._session.get(SourceBundleRevision, revision_id)
        if (
            revision is None
            or revision.status != "FROZEN"
            or revision.opportunity_id != opportunity_id
            or revision.opportunity_version != opportunity_version
        ):
            raise UnitIdentityError("Unit requires an exact FROZEN SourceBundleRevision")
        return revision

    def _require_unit(self, unit_id: UUID) -> OpportunityUnit:
        unit = self._session.get(OpportunityUnit, unit_id)
        if unit is None:
            raise UnitIdentityError("OpportunityUnit does not exist")
        return unit

    def _require_evidence(
        self,
        evidence_ref_ids: list[UUID],
        source_bundle_revision_id: UUID,
    ) -> None:
        if not evidence_ref_ids:
            raise UnitIdentityError("lineage requires Evidence")
        count = self._session.scalar(
            select(func.count(func.distinct(EvidenceRef.evidence_ref_id)))
            .select_from(EvidenceRef)
            .join(
                SourceBundleMember,
                SourceBundleMember.document_id == EvidenceRef.document_id,
            )
            .where(
                EvidenceRef.evidence_ref_id.in_(evidence_ref_ids),
                SourceBundleMember.source_bundle_revision_id == source_bundle_revision_id,
            )
        )
        if count != len(set(evidence_ref_ids)):
            raise UnitIdentityError("lineage Evidence must belong to the exact SourceBundle")

    def _close_current_alias(
        self,
        unit: OpportunityUnit,
        *,
        effective_at: datetime,
    ) -> None:
        current_aliases = tuple(
            self._session.scalars(
                select(OpportunityUnitAlias).where(
                    OpportunityUnitAlias.opportunity_unit_id == unit.opportunity_unit_id,
                    OpportunityUnitAlias.alias_kind == "CURRENT",
                    OpportunityUnitAlias.valid_to.is_(None),
                )
            )
        )
        if len(current_aliases) != 1:
            raise UnitIdentityError("OpportunityUnit must have exactly one CURRENT alias")
        current_alias = current_aliases[0]
        if effective_at <= current_alias.valid_from:
            raise UnitIdentityError("identity transition must advance the alias window")
        current_alias.alias_kind = "HISTORICAL"
        current_alias.valid_to = effective_at
        self._session.flush()

    def _require_bundle_evidence(self, revision_id: UUID) -> UUID:
        evidence_ref_id = self._session.scalar(
            select(EvidenceRef.evidence_ref_id)
            .join(
                SourceBundleMember,
                SourceBundleMember.document_id == EvidenceRef.document_id,
            )
            .where(SourceBundleMember.source_bundle_revision_id == revision_id)
            .order_by(EvidenceRef.evidence_ref_id)
            .limit(1)
        )
        if evidence_ref_id is None:
            raise UnitIdentityError("Unit alias requires bundle-member Evidence")
        return evidence_ref_id

    @staticmethod
    def _require_pointer(unit: OpportunityUnit) -> UUID:
        if unit.current_version_id is None:
            raise UnitIdentityError("OpportunityUnit has no current pointer")
        return unit.current_version_id

    @staticmethod
    def _validate_seed(seed: UnitSeed) -> str:
        normalized = normalize_unit_key(seed.current_unit_key)
        if seed.unit_kind not in {
            "POSITION",
            "TRACK",
            "PROGRAM_TIER",
            "REGION_VARIANT",
            "DEFAULT_SINGLETON",
        }:
            raise UnitIdentityError("unsupported OpportunityUnit kind")
        if not seed.canonical_label.strip():
            raise UnitIdentityError("OpportunityUnit label must not be empty")
        if re.fullmatch(r"[0-9a-f]{64}", seed.identity_fingerprint) is None:
            raise UnitIdentityError("OpportunityUnit fingerprint must be lowercase SHA-256")
        return normalized


__all__ = [
    "OpportunityUnitService",
    "UnitConcurrencyConflict",
    "UnitIdentityCollision",
    "UnitIdentityError",
    "UnitSeed",
    "normalize_unit_key",
]
