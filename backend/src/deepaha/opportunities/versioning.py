import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from hashlib import sha256
from unicodedata import normalize
from uuid import UUID

from pydantic import BaseModel, JsonValue, ValidationError

from deepaha.contracts.phase1 import SourceTier
from deepaha.contracts.phase3 import (
    ApplicationWindowSchema,
    OpportunityDocumentRole,
    OpportunityEventSchemaV03,
    OpportunityEventType,
    OpportunityFieldChangeSchema,
    OpportunityFieldEvidenceSchema,
    OpportunitySnapshotSchema,
    OpportunityVersionSchemaV03,
    SnapshotField,
)
from deepaha.opportunities.types import UNSET, OpportunityPatch

FIELD_ORDER = {field: index for index, field in enumerate(SnapshotField)}


class ReplayError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VersionCommand:
    opportunity_id: UUID
    source_document_id: UUID
    source_evidence_ref_id: UUID
    source_tier: SourceTier
    role: OpportunityDocumentRole
    effective_at: datetime
    facts: OpportunityPatch

    def __post_init__(self) -> None:
        if self.effective_at.tzinfo is None or self.effective_at.utcoffset() is None:
            raise ValueError("effective_at must include timezone information")


@dataclass(frozen=True, slots=True)
class VersionState:
    opportunity_id: UUID
    version: int
    snapshot: OpportunitySnapshotSchema
    field_evidence: tuple[OpportunityFieldEvidenceSchema, ...]
    content_sha256: str

    def snapshot_value(self, field_path: SnapshotField) -> JsonValue:
        return _snapshot_values(self.snapshot)[field_path]


@dataclass(frozen=True, slots=True)
class VersionPlan:
    opportunity_id: UUID
    version: int
    effective_from: datetime
    source_document_id: UUID
    source_evidence_ref_id: UUID
    snapshot: OpportunitySnapshotSchema
    field_evidence: tuple[OpportunityFieldEvidenceSchema, ...]
    changes: tuple[OpportunityFieldChangeSchema, ...]
    content_sha256: str
    event_type: OpportunityEventType

    def as_state(self) -> VersionState:
        return VersionState(
            opportunity_id=self.opportunity_id,
            version=self.version,
            snapshot=self.snapshot,
            field_evidence=self.field_evidence,
            content_sha256=self.content_sha256,
        )


@dataclass(frozen=True, slots=True)
class VersionConflict:
    reason_codes: tuple[str, ...]


