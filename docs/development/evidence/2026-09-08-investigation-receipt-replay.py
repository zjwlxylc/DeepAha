"""Frozen legacy receipt -> current preparation/check/view in an isolated test DB.

Uses six existing files only. No WMA, official HTTP, approvals or business DB writes.
Run from repository root with PYTHONPATH=backend;backend/src and owned port 55437.
"""

import argparse
import json
import os
from collections import Counter
from dataclasses import asdict, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import UUID, uuid7

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url

from deepaha.investigations.delivery import preflight_manifest, validate_delivery, validate_legacy_delivery
from deepaha.investigations.models import InvestigationTask
from deepaha.p9b.models import VerifiedFact
from deepaha.review.models import ReviewerAccountModel
from deepaha.sources.models import SourceEndpoint
from tests.integration.test_investigation_store import harness
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
paths = [case / "result" / name for name in files]
originals = {}
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
legacy, current = validate_legacy_delivery(files, originals), validate_delivery(files, originals)
assert legacy.sha256 == current.sha256
original_case = UUID(legacy.opportunities["case_id"])
seed = legacy.opportunities["seed_url"]
temp_root = root / ".deepaha-local-manual"
temp_root.mkdir(exist_ok=True)
db_name, maintenance, temp_url, temp_connection = temporary_database(database_url, "receipt_replay")
engine = create_engine(temp_url)
try:
    os.environ["DEEPAHA_DATABASE_URL"] = temp_connection
    config = Config(str(root / "backend/alembic.ini"))
    config.set_main_option("script_location", str(root / "backend/migrations"))
    command.upgrade(config, "head")
    with TemporaryDirectory(prefix="receipt-replay-", dir=temp_root) as temp:
        assert Path(temp).resolve().is_relative_to(temp_root.resolve())
        h = harness.__wrapped__(engine, Path(temp))
        # The fixture source policy exercises local import authorization only;
        # it does not attest current robots, source approval or a human review.
        with h.factory.begin() as session:
            endpoint = session.get(SourceEndpoint, h.command.endpoint_id)
            endpoint.url = seed
            endpoint.allowed_hosts = sorted({urlsplit(a.url).hostname for a in legacy.artifacts})
            account = session.get(ReviewerAccountModel, h.principal.reviewer_id)
            account.synthetic = True
        h.principal = replace(h.principal, synthetic=True)
        h.command = h.command.model_copy(update={"notice_url": seed, "expected_entity_keys": (), "calibration": True})
        with patch("deepaha.investigations.store.uuid7", return_value=original_case):
            task_id = h.store.create(h.command, h.principal, "frozen-offline-replay")
        owner = uuid7()
        h.store.claim(task_id, owner, {"provider": "OFFLINE_FROZEN_REPLAY", "wma_calls": 0})
        h.store.transition(task_id, owner, "PREPARING", ("offline-fixture", "offline-fixture"))
        h.store.transition(task_id, owner, "INVESTIGATING")
        h.store.transition(task_id, owner, "COLLECTING")
        h.store.freeze_manifest(task_id, owner, files)
        h.store.finish(task_id, owner, legacy, files)
        with h.factory() as session:
            original_snapshot = session.get(InvestigationTask, task_id).delivery
        prepared = h.store.prepare_documents(task_id, legacy.sha256, h.principal)
        check = prepared["evidence_check"]
        assert h.store.prepare_documents(task_id, legacy.sha256, h.principal) == prepared
        with h.factory() as session:
            assert session.get(InvestigationTask, task_id).delivery == original_snapshot
            assert session.scalar(select(func.count()).select_from(VerifiedFact)) == 0
        assert prepared["review"] is None and prepared["status"] == "PENDING_REVIEW"
        rows = check["references"]
        pairs = list(zip(
            [r for f in current.facts for r in f.evidence],
            [r for f in legacy.facts for r in f.evidence], rows, strict=True,
        ))
        for new, old, row in pairs:
            assert json.loads(json.dumps(asdict(new.verification))) == row["verification"]
            assert new.quote == old.quote == row["verification"]["quote"]
            assert new.locator == old.locator == row["verification"]["original_locator"]
            if old.mechanically_verified:
                assert row["verdict"] == "PASS" and row["persistent_binding"]["evidence_ref_id"]
        assert check["counts"] == {"PASS": 94, "FAIL": 0, "UNVERIFIED": 30}
        assert len(rows) == 124 and check["verdict"] == "UNVERIFIED"
        headers = [r for r in rows if r["verification"]["quote"] == "学历、学位要求"]
        assert len(headers) == 4 and all(r["persistent_binding"] for r in headers)
        inline = [r for r in rows if r["field"] == "site_publish_time"]
        assert len(inline) == 1 and inline[0]["persistent_binding"]
finally:
    os.environ["DEEPAHA_DATABASE_URL"] = database_url
    engine.dispose()
    drop_temporary_database(db_name, maintenance)
assert hashes() == before
implementation = sorted((root / "backend/src/deepaha/evidence_verification").rglob("*.py")) + sorted((root / "backend/src/deepaha/investigations").rglob("*.py"))
implementation += [root / "backend/migrations/versions/20260908_0039_investigation_evidence_checks.py", root / "backend/src/deepaha/documents/reader.py"]
report = {"checked_at": datetime.now(UTC).isoformat(), "mode": "FROZEN_INTAKE_TO_PERSISTENT_RECEIPT",
          "wma_calls": 0, "official_http_calls": 0, "business_database_writes": 0, "human_approvals": 0,
          "temporary_database_removed": True, "temporary_objects_removed": True,
          "original_hashes_before": before, "original_hashes_after": hashes(),
          "original_delivery_unchanged": True, "current_delivery_matches_every_receipt_reference": True,
          "four_headers_bound": True, "inline_publication_bound": True,
          "legacy_counts": dict(Counter("PASS" if old.mechanically_verified else "UNVERIFIED" for _, old, _ in pairs)),
          "check": check, "documents": prepared["document_preparation"],
          "implementation_hashes": {p.relative_to(root).as_posix(): sha256(p.read_bytes()).hexdigest() for p in implementation}}
args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"counts": check["counts"], "verdict": check["verdict"], "all_124_shared_results_equal": True, "temporary_database_removed": True}))
