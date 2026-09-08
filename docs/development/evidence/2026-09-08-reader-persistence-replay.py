"""Frozen files -> temporary PostgreSQL/objects -> real DocumentBlock bindings.

Run from the repository root with backend and backend/src on PYTHONPATH.
Only the explicitly owned local test PostgreSQL port 55437 is accepted. No WMA,
official HTTP, original file writes, human decisions, or business rows are used.
"""

import argparse
import json
import os
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid7

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from deepaha.artifacts.local_file import LocalFileObjectStore
from deepaha.artifacts.service import ImportRawArtifactCommand, import_raw_artifact
from deepaha.documents.reader import ReaderDocumentParser
from deepaha.documents.service import DocumentService, ParseDocumentCommand
from deepaha.evidence_verification.adapters.defaults import default_registry
from deepaha.evidence_verification.binding import PreparedDocumentEvidence
from deepaha.investigations.delivery import preflight_manifest, validate_legacy_delivery
from deepaha.sources.models import Source
from tests.integration.test_p10b1_migration import temporary_database, drop_temporary_database

parser = argparse.ArgumentParser()
parser.add_argument("--case-directory", type=Path, required=True)
parser.add_argument("--baseline", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
case = args.case_directory.resolve(strict=True)
root = Path(__file__).resolve().parents[3]
database_url = os.environ["DEEPAHA_DATABASE_URL"]
url = make_url(database_url)
assert url.host == "127.0.0.1" and url.port == 55437, "owned test database only"
files = {name: (case / "result" / name).read_bytes() for name in ("opportunities.json", "evidence.json", "report.md")}
originals, paths = {}, [case / "result" / name for name in files]
for identity, relative in preflight_manifest(files):
    path = (case / relative).resolve(strict=True)
    assert path.is_relative_to(case)
    originals[identity] = path.read_bytes()
    paths.append(path)
def hashes():
    return {p.relative_to(case).as_posix(): sha256(p.read_bytes()).hexdigest() for p in paths}
before = hashes()
baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
assert before == {k.replace("\\", "/"): v for k, v in baseline["original_file_hashes_before"].items()}
delivery = validate_legacy_delivery(files, originals)
registry = default_registry()
temp_root = root / ".deepaha-local-manual"
temp_root.mkdir(exist_ok=True)
db_name, maintenance, temp_url, temp_connection = temporary_database(database_url, "reader_replay")
engine = create_engine(temp_url)
rows, documents = [], []
try:
    os.environ["DEEPAHA_DATABASE_URL"] = temp_connection
    config = Config(str(root / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(root / "backend" / "migrations"))
    command.upgrade(config, "head")
    factory = sessionmaker(engine, expire_on_commit=False)
    with TemporaryDirectory(prefix="reader-replay-", dir=temp_root) as temp:
        assert Path(temp).resolve().is_relative_to(temp_root.resolve())
        objects = LocalFileObjectStore(root=Path(temp), bucket="reader-replay")
        objects.ensure_bucket()
        source_id, now = uuid7(), datetime.now(UTC)
        with factory.begin() as session:
            session.add(Source(source_id=source_id, public_id=f"src_{source_id.hex}", canonical_url="https://replay.example.gov/", authority_name="Offline frozen corpus replay; not source approval", tier="OFFICIAL_PRIMARY", jurisdiction=None, active=True, created_at=now, updated_at=now))
        prepared = {}
        for item in delivery.artifacts:
            adapter = registry.select(item.media_type)
            if adapter is None:
                documents.append({"artifact_id": item.artifact_id, "status": "READER_UNSUPPORTED"})
                continue
            with factory.begin() as session:
                raw = import_raw_artifact(session=session, object_store=objects, command=ImportRawArtifactCommand(source_id=source_id, requested_url=item.url, resolved_url=item.url, retrieved_at=now, http_status=200, media_type=item.media_type, content=item.content, collector_version="offline-frozen-replay/1", metadata_schema_version="0.2.0")).artifact
            result = DocumentService(session_factory=factory, object_store=objects, parsers=[ReaderDocumentParser(adapter)]).parse(ParseDocumentCommand(raw.artifact_id))
            assert result.document_id is not None and result.outcome == "SUCCEEDED"
            with factory() as session:
                prepared[item.artifact_id] = PreparedDocumentEvidence(session, objects, registry, document_id=result.document_id, source_url=item.url)
            documents.append({"artifact_id": item.artifact_id, "status": result.outcome, "parse": asdict(result)})
        for fact in delivery.facts:
            for ref in fact.evidence:
                entry = {"entity_id": fact.entity_id, "field": fact.field, "artifact_id": ref.artifact_id, "quote": ref.quote, "locator": ref.locator, "legacy_verdict": "PASS" if ref.mechanically_verified else "UNVERIFIED"}
                if ref.artifact_id in prepared:
                    result = prepared[ref.artifact_id].verify(ref.quote, ref.locator)
                    entry.update(verdict=result.verification.verdict, persistent_binding=asdict(result))
                    if result.verification.verdict == "PASS":
                        assert result.evidence_ref_id is not None and result.block_id is not None
                else:
                    entry.update(verdict="UNVERIFIED", reason="READER_UNSUPPORTED", persistent_binding=None)
                rows.append(entry)
finally:
    os.environ["DEEPAHA_DATABASE_URL"] = database_url
    engine.dispose()
    drop_temporary_database(db_name, maintenance)
counts = Counter(r["verdict"] for r in rows)
regressions = [r for r in rows if r["legacy_verdict"] == "PASS" and r["verdict"] != "PASS"]
headers = [r for r in rows if r["quote"] == "学历、学位要求"]
assert len(rows) == 124 and counts == {"PASS": 94, "UNVERIFIED": 30} and not regressions
assert len(headers) == 4 and all(r["persistent_binding"]["evidence_ref_id"] for r in headers)
inline = [r for r in rows if r["field"] == "site_publish_time"]
assert len(inline) == 1 and inline[0]["persistent_binding"]["evidence_ref_id"]
assert hashes() == before
report = {"checked_at": datetime.now(UTC).isoformat(), "mode": "TEMPORARY_PERSISTENCE_REPLAY", "wma_calls": 0, "business_database_writes": 0, "temporary_database_removed": True, "temporary_objects_removed": True, "original_hashes_before": before, "original_hashes_after": hashes(), "counts": {k: counts[k] for k in ("PASS", "FAIL", "UNVERIFIED")}, "delivery_verdict": "UNVERIFIED", "four_headers_bound": True, "inline_publication_bound": all(r["persistent_binding"] and r["persistent_binding"]["evidence_ref_id"] for r in rows if r["field"] == "site_publish_time"), "documents": documents, "references": rows}
implementation_paths = sorted((root / "backend/src/deepaha/evidence_verification").rglob("*.py")) + [root / "backend/src/deepaha" / path for path in ("contracts/evidence_anchor.py", "documents/reader.py", "documents/blocks.py", "documents/service.py", "documents/models.py", "documents/html.py", "documents/spreadsheet_reading.py")]
report["implementation_hashes"] = {p.relative_to(root).as_posix(): sha256(p.read_bytes()).hexdigest() for p in implementation_paths}
args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
print(json.dumps({k: report[k] for k in ("counts", "delivery_verdict", "four_headers_bound", "inline_publication_bound", "temporary_database_removed")}))
