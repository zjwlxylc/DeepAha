from hashlib import sha256

from deepaha.contracts.phase2 import HtmlSelectorLocator
from deepaha.documents.html import _normalized_visible_text, _parse_html_tree


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
