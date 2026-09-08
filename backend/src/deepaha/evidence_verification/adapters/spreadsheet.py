import json
import re
from dataclasses import dataclass, field
from hashlib import sha256
from zipfile import BadZipFile

import openpyxl
from lxml import etree
from openpyxl.utils import column_index_from_string
from openpyxl.utils.exceptions import InvalidFileException

from deepaha.documents.parser import ExpectedParseError
from deepaha.documents.spreadsheet import XLSX_MEDIA_TYPE
from deepaha.documents.spreadsheet_reading import SpreadsheetText, read_spreadsheet_text
from deepaha.evidence_verification.adapters.projection import TextPart, text_projection
from deepaha.evidence_verification.contracts import (
    Projection,
    ReaderIdentity,
    Representation,
    ScopeResolution,
    SourceSpan,
)

MAX_XLSX_BYTES = 20_000_000
MAX_XLSX_TEXT_CHARACTERS = 10_000_000


def _identity(sheet: str, row: int, column: int | None = None) -> str:
    return json.dumps([sheet, row, column], ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True, slots=True, kw_only=True)
class SpreadsheetRepresentation(Representation):
    table: SpreadsheetText = field(repr=False, compare=False)


class SpreadsheetAdapter:
    identity = ReaderIdentity(
        "xlsx_openpyxl_literal",
        "1",
        f"xlsx-cell-text/1;openpyxl={openpyxl.__version__}",
        "whitespace-collapse/1",
    )
    media_types = (XLSX_MEDIA_TYPE,)

    def normalize_quote(self, quote: str) -> str:
        return " ".join(quote.split())

    def read(self, content: bytes) -> Representation:
        if len(content) > MAX_XLSX_BYTES:
            raise ExpectedParseError("XLSX_SIZE_LIMIT_EXCEEDED")
        try:
            table = read_spreadsheet_text(content)
        except (
            BadZipFile,
            InvalidFileException,
            ValueError,
            KeyError,
            IndexError,
            etree.XMLSyntaxError,
        ) as error:
            raise ExpectedParseError("XLSX_PARSE_FAILED") from error
        projections: list[Projection] = []
        total = 0
        for sheet, rows in table.rows.items():
            for row, cells in rows.items():
                parts: list[TextPart] = []
                for column, text in cells.items():
                    identity = _identity(sheet, row, column)
                    total += len(text) * 2 + 1
                    if total > MAX_XLSX_TEXT_CHARACTERS:
                        raise ExpectedParseError("XLSX_TEXT_LIMIT_EXCEEDED")
                    if not text:
                        continue
                    part = TextPart(text, SourceSpan(identity, 0, len(text)))
                    projection = text_projection(identity, (part,))
                    if projection:
                        projections.append(projection)
                    if parts:
                        parts.append(TextPart(" ", None))
                    parts.append(part)
                projection = text_projection(_identity(sheet, row), parts)
                if projection:
                    projections.append(projection)
        return SpreadsheetRepresentation(
            self.identity, sha256(content).hexdigest(), tuple(projections), table=table
        )

    def resolve_scope(
        self, representation: Representation, locator: dict[str, object], *, source_url: str
    ) -> ScopeResolution:
        if not isinstance(representation, SpreadsheetRepresentation):
            raise ExpectedParseError("XLSX_REPRESENTATION_INVALID")
        keys = set(locator) - {"human_verify"}
        ids = tuple(p.projection_id for p in representation.projections)
        if keys not in ({"sheet", "row"}, {"sheet", "row", "col"}, {"sheet", "cell"}):
            return ScopeResolution(
                "UNSUPPORTED" if keys else "UNBOUND",
                ids,
                "ARTIFACT",
                complete=not any(representation.table.display_ambiguities.values()),
            )
        sheet, row, col = locator.get("sheet"), locator.get("row"), locator.get("col")
        if "cell" in keys:
            cell = locator["cell"]
            if (
                not isinstance(cell, str)
                or (match := re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", cell)) is None
            ):
                return ScopeResolution("INVALID", (), "NONE")
            col, row = column_index_from_string(match[1]), int(match[2])
        if (
            not isinstance(sheet, str)
            or type(row) is not int
            or not 1 <= row <= 1048576
            or (keys != {"sheet", "row"} and (type(col) is not int or not 1 <= col <= 16384))
        ):
            return ScopeResolution("INVALID", (), "NONE")
        if sheet not in representation.table.rows or row > representation.table.row_counts[sheet]:
            return ScopeResolution("MISMATCH", (), "NONE")
        if col is not None and type(col) is not int:
            return ScopeResolution("INVALID", (), "NONE")
        identity = _identity(sheet, row, col)
        ambiguous = representation.table.display_ambiguities.get(sheet, {}).get(row, {})
        complete = col not in ambiguous if col is not None else not ambiguous
        return ScopeResolution(
            "VERIFIED",
            (identity,) if identity in ids else (),
            "SCOPE",
            complete=complete,
            reason_codes=() if complete else ("XLSX_DISPLAY_VALUE_UNREAD",),
        )
