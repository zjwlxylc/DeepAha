import re
from hashlib import sha256
from typing import cast

from lxml import etree

from deepaha.contracts.phase2 import EvidenceLocatorV02, HtmlSelectorLocator
from deepaha.documents.blocks import ParsedBlock, validate_parsed_blocks
from deepaha.documents.normalization import normalize_text
from deepaha.documents.parser import (
    P9B_BLOCK_PARSE_CONTRACT_VERSION,
    ExpectedParseError,
    ParsedDocument,
)

_LANGUAGE_PATTERN = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*")
_EXCLUDED_TAGS = frozenset({"script", "style", "noscript", "template"})
_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "body",
        "dd",
        "div",
        "dl",
        "dt",
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
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)


class _RejectExternalResolver(etree.Resolver):
    def resolve(  # type: ignore[override]  # lxml-stubs omits runtime context argument
        self,
        url: str,
        public_id: str,
        context: object,
    ) -> object:
        del url, public_id
        return self.resolve_string("", context, base_url=None)


class LxmlHtmlParser:
    name = "html_lxml"
    version = "0.2.0"
    parse_contract_version = "phase2-locator-contract-v0.2.0"
    emit_document_blocks = False

    def supports(self, media_type: str) -> bool:
        return media_type.partition(";")[0].strip().lower() == "text/html"

    def parse(self, content: bytes, *, artifact_sha256: str) -> ParsedDocument:
        if sha256(content).hexdigest() != artifact_sha256:
            raise ValueError("artifact SHA-256 does not match HTML bytes")

        tree = _parse_html_tree(content)
        root = _select_content_root(tree)
        blocks = _leaf_text_blocks(root)
        block_texts = [_normalized_visible_text(node) for node in blocks]
        block_texts = [text for text in block_texts if text]
        if not block_texts:
            raise ExpectedParseError("HTML_TEXT_EMPTY")

        locators: list[EvidenceLocatorV02] = []
        parsed_blocks: list[ParsedBlock] = []
        for node, text in zip(blocks, block_texts, strict=True):
            selector = _stable_selector(node)
            locators.append(
                HtmlSelectorLocator(
                    schema_version="0.2.0",
                    kind="html_selector",
                    selector=selector,
                    text_sha256=sha256(text.encode()).hexdigest(),
                )
            )
            parsed_blocks.append(
                ParsedBlock(
                    block_type="HTML_ELEMENT",
                    canonical_text_or_value=text,
                    structural_locator={
                        "kind": "html_element_span",
                        "selector": selector,
                        "text_start": 0,
                        "text_end": len(text),
                    },
                    parent_ordinal=None,
                )
            )

        title_nodes = _xpath_elements(tree, "//head/title")
        title = _normalized_visible_text(title_nodes[0]) if title_nodes else ""
        language_value = tree.get("lang", "") if _tag_name(tree) == "html" else ""
        language = (
            language_value if _LANGUAGE_PATTERN.fullmatch(language_value) is not None else "und"
        )
        return ParsedDocument(
            title=title or None,
            published_at=None,
            language=language,
            normalized_text=normalize_text("\n\n".join(block_texts) + "\n"),
            locators=tuple(locators),
            needs_review_reasons=(),
            blocks=(
                validate_parsed_blocks(tuple(parsed_blocks)) if self.emit_document_blocks else ()
            ),
        )


class P9BHtmlDocumentParser(LxmlHtmlParser):
    version = "0.8.0"
    parse_contract_version = P9B_BLOCK_PARSE_CONTRACT_VERSION
    emit_document_blocks = True


def _parse_html_tree(content: bytes) -> etree._Element:
    parser = etree.HTMLParser(no_network=True, recover=True, huge_tree=False)
    parser.resolvers.add(_RejectExternalResolver())
    try:
        tree = etree.fromstring(content, parser=parser)
    except (etree.ParserError, etree.XMLSyntaxError) as error:
        code = "HTML_TEXT_EMPTY" if not content.strip() else "HTML_PARSE_FAILED"
        raise ExpectedParseError(code) from error
    if tree is None:
        raise ExpectedParseError("HTML_TEXT_EMPTY")
    _remove_excluded_nodes(tree)
    return tree


def _remove_excluded_nodes(tree: etree._Element) -> None:
    for node in tuple(tree.iter()):
        if _tag_name(node) not in _EXCLUDED_TAGS:
            continue
        parent = node.getparent()
        if parent is None:
            continue
        if node.tail:
            previous = node.getprevious()
            if previous is None:
                parent.text = (parent.text or "") + node.tail
            else:
                previous.tail = (previous.tail or "") + node.tail
        parent.remove(node)


def _select_content_root(tree: etree._Element) -> etree._Element:
    main_nodes = _xpath_elements(tree, "//main")
    if len(main_nodes) == 1:
        return main_nodes[0]
    article_nodes = _xpath_elements(tree, "//article")
    if len(article_nodes) == 1:
        return article_nodes[0]
    body_nodes = _xpath_elements(tree, "//body")
    return body_nodes[0] if body_nodes else tree


def _leaf_text_blocks(root: etree._Element) -> list[etree._Element]:
    candidates: list[etree._Element] = []
    for node in root.iter():
        if _tag_name(node) not in _BLOCK_TAGS or not _normalized_visible_text(node):
            continue
        has_text_block_descendant = any(
            _tag_name(descendant) in _BLOCK_TAGS and _normalized_visible_text(descendant)
            for descendant in node.iterdescendants()
        )
        if not has_text_block_descendant:
            candidates.append(node)
    if candidates:
        return candidates
    return [root] if _normalized_visible_text(root) else []


def _normalized_visible_text(node: etree._Element) -> str:
    fragments = [
        value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
        for value in node.itertext()
    ]
    return normalize_text(" ".join("".join(fragments).split()))


def _stable_selector(node: etree._Element) -> str:
    parts: list[str] = []
    current: etree._Element | None = node
    while current is not None:
        tag = _tag_name(current)
        if tag:
            index = 1 + sum(
                1 for sibling in current.itersiblings(preceding=True) if _tag_name(sibling) == tag
            )
            parts.append(f"{tag}:nth-of-type({index})")
        current = current.getparent()
    return " > ".join(reversed(parts))


def _tag_name(node: etree._Element) -> str:
    return node.tag.lower() if isinstance(node.tag, str) else ""


def _xpath_elements(tree: etree._Element, expression: str) -> list[etree._Element]:
    result = tree.xpath(expression)
    if not isinstance(result, list) or not all(
        isinstance(value, etree._Element) for value in result
    ):
        raise RuntimeError(f"element XPath returned a non-element result: {expression}")
    return cast(list[etree._Element], result)
