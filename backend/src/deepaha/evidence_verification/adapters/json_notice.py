"""Read the single-row notice API envelope; never interpret arbitrary model JSON.

Origins are decoded JSON string coordinates (RFC 6901 pointers), with the existing
HTML Reader's node coordinates inside column13. Raw JSON remains the artifact.
Reading a saved response does not authenticate its declared source URL.
"""

import json
import re
from dataclasses import replace
from hashlib import sha256

from deepaha.documents.parser import ExpectedParseError
from deepaha.evidence_verification.adapters.html import HtmlAdapter
from deepaha.evidence_verification.adapters.projection import (
    TextPart,
    canonical_html_text,
    text_projection,
)
from deepaha.evidence_verification.contracts import (
    Projection,
    ReaderIdentity,
    Representation,
    ScopeResolution,
    SourceSpan,
)

MAX_JSON_BYTES = 2_000_000
_ENVELOPE_KEYS = {"footer", "header", "message", "rows", "title", "total"}


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ExpectedParseError("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ExpectedParseError("JSON_NONFINITE_VALUE")


class JsonNoticeAdapter:
    identity = ReaderIdentity(
        "single_row_json_notice",
        "1",
        "json-notice/1;" + HtmlAdapter.identity.parse_contract,
        HtmlAdapter.identity.comparison_version,
    )
    media_types = ("application/json",)

    def normalize_quote(self, quote: str) -> str:
        return canonical_html_text(quote)

    def read(self, content: bytes) -> Representation:
        if len(content) > MAX_JSON_BYTES:
            raise ExpectedParseError("JSON_SIZE_LIMIT_EXCEEDED")
        try:
            value = json.loads(
                content.decode("utf-8-sig"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except (ValueError, UnicodeError, RecursionError) as error:
            raise ExpectedParseError("JSON_PARSE_FAILED") from error
        if (
            not isinstance(value, dict)
            or set(value) - _ENVELOPE_KEYS
            or value.get("footer", []) != []
            or value.get("title", []) != []
            or value.get("message", "") != ""
            or not isinstance(value.get("rows"), list)
            or len(value["rows"]) != 1
        ):
            raise ExpectedParseError("JSON_NOTICE_SCHEMA_UNSUPPORTED")
        row = value["rows"][0]
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("column13"), str)
            or not row["column13"].strip()
            or any(
                re.fullmatch(r"column[1-9][0-9]?", key) is None or not isinstance(text, str)
                for key, text in row.items()
            )
        ):
            raise ExpectedParseError("JSON_NOTICE_SCHEMA_UNSUPPORTED")
        projections: list[Projection] = []
        for key, text in sorted(row.items()):
            # Escaped unpaired surrogates are accepted by json.loads but cannot
            # produce a deterministic UTF-8 projection or evidence hash.
            try:
                text.encode("utf-8")
            except UnicodeError as error:
                raise ExpectedParseError("JSON_INVALID_UNICODE") from error
            pointer = f"/rows/0/{key}"
            if key == "column13":
                html = HtmlAdapter().read(text.encode())
                for projection in html.projections:
                    projections.append(
                        replace(
                            projection,
                            projection_id=pointer + "::" + projection.projection_id,
                            runs=tuple(
                                replace(
                                    run,
                                    sources=tuple(
                                        replace(
                                            source,
                                            origin_id=pointer + "::" + source.origin_id,
                                        )
                                        for source in run.sources
                                    ),
                                )
                                for run in projection.runs
                            ),
                        )
                    )
            elif text:
                plain = text_projection(
                    pointer,
                    (TextPart(text, SourceSpan(pointer, 0, len(text))),),
                    html=True,
                )
                if plain is not None:
                    projections.append(plain)
        damaged = any("\ufffd" in text for text in row.values())
        return Representation(
            self.identity,
            sha256(content).hexdigest(),
            tuple(projections),
            reliable=not damaged,
            reason_codes=("JSON_TEXT_REPLACEMENT_CHARACTER",) if damaged else (),
        )

    def resolve_scope(
        self,
        representation: Representation,
        locator: dict[str, object],
        *,
        source_url: str,
    ) -> ScopeResolution:
        keys = set(locator) - {"human_verify"}
        available = tuple(p.projection_id for p in representation.projections)
        if keys == {"url"}:
            return ScopeResolution(
                "VERIFIED" if locator["url"] == source_url else "MISMATCH",
                available,
                "ARTIFACT",
            )
        if keys == {"json_pointer"}:
            pointer = locator["json_pointer"]
            if (
                not isinstance(pointer, str)
                or re.fullmatch(r"/rows/0/column[1-9][0-9]?", pointer) is None
            ):
                return ScopeResolution("INVALID", (), "NONE")
            selected = tuple(p for p in available if p == pointer or p.startswith(pointer + "::"))
            return ScopeResolution("VERIFIED" if selected else "MISMATCH", selected, "SCOPE")
        return ScopeResolution("UNSUPPORTED" if keys else "UNBOUND", available, "ARTIFACT")
