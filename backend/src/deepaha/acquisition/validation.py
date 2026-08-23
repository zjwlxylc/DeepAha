import json
from collections.abc import Mapping

from lxml import etree, html
from lxml.cssselect import SelectorError

from deepaha.acquisition.contracts import (
    ChallengeType,
    ContentExpectations,
    FetchResult,
    ValidationResult,
    ValidationStatus,
)

VALIDATOR_NAME = "deepaha-content-validator"
VALIDATOR_VERSION = "1.0.0"
METRICS_SCHEMA_VERSION = "1.0.0"


class ContentValidator:
    def evaluate(
        self,
        result: FetchResult,
        expectations: ContentExpectations,
        *,
        discovered_count: int | None = None,
    ) -> ValidationResult:
        body = result.body
        if body is None:
            return self._result(
                ValidationStatus.UNEXPECTED_CONTENT,
                "BODY_UNAVAILABLE",
                byte_size=result.byte_size or 0,
                discovered_count=discovered_count,
            )

        metrics: dict[str, bool | int | str] = {"byte_size": len(body)}
        if discovered_count is not None:
            metrics["discovered_count"] = discovered_count

        content = body.decode("utf-8", errors="replace")
        folded = content.casefold()
        challenge = self._challenge(folded)
        if challenge is not None:
            status, challenge_type, diagnostic = challenge
            return self._result(
                status,
                diagnostic,
                challenge_type=challenge_type,
                metrics=metrics,
                discovered_count=discovered_count,
            )

        if not body:
            return self._result(
                ValidationStatus.UNEXPECTED_CONTENT,
                "EMPTY_BODY",
                metrics=metrics,
                discovered_count=discovered_count,
            )
        if len(body) < expectations.minimum_bytes:
            return self._result(
                ValidationStatus.UNEXPECTED_CONTENT,
                "BODY_TOO_SHORT",
                metrics=metrics,
                discovered_count=discovered_count,
            )
        if len(body) > expectations.maximum_bytes:
            return self._result(
                ValidationStatus.UNEXPECTED_CONTENT,
                "BODY_TOO_LARGE",
                metrics=metrics,
                discovered_count=discovered_count,
            )

        media_type = (result.media_type or "").partition(";")[0].strip().lower()
        if not self._media_type_matches(media_type, expectations):
            return self._result(
                ValidationStatus.UNEXPECTED_CONTENT,
                "MIME_MISMATCH",
                metrics=metrics,
                discovered_count=discovered_count,
            )

        structured_error = self._structured_error(body, expectations.structured_kind)
        if structured_error is not None:
            return self._result(
                ValidationStatus.UNEXPECTED_CONTENT,
                structured_error,
                metrics=metrics,
                discovered_count=discovered_count,
            )

        forbidden_matches = sum(
            marker.casefold() in folded for marker in expectations.forbidden_markers
        )
        if expectations.forbidden_markers:
            metrics["forbidden_marker_matches"] = forbidden_matches
        if forbidden_matches:
            return self._result(
                ValidationStatus.UNEXPECTED_CONTENT,
                "FORBIDDEN_MARKER_PRESENT",
                metrics=metrics,
                discovered_count=discovered_count,
            )

        required_matches = sum(
            marker.casefold() in folded for marker in expectations.required_markers
        )
        metrics["required_marker_matches"] = required_matches
        if required_matches != len(expectations.required_markers):
            return self._result(
                ValidationStatus.UNEXPECTED_CONTENT,
                "REQUIRED_MARKER_MISSING",
                metrics=metrics,
                discovered_count=discovered_count,
            )

        selector_matches = self._selector_matches(content, expectations.required_selectors)
        metrics["required_selector_matches"] = selector_matches
        if selector_matches != len(expectations.required_selectors):
            return self._result(
                ValidationStatus.SELECTOR_DRIFT,
                "REQUIRED_SELECTOR_MISSING",
                metrics=metrics,
                discovered_count=discovered_count,
            )

        minimum = expectations.minimum_discovered_count
        if minimum is not None and (discovered_count is None or discovered_count < minimum):
            diagnostic = (
                "DISCOVERY_COUNT_MISSING"
                if discovered_count is None
                else "MINIMUM_DISCOVERY_NOT_MET"
            )
            return self._result(
                ValidationStatus.ZERO_DISCOVERY_SUSPECT,
                diagnostic,
                metrics=metrics,
                discovered_count=discovered_count,
            )

        return self._result(
            ValidationStatus.VALID,
            metrics=metrics,
            discovered_count=discovered_count,
        )

    @staticmethod
    def _challenge(
        folded: str,
    ) -> tuple[ValidationStatus, ChallengeType, str] | None:
        if "access denied" in folded or "request forbidden" in folded:
            return (
                ValidationStatus.ACCESS_DENIED,
                ChallengeType.ACCESS_CONTROL,
                "ACCESS_DENIED_MARKER",
            )
        if 'id="login"' in folded or 'type="password"' in folded:
            return (
                ValidationStatus.AUTH_REQUIRED,
                ChallengeType.AUTHENTICATION,
                "AUTH_REQUIRED_MARKER",
            )
        if "captcha" in folded or "验证码" in folded:
            return (
                ValidationStatus.CAPTCHA_REQUIRED,
                ChallengeType.CAPTCHA,
                "CAPTCHA_MARKER",
            )
        if "__jsl_clearance" in folded or "document.cookie" in folded:
            return (
                ValidationStatus.CONTENT_CHALLENGE,
                ChallengeType.JAVASCRIPT_COOKIE,
                "JAVASCRIPT_COOKIE_CHALLENGE",
            )
        return None

    @staticmethod
    def _media_type_matches(media_type: str, expectations: ContentExpectations) -> bool:
        if expectations.structured_kind == "JSON":
            return media_type == "application/json" or media_type.endswith("+json")
        if expectations.structured_kind == "XML":
            return media_type in {"application/xml", "text/xml"} or media_type.endswith("+xml")
        if expectations.required_selectors:
            return media_type in {"application/xhtml+xml", "text/html"}
        return bool(media_type)

    @staticmethod
    def _structured_error(body: bytes, kind: str | None) -> str | None:
        try:
            if kind == "JSON":
                json.loads(body)
            elif kind == "XML":
                parser = etree.XMLParser(
                    no_network=True,
                    recover=False,
                    resolve_entities=False,
                    huge_tree=False,
                )
                etree.fromstring(body, parser=parser)
        except json.JSONDecodeError, UnicodeDecodeError:
            return "MALFORMED_JSON"
        except etree.XMLSyntaxError:
            return "MALFORMED_XML"
        return None

    @staticmethod
    def _selector_matches(content: str, selectors: tuple[str, ...]) -> int:
        if not selectors:
            return 0
        try:
            tree = html.fromstring(content)
        except ValueError, TypeError:
            return 0
        matched = 0
        for selector in selectors:
            try:
                if tree.cssselect(selector):
                    matched += 1
            except SelectorError:
                continue
        return matched

    @staticmethod
    def _result(
        status: ValidationStatus,
        diagnostic: str | None = None,
        *,
        challenge_type: ChallengeType | None = None,
        metrics: Mapping[str, bool | int | str] | None = None,
        discovered_count: int | None = None,
        byte_size: int | None = None,
    ) -> ValidationResult:
        values = dict(metrics or {})
        if byte_size is not None:
            values["byte_size"] = byte_size
        return ValidationResult(
            status=status,
            challenge_type=challenge_type,
            discovered_count=discovered_count,
            diagnostic_codes=(diagnostic,) if diagnostic is not None else (),
            metrics=values,
            validator_name=VALIDATOR_NAME,
            validator_version=VALIDATOR_VERSION,
            metrics_schema_version=METRICS_SCHEMA_VERSION,
            contract_version="1.0.0",
        )


__all__ = ["ContentValidator"]
