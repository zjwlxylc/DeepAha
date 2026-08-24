from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy.orm import Session

from deepaha.artifacts.models import RawArtifact
from deepaha.documents.models import Document, EvidenceRef
from deepaha.documents.parser import LEGACY_PARSE_CONTRACT_VERSION
from deepaha.opportunities.models import Opportunity, OpportunityEvent, OpportunityVersion
from deepaha.p9b.hashing import document_parse_key
from deepaha.public_catalog.models import PublicCatalogEntry
from deepaha.sources.models import Source

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "public_catalog"
FIXTURE_PATH = FIXTURE_ROOT / "phase5-public-catalog.json"
MANIFEST_PATH = FIXTURE_ROOT / "phase5-public-catalog.manifest.json"
FIELD_PATHS = (
    "canonical_title",
    "type",
    "issuer_name",
    "jurisdiction",
    "status",
    "published_at",
    "application_window.closes_on",
    "application_url",
    "attachment_urls",
    "locations",
)


class FixtureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HtmlLocator(FixtureModel):
    schema_version: Literal["0.2.0"]
    kind: Literal["html_selector"]
    selector: str
    text_sha256: str


class PdfLocator(FixtureModel):
    schema_version: Literal["0.2.0"]
    kind: Literal["pdf_page_text"]
    page_number: int
    text_start: int
    text_end: int
    text_sha256: str


class SpreadsheetLocator(FixtureModel):
    schema_version: Literal["0.2.0"]
    kind: Literal["spreadsheet_range"]
    sheet_name: str
    start_row: int
    end_row: int
    start_column: int
    end_column: int
    cells_sha256: str


Locator = Annotated[
    HtmlLocator | PdfLocator | SpreadsheetLocator,
    Field(discriminator="kind"),
]


class FixtureVersion(FixtureModel):
    effective_at: datetime
    status: str
    closes_on: date | None = None
    event_type: str
    changed_fields: tuple[str, ...]


class FixtureItem(FixtureModel):
    key: str
    type: str
    title: str
    issuer_name: str
    jurisdiction: str
    published_at: datetime
    opens_on: date
    closes_on: date
    timezone: str
    application_url: HttpUrl
    attachment_urls: tuple[HttpUrl, ...]
    locations: tuple[str, ...]
    media_type: str
    locator: Locator
    versions: tuple[FixtureVersion, ...]
    approved_at: datetime
    last_verified_at: datetime


class PublicCatalogFixture(FixtureModel):
    schema_version: Literal["phase5-public-catalog-fixture-v1"]
    synthetic: Literal[True]
    business_truth: Literal[False]
    release_qualification_eligible: Literal[False]
    license: Literal["CC0-1.0 synthetic fixture"]
    items: tuple[FixtureItem, ...]


class FixtureManifest(FixtureModel):
    fixture: Literal["phase5-public-catalog.json"]
    sha256: str
    license: Literal["CC0-1.0 synthetic fixture"]
    synthetic: Literal[True]
    business_truth: Literal[False]
    release_qualification_eligible: Literal[False]
    contains_personal_data: Literal[False]
    item_count: int
    purpose: str


def stable_uuid7(key: str) -> UUID:
    value = bytearray(hashlib.sha256(key.encode("utf-8")).digest()[:16])
    value[6] = (value[6] & 0x0F) | 0x70
    value[8] = (value[8] & 0x3F) | 0x80
    return UUID(bytes=bytes(value))


def load_phase5_fixture() -> PublicCatalogFixture:
    fixture_bytes = FIXTURE_PATH.read_bytes()
    manifest = FixtureManifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert hashlib.sha256(fixture_bytes).hexdigest() == manifest.sha256
    fixture = PublicCatalogFixture.model_validate_json(fixture_bytes)
    assert len(fixture.items) == manifest.item_count
    return fixture


def _snapshot(item: FixtureItem, version: FixtureVersion) -> dict[str, object]:
    closes_on = version.closes_on or item.closes_on
    return {
        "canonical_title": item.title,
        "type": item.type,
        "issuer_name": item.issuer_name,
        "jurisdiction": item.jurisdiction,
        "status": version.status,
        "published_at": item.published_at.isoformat(),
        "application_window": {
            "opens_on": item.opens_on.isoformat(),
            "closes_on": closes_on.isoformat(),
            "timezone": item.timezone,
        },
        "application_url": str(item.application_url),
        "attachment_urls": [str(value) for value in item.attachment_urls],
        "locations": list(item.locations),
    }


def _snapshot_value(snapshot: dict[str, object], field_path: str) -> object:
    if field_path == "application_window.closes_on":
        application_window = snapshot["application_window"]
        assert isinstance(application_window, dict)
        return application_window["closes_on"]
    return snapshot[field_path]


