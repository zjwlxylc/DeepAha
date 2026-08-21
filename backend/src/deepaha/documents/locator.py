from hashlib import sha256

from deepaha.contracts.phase2 import HtmlSelectorLocator, PdfPageTextLocator
from deepaha.documents.html import _normalized_visible_text, _parse_html_tree
from deepaha.documents.parser import ExpectedParseError
from deepaha.documents.pdf import _extract_page_text, _read_pdf


class LocatorReplayError(RuntimeError):
    pass


def replay_html_locator(content: bytes, locator: HtmlSelectorLocator) -> str:
    tree = _parse_html_tree(content)
    nodes = tree.cssselect(locator.selector)
    if len(nodes) != 1:
        raise LocatorReplayError(
            f"HTML locator must resolve to exactly one node; found {len(nodes)}"
        )
    text = _normalized_visible_text(nodes[0])
    if sha256(text.encode()).hexdigest() != locator.text_sha256:
        raise LocatorReplayError("HTML locator text hash mismatch")
    return text


def replay_pdf_locator(content: bytes, locator: PdfPageTextLocator) -> str:
    if not isinstance(locator.page_number, int) or locator.page_number < 1:
        raise LocatorReplayError("PDF locator page number must be 1-based")
    try:
        reader = _read_pdf(content)
        if locator.page_number > len(reader.pages):
            raise LocatorReplayError("PDF locator page does not exist")
        page_text = _extract_page_text(reader, locator.page_number - 1)
    except ExpectedParseError as error:
        raise LocatorReplayError(f"PDF locator input cannot be parsed: {error.code}") from error

    if (
        not isinstance(locator.text_start, int)
        or not isinstance(locator.text_end, int)
        or locator.text_start < 0
        or locator.text_end <= locator.text_start
        or locator.text_end > len(page_text)
    ):
        raise LocatorReplayError("PDF locator text offsets are outside the page text")
    text = page_text[locator.text_start : locator.text_end]
    if sha256(text.encode()).hexdigest() != locator.text_sha256:
        raise LocatorReplayError("PDF locator text hash mismatch")
    return text