def _canonical_json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return normalize("NFC", value) if isinstance(value, str) else value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite floats are not canonical JSON values")
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("canonical datetime must include timezone information")
        utc_value = value.astimezone(UTC)
        return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, BaseModel):
        return _canonical_json_value(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {
            normalize("NFC", str(key)): _canonical_json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_json_value(item) for item in value]
    raise ValueError(f"unsupported canonical JSON value: {type(value).__name__}")


def _canonical_json_bytes(value: object) -> bytes:
    canonical = _canonical_json_value(value)
    return json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sorted_evidence(
    field_evidence: Sequence[OpportunityFieldEvidenceSchema],
) -> tuple[OpportunityFieldEvidenceSchema, ...]:
    return tuple(sorted(field_evidence, key=lambda item: FIELD_ORDER[item.field_path]))


def canonical_content_sha256(
    snapshot: OpportunitySnapshotSchema,
    field_evidence: Sequence[OpportunityFieldEvidenceSchema],
) -> str:
    payload = {
        "snapshot": snapshot.model_dump(mode="json"),
        "field_evidence": [
            item.model_dump(mode="json") for item in _sorted_evidence(field_evidence)
        ],
    }
    return sha256(_canonical_json_bytes(payload)).hexdigest()


def derive_precedence(
    source_tier: SourceTier,
    role: OpportunityDocumentRole,
) -> int | None:
    if source_tier is SourceTier.OFFICIAL_AGGREGATOR:
        return 250
    if source_tier is not SourceTier.OFFICIAL_PRIMARY:
        return None
    if role in {
        OpportunityDocumentRole.CORRECTION,
        OpportunityDocumentRole.DEADLINE_EXTENSION,
        OpportunityDocumentRole.CANCELLATION,
    }:
        return 600
    if role in {
        OpportunityDocumentRole.POSITION_TABLE,
        OpportunityDocumentRole.ATTACHMENT,
    }:
        return 500
    if role in {
        OpportunityDocumentRole.PRIMARY_NOTICE,
        OpportunityDocumentRole.RESULT,
    }:
        return 400
    return 300


def _json_scalar(value: object) -> JsonValue:
    return _canonical_json_value(value)


def _snapshot_values(
    snapshot: OpportunitySnapshotSchema,
) -> dict[SnapshotField, JsonValue]:
    return {
        SnapshotField.CANONICAL_TITLE: snapshot.canonical_title,
        SnapshotField.TYPE: snapshot.type.value,
        SnapshotField.ISSUER_NAME: snapshot.issuer_name,
        SnapshotField.JURISDICTION: snapshot.jurisdiction,
        SnapshotField.STATUS: snapshot.status.value,
        SnapshotField.PUBLISHED_AT: _json_scalar(snapshot.published_at),
        SnapshotField.APPLICATION_WINDOW_OPENS_ON: _json_scalar(
            snapshot.application_window.opens_on
        ),
        SnapshotField.APPLICATION_WINDOW_CLOSES_ON: _json_scalar(
            snapshot.application_window.closes_on
        ),
        SnapshotField.APPLICATION_WINDOW_TIMEZONE: snapshot.application_window.timezone,
        SnapshotField.APPLICATION_URL: (
            None if snapshot.application_url is None else str(snapshot.application_url)
        ),
        SnapshotField.ATTACHMENT_URLS: [str(value) for value in snapshot.attachment_urls],
        SnapshotField.LOCATIONS: list(snapshot.locations),
    }


def _patch_values(facts: OpportunityPatch) -> dict[SnapshotField, JsonValue]:
    values: dict[SnapshotField, JsonValue] = {}
    scalar_fields = (
        (SnapshotField.CANONICAL_TITLE, facts.canonical_title),
        (SnapshotField.TYPE, facts.type),
        (SnapshotField.ISSUER_NAME, facts.issuer_name),
        (SnapshotField.JURISDICTION, facts.jurisdiction),
        (SnapshotField.STATUS, facts.status),
        (SnapshotField.PUBLISHED_AT, facts.published_at),
        (SnapshotField.APPLICATION_URL, facts.application_url),
        (SnapshotField.ATTACHMENT_URLS, facts.attachment_urls),
        (SnapshotField.LOCATIONS, facts.locations),
    )
    for field_path, value in scalar_fields:
        if value is not UNSET:
            values[field_path] = _json_scalar(value)
    if isinstance(facts.application_window, ApplicationWindowSchema):
        window = facts.application_window
        values[SnapshotField.APPLICATION_WINDOW_OPENS_ON] = _json_scalar(window.opens_on)
        values[SnapshotField.APPLICATION_WINDOW_CLOSES_ON] = _json_scalar(window.closes_on)
        values[SnapshotField.APPLICATION_WINDOW_TIMEZONE] = window.timezone
    return values


def _empty_snapshot_values() -> dict[SnapshotField, JsonValue]:
    return {
        SnapshotField.JURISDICTION: None,
        SnapshotField.PUBLISHED_AT: None,
        SnapshotField.APPLICATION_WINDOW_OPENS_ON: None,
        SnapshotField.APPLICATION_WINDOW_CLOSES_ON: None,
        SnapshotField.APPLICATION_WINDOW_TIMEZONE: None,
        SnapshotField.APPLICATION_URL: None,
        SnapshotField.ATTACHMENT_URLS: [],
        SnapshotField.LOCATIONS: [],
    }


def _build_snapshot(values: Mapping[SnapshotField, JsonValue]) -> OpportunitySnapshotSchema:
    return OpportunitySnapshotSchema.model_validate(
        {
            "canonical_title": values.get(SnapshotField.CANONICAL_TITLE),
            "type": values.get(SnapshotField.TYPE),
            "issuer_name": values.get(SnapshotField.ISSUER_NAME),
            "jurisdiction": values.get(SnapshotField.JURISDICTION),
            "status": values.get(SnapshotField.STATUS),
            "published_at": values.get(SnapshotField.PUBLISHED_AT),
            "application_window": {
                "opens_on": values.get(SnapshotField.APPLICATION_WINDOW_OPENS_ON),
                "closes_on": values.get(SnapshotField.APPLICATION_WINDOW_CLOSES_ON),
                "timezone": values.get(SnapshotField.APPLICATION_WINDOW_TIMEZONE),
            },
            "application_url": values.get(SnapshotField.APPLICATION_URL),
            "attachment_urls": values.get(SnapshotField.ATTACHMENT_URLS, []),
            "locations": values.get(SnapshotField.LOCATIONS, []),
        }
    )


def classify_event_type(
    version: int,
    role: OpportunityDocumentRole,
    changes: Sequence[OpportunityFieldChangeSchema],
) -> OpportunityEventType:
    if version == 1:
        return OpportunityEventType.CREATED
    status_change = next(
        (change for change in changes if change.field_path is SnapshotField.STATUS),
        None,
    )
    if status_change is not None and status_change.after == "CANCELLED":
        return OpportunityEventType.CANCELLED
    if (
        status_change is not None
        and status_change.before == "CANCELLED"
        and status_change.after in {"OPEN", "CLOSING_SOON"}
    ):
        return OpportunityEventType.REOPENED
    changed_fields = {change.field_path for change in changes}
    if SnapshotField.APPLICATION_WINDOW_CLOSES_ON in changed_fields:
        return OpportunityEventType.DEADLINE_CHANGED
    if SnapshotField.ATTACHMENT_URLS in changed_fields:
        return OpportunityEventType.ATTACHMENT_REPLACED
    if role is OpportunityDocumentRole.CORRECTION:
        return OpportunityEventType.CORRECTED
    return OpportunityEventType.UPDATED


def plan_version(
    current: VersionState | None,
    command: VersionCommand,
) -> VersionPlan | VersionConflict | None:
    precedence = derive_precedence(command.source_tier, command.role)
    if precedence is None or precedence < 300:
        return VersionConflict(reason_codes=("NON_AUTHORITATIVE_VERSION_SOURCE",))

    incoming = _patch_values(command.facts)
    if current is None:
        values = _empty_snapshot_values()
        values.update(incoming)
        try:
            snapshot = _build_snapshot(values)
        except ValidationError:
            return VersionConflict(reason_codes=("INCOMPLETE_SNAPSHOT",))
        changes = tuple(
            OpportunityFieldChangeSchema(
                field_path=field_path,
                before=None,
                after=after,
                evidence_ref_id=command.source_evidence_ref_id,
            )
            for field_path, after in sorted(incoming.items(), key=lambda item: FIELD_ORDER[item[0]])
            if after is not None
        )
        if not changes:
            return VersionConflict(reason_codes=("INCOMPLETE_SNAPSHOT",))
        field_evidence = tuple(
            OpportunityFieldEvidenceSchema(
                field_path=change.field_path,
                precedence=precedence,
                evidence_ref_id=command.source_evidence_ref_id,
                effective_at=command.effective_at,
            )
            for change in changes
        )
        content_hash = canonical_content_sha256(snapshot, field_evidence)
        return VersionPlan(
            opportunity_id=command.opportunity_id,
            version=1,
            effective_from=command.effective_at,
            source_document_id=command.source_document_id,
            source_evidence_ref_id=command.source_evidence_ref_id,
            snapshot=snapshot,
            field_evidence=field_evidence,
            changes=changes,
            content_sha256=content_hash,
            event_type=OpportunityEventType.CREATED,
        )

    if current.opportunity_id != command.opportunity_id:
        raise ValueError("VersionCommand opportunity_id must match current state")

    current_values = _snapshot_values(current.snapshot)
    evidence_by_field = {item.field_path: item for item in current.field_evidence}
    differing = {
        field_path: value
        for field_path, value in incoming.items()
        if current_values.get(field_path) != value
    }
    if not differing:
        return None

    conflicts: set[str] = set()
    for field_path in differing:
        existing = evidence_by_field.get(field_path)
        if existing is None or precedence > existing.precedence:
            continue
        if precedence < existing.precedence or command.effective_at < existing.effective_at:
            conflicts.add("LOWER_PRIORITY_CONFLICT")
        elif command.effective_at == existing.effective_at:
            conflicts.add("EVIDENCE_CONFLICT")
    if conflicts:
        ordered = tuple(
            reason
            for reason in ("EVIDENCE_CONFLICT", "LOWER_PRIORITY_CONFLICT")
            if reason in conflicts
        )
        return VersionConflict(reason_codes=ordered)

    next_values = dict(current_values)
    next_values.update(differing)
    snapshot = _build_snapshot(next_values)
    changes = tuple(
        OpportunityFieldChangeSchema(
            field_path=field_path,
            before=current_values[field_path],
            after=differing[field_path],
            evidence_ref_id=command.source_evidence_ref_id,
        )
        for field_path in sorted(differing, key=lambda field: FIELD_ORDER[field])
    )
    for change in changes:
        evidence_by_field[change.field_path] = OpportunityFieldEvidenceSchema(
            field_path=change.field_path,
            precedence=precedence,
            evidence_ref_id=command.source_evidence_ref_id,
            effective_at=command.effective_at,
        )
    field_evidence = _sorted_evidence(tuple(evidence_by_field.values()))
    version = current.version + 1
    content_hash = canonical_content_sha256(snapshot, field_evidence)
    return VersionPlan(
        opportunity_id=command.opportunity_id,
        version=version,
        effective_from=command.effective_at,
        source_document_id=command.source_document_id,
        source_evidence_ref_id=command.source_evidence_ref_id,
        snapshot=snapshot,
        field_evidence=field_evidence,
        changes=changes,
        content_sha256=content_hash,
        event_type=classify_event_type(version, command.role, changes),
    )


def _contract_values(value: BaseModel) -> JsonValue:
    return _canonical_json_value(value.model_dump(mode="json"))


def replay_opportunity_state(
    versions: Sequence[OpportunityVersionSchemaV03],
    events: Sequence[OpportunityEventSchemaV03],
) -> VersionState:
    if not versions:
        raise ReplayError("history must contain at least one version")
    ordered_versions = sorted(versions, key=lambda item: item.version)
    expected_versions = list(range(1, len(ordered_versions) + 1))
    if [item.version for item in ordered_versions] != expected_versions:
        raise ReplayError("version sequence must be continuous from 1")

    events_by_version: dict[int, list[OpportunityEventSchemaV03]] = {}
    for event in events:
        events_by_version.setdefault(event.to_version, []).append(event)
    if set(events_by_version) != set(expected_versions) or any(
        len(items) != 1 for items in events_by_version.values()
    ):
        raise ReplayError("each version requires exactly one event")

    opportunity_id = ordered_versions[0].opportunity_id
    values: dict[SnapshotField, JsonValue] = {}
    evidence_by_field: dict[SnapshotField, OpportunityFieldEvidenceSchema] = {}
    for version in ordered_versions:
        if version.opportunity_id != opportunity_id:
            raise ReplayError("all versions must belong to one opportunity")
        event = events_by_version[version.version][0]
        expected_from = None if version.version == 1 else version.version - 1
        if (
            event.opportunity_id != opportunity_id
            or event.from_version != expected_from
            or event.to_version != version.version
        ):
            raise ReplayError("event chain is not continuous")
        if (
            event.source_document_id != version.source_document_id
            or event.source_evidence_ref_id != version.source_evidence_ref_id
        ):
            raise ReplayError("event and version source evidence differ")

        for change in event.changes:
            actual_before = values.get(change.field_path)
            if actual_before != change.before:
                raise ReplayError(
                    f"change before value does not match replay state: {change.field_path.value}"
                )
            values[change.field_path] = change.after

        if [_contract_values(change) for change in event.changes] != [
            _contract_values(change) for change in version.changes
        ]:
            raise ReplayError("event changes differ from version changes")

        version_evidence = {item.field_path: item for item in version.field_evidence}
        candidate_evidence = dict(evidence_by_field)
        for change in event.changes:
            field_evidence = version_evidence.get(change.field_path)
            if field_evidence is None or field_evidence.evidence_ref_id != change.evidence_ref_id:
                raise ReplayError("version field evidence does not match event change")
            candidate_evidence[change.field_path] = field_evidence
        if {field: _contract_values(item) for field, item in candidate_evidence.items()} != {
            field: _contract_values(item) for field, item in version_evidence.items()
        }:
            raise ReplayError("field evidence changed without an event change")
        evidence_by_field = candidate_evidence

        try:
            snapshot = _build_snapshot(_empty_snapshot_values() | values)
        except ValidationError as error:
            raise ReplayError("event changes do not build a valid snapshot") from error
        if _contract_values(snapshot) != _contract_values(version.snapshot):
            raise ReplayError("replayed snapshot differs from version snapshot")
        content_hash = canonical_content_sha256(snapshot, tuple(evidence_by_field.values()))
        if content_hash != version.content_sha256:
            raise ReplayError("version content hash differs from replayed hash")

    latest = ordered_versions[-1]
    return VersionState(
        opportunity_id=opportunity_id,
        version=latest.version,
        snapshot=latest.snapshot,
        field_evidence=_sorted_evidence(latest.field_evidence),
        content_sha256=latest.content_sha256,
    )


__all__ = [
    "ReplayError",
    "VersionCommand",
    "VersionConflict",
    "VersionPlan",
    "VersionState",
    "canonical_content_sha256",
    "classify_event_type",
    "derive_precedence",
    "plan_version",
    "replay_opportunity_state",
]
