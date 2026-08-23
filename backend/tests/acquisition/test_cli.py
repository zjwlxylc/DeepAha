import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RECIPE_ID = "019c0000-0000-7000-8000-000000000501"
ENDPOINT_ID = "019c0000-0000-7000-8000-000000000503"
BACKEND = Path(__file__).parents[2]


def run_cli(
    *extra: str,
    live_setting: str | None = None,
    scenario: str = "complete",
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("DEEPAHA_ALLOW_LIVE_SOURCE_CHECK", None)
    if live_setting is not None:
        environment["DEEPAHA_ALLOW_LIVE_SOURCE_CHECK"] = live_setting
    environment["DEEPAHA_QUALIFICATION_TEST_SCENARIO"] = scenario
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(BACKEND / "src"), environment.get("PYTHONPATH")))
    )
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.acquisition.cli_harness",
            "qualify",
            "--recipe-id",
            RECIPE_ID,
            "--endpoint-id",
            ENDPOINT_ID,
            "--recipe-path",
            "recipes.json",
            "--maximum-requests",
            "3",
            "--minimum-interval-seconds",
            "2",
            *extra,
        ],
        cwd=BACKEND,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_qualification_requires_command_and_environment_live_opt_in() -> None:
    no_flag = run_cli(live_setting="true", scenario="must-not-run")
    assert no_flag.returncode == 2
    assert json.loads(no_flag.stdout)["error_code"] == "LIVE_QUALIFICATION_NOT_ALLOWED"

    no_setting = run_cli("--live", scenario="must-not-run")
    assert no_setting.returncode == 2
    assert json.loads(no_setting.stdout)["error_code"] == "LIVE_QUALIFICATION_NOT_ALLOWED"


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--maximum-requests", "0"),
        ("--maximum-requests", "26"),
        ("--minimum-interval-seconds", "0"),
        ("--minimum-interval-seconds", "86401"),
    ],
)
def test_qualification_rejects_unbounded_or_invalid_budget(option: str, value: str) -> None:
    result = run_cli(
        "--live",
        option,
        value,
        live_setting="true",
        scenario="must-not-run",
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["error_code"] == "QUALIFICATION_BUDGET_INVALID"


def test_safe_json_summary_excludes_body_headers_cookies_and_secrets() -> None:
    result = run_cli("--live", live_setting="true")

    assert result.returncode == 0
    assert result.stderr == ""
    assert "official response body" not in result.stdout
    assert "super-secret-value" not in result.stdout
    assert "cookie" not in result.stdout.lower()
    assert "header" not in result.stdout.lower()
    output = json.loads(result.stdout)
    assert set(output) == {
        "schema_version",
        "recipe_id",
        "recipe_version",
        "source_id",
        "endpoint_id",
        "terminal_code",
        "request_count",
        "valid_count",
        "parsed_count",
        "discovered_count",
        "attachment_count",
        "evidence_count",
        "attempts",
    }
    assert set(output["attempts"][0]) == {
        "requested_url",
        "strategy",
        "validation_status",
        "error_code",
    }


def test_challenge_summary_is_safe_and_returns_nonzero() -> None:
    result = run_cli("--live", live_setting="true", scenario="challenge")

    assert result.returncode == 1
    assert json.loads(result.stdout)["terminal_code"] == "CAPTCHA_REQUIRED"
    assert "super-secret-value" not in result.stdout


def test_live_runner_registers_official_alternative_strategy() -> None:
    source = (BACKEND / "src" / "deepaha" / "acquisition" / "cli.py").read_text(
        encoding="utf-8"
    )

    assert "FetchStrategy.OFFICIAL_ALTERNATIVE: OfficialAlternativeFetcher(" in source
