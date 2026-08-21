import json
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

from deepaha.contracts.phase2 import HtmlSelectorLocator
from deepaha.documents.html import LxmlHtmlParser
from deepaha.documents.locator import replay_html_locator

PROJECT_ROOT = Path(__file__).parents[3]
FIXTURES = Path(__file__).parents[1] / "fixtures" / "official"
HTML = FIXTURES / "civil-service-fast-stream-news-2025.html"
MANIFEST = FIXTURES / "civil-service-fast-stream-news-2025-html.manifest.json"
REGISTRY = PROJECT_ROOT / "config" / "sources" / "phase2-official-endpoints.json"
RUNNER = PROJECT_ROOT / "scripts" / "run-phase2-source-observation.ps1"
FIXED_SIZE = 69_317
FIXED_SHA256 = "b7b92f5e24f496bf462aeb6669cd117fbc83d2f691d6bf2a42024085a58d3468"


def test_official_html_matches_manifest_and_ogl() -> None:
    content = HTML.read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert len(content) == FIXED_SIZE == manifest["byte_size"]
    assert sha256(content).hexdigest() == FIXED_SHA256 == manifest["content_sha256"]
    assert manifest["requested_url"] == (
        "https://www.gov.uk/government/news/"
        "civil-service-fast-stream-named-uks-top-graduate-employer"
    )
    assert manifest["http_status"] == 200
    assert manifest["media_type"] == "text/html; charset=utf-8"
    assert manifest["license"]["name"] == "Open Government Licence v3.0"
    assert manifest["license"]["attribution"] == (
        "Contains public sector information licensed under the Open Government Licence v3.0."
    )
    assert manifest["limitations"] == {
        "gold_business_sample": False,
        "china_launch_coverage": False,
        "current_application_status_proven": False,
    }
    assert manifest["capture"] == {
        "response_body_only": True,
        "headers_stored": False,
        "cookies_stored": False,
        "external_assets_stored": False,
        "redirect_count": 0,
        "tls_verified": True,
    }
    assert b"HTTP/1.1 200" not in content[:100]
    assert b"Open Government Licence v3.0" in content
    assert b'rel="license"' in content


def test_official_html_locators_replay_from_fixed_raw_bytes() -> None:
    content = HTML.read_bytes()
    parsed = LxmlHtmlParser().parse(content, artifact_sha256=FIXED_SHA256)

    assert parsed.title == "Civil Service Fast Stream named UK's top graduate employer - GOV.UK"
    assert parsed.language == "en"
    assert parsed.published_at is None
    assert len(parsed.locators) == 28
    for locator in parsed.locators:
        assert isinstance(locator, HtmlSelectorLocator)
        replayed = replay_html_locator(content, locator)
        assert sha256(replayed.encode()).hexdigest() == locator.text_sha256


def test_live_runner_uses_mock_cli_without_network_or_sleep(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is unavailable")
    fake_cli = tmp_path / "fake-source-cli.ps1"
    fake_cli.write_text(
        """
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Remaining)
$command = $Remaining[0]
if ($command -eq "import-registry") {
    [ordered]@{ schema_version = "0.2.0"; created_sources = 10; created_endpoints = 10 } |
        ConvertTo-Json -Compress
    exit 0
}
if ($command -eq "collect") {
    $endpointId = $Remaining[2]
    [ordered]@{
        endpoint_id = $endpointId
        collection_run_id = "0198d239-4b00-7000-8000-000000000499"
        attempts = @([ordered]@{
            attempt_number = 1
            outcome = "SUCCEEDED"
            http_status = 200
            artifact_id = "0198d239-4b00-7000-8000-000000000498"
            error_code = $null
            started_at = "2026-08-21T00:00:00Z"
            completed_at = "2026-08-21T00:00:01Z"
        })
        final_error_code = $null
    } | ConvertTo-Json -Depth 10 -Compress
    exit 0
}
if ($command -eq "health") {
    $endpointId = $Remaining[2]
    $digest = ("a" * 64) -join ""
    [ordered]@{
        endpoint_id = $endpointId
        latest_content_sha256 = $digest
        latest_object_key = "raw/sha256/aa/$digest"
    } | ConvertTo-Json -Depth 10 -Compress
    exit 0
}
throw "unexpected fake CLI command: $command"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "observation.json"
    monkeypatch.setenv("DEEPAHA_ALLOW_LIVE_SOURCE_CHECK", "true")
    monkeypatch.setenv("DEEPAHA_OBJECT_STORE_SECRET_KEY", "must-not-appear")

    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(RUNNER),
            "-Rounds",
            "1",
            "-IntervalSeconds",
            "21600",
            "-OutputPath",
            str(output),
            "-RegistryPath",
            str(REGISTRY),
            "-CliPath",
            str(fake_cli),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["requested_rounds"] == 1
    assert result["interval_seconds"] == 21600
    assert result["endpoint_count"] == 10
    assert len(result["rounds"]) == 1
    assert len(result["rounds"][0]["results"]) == 10
    assert result["counts"] == {"results": 10, "valid": 10, "failed": 0}
    serialized = output.read_text(encoding="utf-8")
    assert "must-not-appear" not in serialized
    assert "response_body" not in serialized


def test_live_runner_rejects_interval_below_registry_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is unavailable")
    monkeypatch.setenv("DEEPAHA_ALLOW_LIVE_SOURCE_CHECK", "true")

    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(RUNNER),
            "-Rounds",
            "1",
            "-IntervalSeconds",
            "1",
            "-OutputPath",
            str(tmp_path / "observation.json"),
            "-RegistryPath",
            str(REGISTRY),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )

    assert completed.returncode != 0
    assert "minimum_interval_seconds" in (completed.stdout + completed.stderr)
