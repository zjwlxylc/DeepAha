from dataclasses import dataclass, field
from hashlib import sha256

from cssselect import SelectorError
from lxml import etree

from deepaha.documents.html import _parse_html_tree
from deepaha.documents.parser import ExpectedParseError
from deepaha.evidence_verification.adapters.html_text import (
    HTML_QUOTE_CANONICALIZATION_VERSION,
    html_text_parts,
)
from deepaha.evidence_verification.adapters.projection import canonical_html_text, text_projection
from deepaha.evidence_verification.contracts import (
    Projection,
    ReaderIdentity,
    Representation,
    ScopeResolution,
)

MAX_HTML_BYTES = 20_000_000
MAX_HTML_ELEMENTS = 20_000
MAX_PROJECTION_CHARACTERS = 10_000_000


@dataclass(frozen=True, slots=True, kw_only=True)
class HtmlRepresentation(Representation):
    # A per-run locator index, excluded from the stable representation hash.
    # All comparable text and traces are in the base, serializable projections.
    root: etree._Element = field(repr=False, compare=False)


class HtmlAdapter:
    identity = ReaderIdentity(
        "html_lxml_literal",
        "1",
        f"html-text-node/1;lxml={etree.LXML_VERSION};libxml={etree.LIBXML_VERSION}",
        HTML_QUOTE_CANONICALIZATION_VERSION,
    )
    media_types = ("text/html",)

    def normalize_quote(self, quote: str) -> str:
        return canonical_html_text(quote)

    def read(self, content: bytes) -> Representation:
        if len(content) > MAX_HTML_BYTES:
            raise ExpectedParseError("HTML_SIZE_LIMIT_EXCEEDED")
        tree = _parse_html_tree(content, utf8_fallback=True, reject_incomplete=True)
        elements = [node for node in tree.iter() if isinstance(node.tag, str)]
        if len(elements) > MAX_HTML_ELEMENTS:
            raise ExpectedParseError("HTML_ELEMENT_LIMIT_EXCEEDED")
        projections: list[Projection] = []
        total = 0
        for node in elements:
            path = tree.getroottree().getpath(node)
            for joined in (False, True) if node.tag in {"td", "th"} else (False,):
                parts = html_text_parts(node, join_cell_wraps=joined)
                # Bound aggregate ancestor projections, before allocating their traces.
                total += sum(len(part.text) for part in parts)
                if total > MAX_PROJECTION_CHARACTERS:
                    raise ExpectedParseError("HTML_PROJECTION_LIMIT_EXCEEDED")
                projection = text_projection(
                    path + ("::cell-wraps" if joined else ""), parts, html=True
                )
                if projection is not None:
                    projections.append(projection)
        return HtmlRepresentation(
            self.identity, sha256(content).hexdigest(), tuple(projections), root=tree
        )

    def resolve_scope(
        self, representation: Representation, locator: dict[str, object], *, source_url: str
    ) -> ScopeResolution:
        if not isinstance(representation, HtmlRepresentation):
            raise ExpectedParseError("HTML_REPRESENTATION_INVALID")
        root = representation.root
        keys = set(locator) - {"human_verify"}
        available = {p.projection_id for p in representation.projections}
        root_path = root.getroottree().getpath(root)
        artifact_ids = (root_path,) if root_path in available else ()
        selector = locator.get("selector")
        if keys == {"selector"}:
            if not isinstance(selector, str) or not selector.strip() or len(selector) > 4096:
                return ScopeResolution("INVALID", (), "NONE")
            try:
                nodes = root.cssselect(selector)
            except SelectorError, etree.XPathError:
                return ScopeResolution("INVALID", (), "NONE")
            if not nodes:
                return ScopeResolution("MISMATCH", (), "NONE")
            paths: list[str] = []
            for node in nodes:
                path = root.getroottree().getpath(node)
                paths.extend(
                    identity for identity in (path, path + "::cell-wraps") if identity in available
                )
            return ScopeResolution("VERIFIED", tuple(dict.fromkeys(paths)), "SCOPE")
        if keys == {"url"}:
            return ScopeResolution(
                "VERIFIED" if locator["url"] == source_url else "MISMATCH", artifact_ids, "ARTIFACT"
            )
        return ScopeResolution("UNSUPPORTED" if keys else "UNBOUND", artifact_ids, "ARTIFACT")
