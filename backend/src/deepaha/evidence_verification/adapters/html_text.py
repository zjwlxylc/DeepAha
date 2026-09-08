import re

from lxml import etree

from deepaha.evidence_verification.adapters.projection import HAN, TextPart
from deepaha.evidence_verification.contracts import SourceSpan

HTML_QUOTE_CANONICALIZATION_VERSION = "html-quote-c14n/1"
_HTML_TEXT_BOUNDARIES = frozenset(
    [
        "address",
        "article",
        "aside",
        "blockquote",
        "body",
        "br",
        "caption",
        "dd",
        "details",
        "dialog",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hgroup",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "summary",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    ]
)


def _html_quote_text(root: etree._Element, *, join_cell_wraps: bool = False) -> str:
    return "".join(part.text for part in html_text_parts(root, join_cell_wraps=join_cell_wraps))


def html_text_parts(root: etree._Element, *, join_cell_wraps: bool = False) -> list[TextPart]:
    """Preserve inline text while separating paragraphs, rows and cells.

    This checks source text structure, not CSS layout or the meaning of a fact.
    The original artifact bytes remain untouched.
    """
    # Only an explicitly selected cell may join adjacent Han text across p/br
    # layout boundaries. None records an extractor-generated separator; literal
    # source whitespace and all row/cell/other block boundaries remain distinct.
    cell_wraps = join_cell_wraps and root.tag in {"td", "th"}
    parts: list[TextPart | None] = []
    tree = root.getroottree()
    for event, node in etree.iterwalk(root, events=("start", "end", "comment", "pi")):
        if node.tag in _HTML_TEXT_BOUNDARIES:
            parts.append(None if cell_wraps and node.tag in {"p", "br"} else TextPart(" ", None))
        if event == "start" and isinstance(node.tag, str) and node.text:
            parts.append(
                TextPart(node.text, SourceSpan(tree.getpath(node) + "::text", 0, len(node.text)))
            )
        elif event != "start" and node is not root and node.tail:
            parts.append(
                TextPart(node.tail, SourceSpan(tree.getpath(node) + "::tail", 0, len(node.tail)))
            )
    rendered: list[TextPart] = []
    pending_wrap = False
    for part in parts:
        if part is None:
            pending_wrap = True
        elif part.text:
            if (
                pending_wrap
                and rendered
                and not (
                    re.fullmatch(HAN, rendered[-1].text[-1]) and re.fullmatch(HAN, part.text[0])
                )
            ):
                rendered.append(TextPart(" ", None))
            rendered.append(part)
            pending_wrap = False
    return rendered
