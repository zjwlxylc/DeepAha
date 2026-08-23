import ipaddress
import json
from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
from fnmatch import fnmatchcase
from urllib.parse import urljoin, urlsplit, urlunsplit

from lxml import etree, html
from lxml.cssselect import SelectorError
from pydantic import HttpUrl

from deepaha.acquisition.contracts import DiscoveryKind, DiscoverySpec, SourceRecipe


class DiscoveredLinkKind(StrEnum):
    DETAIL = "DETAIL"
    ATTACHMENT = "ATTACHMENT"
    PAGINATION = "PAGINATION"


class DiscoveredLink:
    def __init__(self, *, kind: DiscoveredLinkKind, url: str, ordinal: int) -> None:
        self.kind = kind
        self.url = HttpUrl(url)
        self.ordinal = ordinal

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DiscoveredLink):
            return NotImplemented
        return (self.kind, self.url, self.ordinal) == (other.kind, other.url, other.ordinal)


class DiscoveryError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class DisallowedDiscoveredUrl(DiscoveryError):
    def __init__(self) -> None:
        super().__init__("DISCOVERED_URL_NOT_ALLOWED")


def canonicalize_discovered_url(
    raw_url: str,
    *,
    base_url: str,
    allowed_hosts: tuple[str, ...],
    allowed_url_patterns: tuple[str, ...] = ("/*",),
) -> str:
    candidate = urljoin(base_url, raw_url.strip())
    parsed = urlsplit(candidate)
    host = (parsed.hostname or "").lower().rstrip(".")
    normalized_allowed_hosts = {value.lower().rstrip(".") for value in allowed_hosts}
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or host not in normalized_allowed_hosts
        or _is_non_public_literal(host)
        or not any(fnmatchcase(parsed.path or "/", pattern) for pattern in allowed_url_patterns)
    ):
        raise DisallowedDiscoveredUrl
    try:
        port = parsed.port
    except ValueError as error:
        raise DisallowedDiscoveredUrl from error
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


def discover_links(
    *,
    content: bytes,
    media_type: str,
    base_url: str,
    allowed_hosts: tuple[str, ...],
    recipe: SourceRecipe,
) -> tuple[DiscoveredLink, ...]:
    if recipe.discovery.kind is DiscoveryKind.NONE:
        return ()
    if not content:
        raise DiscoveryError("UNEXPECTED_DISCOVERY_CONTENT")

    raw_links = _extract_links(content, media_type, recipe.discovery)
    limits = {
        DiscoveredLinkKind.DETAIL: recipe.discovery.detail_limit,
        DiscoveredLinkKind.ATTACHMENT: recipe.discovery.attachment_limit,
        DiscoveredLinkKind.PAGINATION: recipe.discovery.pagination_limit,
    }
    counts = {kind: 0 for kind in DiscoveredLinkKind}
    seen: set[str] = set()
    discovered: list[DiscoveredLink] = []
    for kind, raw_url in raw_links:
        if counts[kind] >= limits[kind]:
            continue
        url = canonicalize_discovered_url(
            raw_url,
            base_url=base_url,
            allowed_hosts=allowed_hosts,
            allowed_url_patterns=recipe.allowed_url_patterns,
        )
        if url in seen:
            continue
        seen.add(url)
        counts[kind] += 1
        discovered.append(DiscoveredLink(kind=kind, url=url, ordinal=len(discovered)))
    return tuple(discovered)


