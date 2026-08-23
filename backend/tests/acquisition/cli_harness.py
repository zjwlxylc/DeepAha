import os
import sys
from uuid import UUID

from deepaha.acquisition.cli import QualificationOutcome, main
from deepaha.acquisition.orchestrator import AcquisitionRunSummary


def fake_qualifier(
    recipe_id: UUID,
    endpoint_id: UUID,
    recipe_path: object,
    maximum_requests: int,
    minimum_interval_seconds: int,
) -> QualificationOutcome:
    del recipe_path, maximum_requests, minimum_interval_seconds
    scenario = os.environ.get("DEEPAHA_QUALIFICATION_TEST_SCENARIO", "complete")
    if scenario == "must-not-run":
        raise AssertionError("fake qualifier must not run")
    terminal = "CAPTCHA_REQUIRED" if scenario == "challenge" else "COMPLETE"
    summary = AcquisitionRunSummary.model_validate(
        {
            "recipe_id": recipe_id,
            "recipe_version": "test-v1",
            "source_id": "019c0000-0000-7000-8000-000000000502",
            "endpoint_id": endpoint_id,
            "terminal_code": terminal,
            "request_count": 1,
            "valid_count": 0 if scenario == "challenge" else 1,
            "parsed_count": 0 if scenario == "challenge" else 1,
            "discovered_count": 0,
            "attachment_count": 0,
            "evidence_count": 0,
            "attempts": [
                {
                    "requested_url": "https://official.example/list",
                    "strategy": "STATIC_HTTP",
                    "validation_status": (
                        "CAPTCHA_REQUIRED" if scenario == "challenge" else "VALID"
                    ),
                    "error_code": "CAPTCHA_MARKER" if scenario == "challenge" else None,
                }
            ],
        }
    )
    return QualificationOutcome(
        summary=summary,
        unsafe_diagnostics={
            "body": "official response body must never be emitted",
            "cookie": "session=super-secret-value",
            "headers": {"authorization": "Bearer super-secret-value"},
        },
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], qualifier=fake_qualifier))