def persist_phase5_fixture(session: Session) -> tuple[str, ...]:
    fixture = load_phase5_fixture()
    public_ids: list[str] = []
    for item in fixture.items:
        source_id = stable_uuid7(f"{item.key}:source")
        source = Source(
            source_id=source_id,
            public_id=f"src_{source_id.hex}",
            canonical_url=f"https://phase5-fixture.example.test/{item.key}/",
            authority_name=item.issuer_name,
            tier="OFFICIAL_PRIMARY",
            jurisdiction=item.jurisdiction,
            active=True,
            created_at=item.versions[0].effective_at,
            updated_at=item.versions[-1].effective_at,
        )
        opportunity_id = stable_uuid7(f"{item.key}:opportunity")
        opportunity = Opportunity(
            opportunity_id=opportunity_id,
            public_id=f"opp_{opportunity_id.hex}",
            type=item.type,
            canonical_title=item.title,
            issuer_name=item.issuer_name,
            jurisdiction=item.jurisdiction,
            current_version=None,
            status=item.versions[-1].status,
            publication_status="PUBLISHED",
            created_at=item.versions[0].effective_at,
            updated_at=item.versions[-1].effective_at,
        )
        session.add_all([source, opportunity])
        session.flush()

        previous_snapshot: dict[str, object] | None = None
        for version_number, version_fixture in enumerate(item.versions, start=1):
            snapshot = _snapshot(item, version_fixture)
            content_bytes = json.dumps(
                snapshot,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            content_sha256 = hashlib.sha256(content_bytes).hexdigest()
            artifact_id = stable_uuid7(f"{item.key}:artifact:{version_number}")
            document_id = stable_uuid7(f"{item.key}:document:{version_number}")
            evidence_id = stable_uuid7(f"{item.key}:evidence:{version_number}")
            official_url = (
                f"https://phase5-fixture.example.test/{item.key}/notice-v{version_number}"
            )
            artifact = RawArtifact(
                artifact_id=artifact_id,
                source_id=source.source_id,
                requested_url=official_url,
                resolved_url=official_url,
                retrieved_at=version_fixture.effective_at,
                http_status=200,
                media_type=item.media_type,
                content_sha256=content_sha256,
                storage_bucket="deepaha-raw",
                object_key=f"raw/sha256/{content_sha256[:2]}/{content_sha256}",
                byte_size=len(content_bytes),
                collector_version="phase5-fixture/1",
                metadata_schema_version="0.2.0",
            )
            document = Document(
                document_id=document_id,
                artifact_id=artifact_id,
                title=f"{item.title} 第 {version_number} 版合成公告",
                published_at=version_fixture.effective_at,
                language="zh-CN",
                extracted_text_uri=None,
                parser_name="phase5_fixture",
                parser_version="1",
                parse_contract_version=LEGACY_PARSE_CONTRACT_VERSION,
                document_parse_key=document_parse_key(
                    artifact_id=artifact_id,
                    artifact_sha256=content_sha256,
                    parser_name="phase5_fixture",
                    parser_version="1",
                    parse_contract_version=LEGACY_PARSE_CONTRACT_VERSION,
                ),
                parse_confidence=None,
                created_at=version_fixture.effective_at,
            )
            evidence = EvidenceRef(
                evidence_ref_id=evidence_id,
                document_id=document_id,
                artifact_id=artifact_id,
                locator_kind=item.locator.kind,
                locator_value=None,
                locator_schema_version="0.2.0",
                locator_payload=item.locator.model_dump(mode="json"),
                quote_sha256=content_sha256,
            )
            session.add(artifact)
            session.flush()
            session.add(document)
            session.flush()
            session.add(evidence)
            session.flush()

            changes = []
            for field_path in version_fixture.changed_fields:
                before = (
                    None
                    if previous_snapshot is None
                    else _snapshot_value(previous_snapshot, field_path)
                )
                changes.append(
                    {
                        "field_path": field_path,
                        "before": before,
                        "after": _snapshot_value(snapshot, field_path),
                        "evidence_ref_id": str(evidence_id),
                    }
                )
            opportunity_version = OpportunityVersion(
                opportunity_id=opportunity_id,
                version=version_number,
                effective_from=version_fixture.effective_at,
                source_document_id=document_id,
                source_evidence_ref_id=evidence_id,
                snapshot=snapshot,
                field_evidence=[
                    {
                        "field_path": field_path,
                        "precedence": 400,
                        "evidence_ref_id": str(evidence_id),
                        "effective_at": version_fixture.effective_at.isoformat(),
                    }
                    for field_path in FIELD_PATHS
                ],
                changes=changes,
                content_sha256=content_sha256,
                review_status="APPROVED",
                created_at=version_fixture.effective_at,
            )
            event = OpportunityEvent(
                event_id=stable_uuid7(f"{item.key}:event:{version_number}"),
                opportunity_id=opportunity_id,
                from_version=None if version_number == 1 else version_number - 1,
                to_version=version_number,
                event_type=version_fixture.event_type,
                changed_fields=list(version_fixture.changed_fields),
                changes=changes,
                source_document_id=document_id,
                source_evidence_ref_id=evidence_id,
                detected_at=version_fixture.effective_at,
            )
            session.add(opportunity_version)
            session.flush()
            session.add(event)
            session.flush()
            previous_snapshot = snapshot

        opportunity.current_version = len(item.versions)
        session.add(
            PublicCatalogEntry(
                opportunity_id=opportunity_id,
                opportunity_version=len(item.versions),
                collection_kind="LICENSE_SAFE_FIXTURE",
                dataset_id="phase5-public-catalog-synthetic",
                dataset_version="v1",
                content_use_basis="OPEN_LICENSE",
                reviewed_by="phase5-fixture-governance",
                approved_at=item.approved_at,
                last_verified_at=item.last_verified_at,
            )
        )
        session.flush()
        public_ids.append(opportunity.public_id)
    return tuple(public_ids)