def _is_non_public_literal(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return not address.is_global


def _extract_links(
    content: bytes,
    media_type: str,
    spec: DiscoverySpec,
) -> tuple[tuple[DiscoveredLinkKind, str], ...]:
    normalized_media_type = media_type.partition(";")[0].strip().lower()
    if spec.kind is DiscoveryKind.HTML_LINKS:
        if normalized_media_type not in {"application/xhtml+xml", "text/html"}:
            raise DiscoveryError("UNEXPECTED_DISCOVERY_CONTENT")
        return _extract_html_links(content, spec)
    if spec.kind is DiscoveryKind.JSON_ITEMS:
        if normalized_media_type != "application/json" and not normalized_media_type.endswith(
            "+json"
        ):
            raise DiscoveryError("UNEXPECTED_DISCOVERY_CONTENT")
        return _extract_json_links(content, spec)
    if normalized_media_type not in {"application/xml", "text/xml"} and not (
        normalized_media_type.endswith("+xml")
    ):
        raise DiscoveryError("UNEXPECTED_DISCOVERY_CONTENT")
    return _extract_xml_links(content, spec)


def _extract_html_links(
    content: bytes, spec: DiscoverySpec
) -> tuple[tuple[DiscoveredLinkKind, str], ...]:
    try:
        tree = html.fromstring(content)
        roots = tree.cssselect(spec.item_selector or "")
        if not roots:
            raise DiscoveryError("SELECTOR_DRIFT")
        values: list[tuple[DiscoveredLinkKind, str]] = []
        selectors = (
            (DiscoveredLinkKind.DETAIL, spec.detail_link_selector),
            (DiscoveredLinkKind.ATTACHMENT, spec.attachment_link_selector),
            (DiscoveredLinkKind.PAGINATION, spec.pagination_link_selector),
        )
        for kind, selector in selectors:
            if selector is None:
                continue
            for root in roots:
                for node in root.cssselect(selector):
                    href = node.get("href")
                    if href:
                        values.append((kind, href))
        return tuple(values)
    except DiscoveryError:
        raise
    except (SelectorError, TypeError, ValueError, etree.ParserError) as error:
        raise DiscoveryError("SELECTOR_DRIFT") from error


def _extract_json_links(
    content: bytes, spec: DiscoverySpec
) -> tuple[tuple[DiscoveredLinkKind, str], ...]:
    try:
        value: object = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise DiscoveryError("UNEXPECTED_DISCOVERY_CONTENT") from error
    items = _traverse_mapping(value, spec.structured_items_path)
    if not isinstance(items, list):
        raise DiscoveryError("SELECTOR_DRIFT")
    values: list[tuple[DiscoveredLinkKind, str]] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise DiscoveryError("SELECTOR_DRIFT")
        values.extend(_structured_item_links(item, spec))
    return tuple(values)


def _extract_xml_links(
    content: bytes, spec: DiscoverySpec
) -> tuple[tuple[DiscoveredLinkKind, str], ...]:
    parser = etree.XMLParser(
        no_network=True,
        recover=False,
        resolve_entities=False,
        huge_tree=False,
    )
    try:
        root = etree.fromstring(content, parser=parser)
    except etree.XMLSyntaxError as error:
        raise DiscoveryError("UNEXPECTED_DISCOVERY_CONTENT") from error
    nodes = [root]
    for component in spec.structured_items_path:
        nodes = [child for node in nodes for child in node if _local_name(child.tag) == component]
    if not nodes:
        raise DiscoveryError("SELECTOR_DRIFT")
    values: list[tuple[DiscoveredLinkKind, str]] = []
    for node in nodes:
        fields = {_local_name(child.tag): (child.text or "").strip() for child in node}
        values.extend(_structured_item_links(fields, spec))
    return tuple(values)


def _traverse_mapping(value: object, path: Sequence[str]) -> object:
    current = value
    for component in path:
        if not isinstance(current, Mapping) or component not in current:
            raise DiscoveryError("SELECTOR_DRIFT")
        current = current[component]
    return current


def _structured_item_links(
    item: Mapping[str, object], spec: DiscoverySpec
) -> Iterable[tuple[DiscoveredLinkKind, str]]:
    yield from _field_links(item, spec.structured_detail_url_field, DiscoveredLinkKind.DETAIL)
    yield from _field_links(
        item,
        spec.structured_attachment_url_field,
        DiscoveredLinkKind.ATTACHMENT,
    )


def _field_links(
    item: Mapping[str, object],
    field: str | None,
    kind: DiscoveredLinkKind,
) -> Iterable[tuple[DiscoveredLinkKind, str]]:
    if field is None:
        return
    value = item.get(field)
    if isinstance(value, str) and value.strip():
        yield kind, value
    elif isinstance(value, list):
        for candidate in value:
            if not isinstance(candidate, str):
                raise DiscoveryError("SELECTOR_DRIFT")
            if candidate.strip():
                yield kind, candidate
    elif value is not None:
        raise DiscoveryError("SELECTOR_DRIFT")


def _local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", maxsplit=1)[-1]


__all__ = [
    "DisallowedDiscoveredUrl",
    "DiscoveredLink",
    "DiscoveredLinkKind",
    "DiscoveryError",
    "canonicalize_discovered_url",
    "discover_links",
]
