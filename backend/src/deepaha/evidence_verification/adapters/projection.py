import re
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

from deepaha.evidence_verification.contracts import Projection, ProjectionRun, SourceSpan

HAN = r"[\u3400-\u4dbf\u4e00-\u9fff]"
HAN_FORMAT_MARKS = re.compile(rf"(?<={HAN})[\u200b\ufeff]+(?={HAN})")
_HTML_TOKENS = re.compile(rf"\s+|(?<={HAN})[\u200b\ufeff]+(?={HAN})")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class TextPart:
    text: str
    # None is ONLY for a separator introduced by this Reader, never missing provenance.
    source: SourceSpan | None


def canonical_html_text(text: str) -> str:
    # Preserve the established html-quote-c14n/1 policy, including case,
    # punctuation, original Han spaces, ZWJ/ZWNJ and bidi controls. No NFC/NFKC.
    return " ".join(HAN_FORMAT_MARKS.sub("", text.strip().lstrip("\ufeff")).split())


def text_projection(
    identity: str, parts: Sequence[TextPart], *, html: bool = False
) -> Projection | None:
    """Collapse whitespace with a trace to original Reader text coordinates.

    This is a comparison view. Neither original bytes nor Reader text is edited.
    Runs are split at origin boundaries so partial matches retain exact offsets.
    """
    raw = "".join(part.text for part in parts)
    if not raw:
        return None
    original_runs: list[ProjectionRun] = []
    offset = 0
    for part in parts:
        if not part.text:
            continue
        if part.source and part.source.end - part.source.start != len(part.text):
            raise ValueError("Reader text part must map linearly to original text")
        original_runs.append(
            ProjectionRun(offset, offset + len(part.text), (part.source,) if part.source else ())
        )
        offset += len(part.text)
    ends = [run.end for run in original_runs]

    def slices(start: int, end: int) -> list[tuple[str, tuple[SourceSpan, ...]]]:
        values: list[tuple[str, tuple[SourceSpan, ...]]] = []
        if start >= end:
            return values
        index = bisect_right(ends, start)
        while index < len(original_runs) and original_runs[index].start < end:
            run = original_runs[index]
            lo, hi = max(start, run.start), min(end, run.end)
            sources: tuple[SourceSpan, ...] = ()
            if run.sources:
                source = run.sources[0]
                sources = (
                    SourceSpan(
                        source.origin_id,
                        source.start + lo - run.start,
                        source.start + hi - run.start,
                    ),
                )
            values.append((raw[lo:hi], sources))
            index += 1
        return values

    lo, hi = len(raw) - len(raw.lstrip()), len(raw.rstrip())
    if html:
        while lo < hi and raw[lo] == "\ufeff":
            lo += 1
        while lo < hi and raw[lo].isspace():
            lo += 1
    if lo >= hi:
        return None
    tokens = _HTML_TOKENS if html else _WHITESPACE
    chunks: list[str] = []
    runs: list[ProjectionRun] = []
    cursor = 0

    def append(text: str, sources: tuple[SourceSpan, ...]) -> None:
        nonlocal cursor
        if text:
            chunks.append(text)
            runs.append(ProjectionRun(cursor, cursor + len(text), sources))
            cursor += len(text)

    position = lo
    for match in tokens.finditer(raw, lo, hi):
        for text, sources in slices(position, match.start()):
            append(text, sources)
        if match[0].isspace():
            sources = tuple(
                source for _, group in slices(match.start(), match.end()) for source in group
            )
            append(" ", sources)
        # Only documented Han-adjacent format marks are omitted.
        position = match.end()
    for text, sources in slices(position, hi):
        append(text, sources)
    return Projection(identity, "".join(chunks), tuple(runs)) if chunks else None
