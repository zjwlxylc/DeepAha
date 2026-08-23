from pathlib import Path

import pytest

from deepaha.acquisition.contracts import SourceRecipe, SourceRecipeManifest
from deepaha.acquisition.discovery import (
    DisallowedDiscoveredUrl,
    DiscoveredLinkKind,
    DiscoveryError,
    canonicalize_discovered_url,
    discover_links,
)
from deepaha.acquisition.recipes import load_recipe_manifest

FIXTURES = Path(__file__).parents[1] / "fixtures" / "acquisition"
VALID = FIXTURES / "recipes-valid.json"
BASE_URL = "https://notices.example.gov/list/"
ALLOWED_HOSTS = ("notices.example.gov",)


def recipe(**discovery_changes: object) -> SourceRecipe:
    original = load_recipe_manifest(VALID).recipes[0]
    values = original.model_dump(mode="json")
    discovery = values["discovery"]
    assert isinstance(discovery, dict)
    discovery.update(discovery_changes)
    return SourceRecipe.model_validate(values)


def test_html_discovery_normalizes_relative_urls_deduplicates_and_preserves_order() -> None:
    content = b"""
    <html><body><main>
      <a class="notice" href="../notice/1#details">One</a>
      <a class="notice" href="https://notices.example.gov/notice/1">Duplicate</a>
      <a class="notice" href="/notice/2?from=list">Two</a>
      <a class="attachment" href="/files/notice-2.pdf#page=1">PDF</a>
      <a class="next" href="?page=2">Next</a>
    </main></body></html>
    """

    links = discover_links(
        content=content,
        media_type="text/html; charset=utf-8",
        base_url=BASE_URL,
        allowed_hosts=ALLOWED_HOSTS,
        recipe=recipe(),
    )

    assert [(item.kind, str(item.url)) for item in links] == [
        (DiscoveredLinkKind.DETAIL, "https://notices.example.gov/notice/1"),
        (DiscoveredLinkKind.DETAIL, "https://notices.example.gov/notice/2?from=list"),
        (DiscoveredLinkKind.ATTACHMENT, "https://notices.example.gov/files/notice-2.pdf"),
        (DiscoveredLinkKind.PAGINATION, "https://notices.example.gov/list/?page=2"),
    ]
    assert [item.ordinal for item in links] == [0, 1, 2, 3]


def test_html_discovery_applies_each_declared_limit() -> None:
    content = b"""
    <main>
      <a class="notice" href="/d/1">1</a><a class="notice" href="/d/2">2</a>
      <a class="attachment" href="/a/1.pdf">a1</a>
      <a class="attachment" href="/a/2.pdf">a2</a>
      <a class="next" href="?p=2">p2</a><a class="next" href="?p=3">p3</a>
    </main>
    """

    links = discover_links(
        content=content,
        media_type="text/html",
        base_url=BASE_URL,
        allowed_hosts=ALLOWED_HOSTS,
        recipe=recipe(detail_limit=1, attachment_limit=1, pagination_limit=1),
    )

    assert [item.kind for item in links] == [
        DiscoveredLinkKind.DETAIL,
        DiscoveredLinkKind.ATTACHMENT,
        DiscoveredLinkKind.PAGINATION,
    ]


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/notice/1",
        "https://user:secret@notices.example.gov/notice/1",
        "javascript:alert(1)",
        "http://127.0.0.1/private",
        "http://10.0.0.1/private",
    ],
)
def test_canonicalization_rejects_off_policy_or_private_urls(url: str) -> None:
    with pytest.raises(DisallowedDiscoveredUrl, match="DISCOVERED_URL_NOT_ALLOWED"):
        canonicalize_discovered_url(url, base_url=BASE_URL, allowed_hosts=ALLOWED_HOSTS)


def test_canonicalization_enforces_declared_path_patterns() -> None:
    with pytest.raises(DisallowedDiscoveredUrl, match="DISCOVERED_URL_NOT_ALLOWED"):
        canonicalize_discovered_url(
            "https://notices.example.gov/admin/export",
            base_url=BASE_URL,
            allowed_hosts=ALLOWED_HOSTS,
            allowed_url_patterns=("/notice/*",),
        )


def test_invalid_or_missing_html_selectors_are_visible_drift() -> None:
    for changes in (
        {"item_selector": "section.missing"},
        {"detail_link_selector": "a["},
    ):
        with pytest.raises(DiscoveryError, match="SELECTOR_DRIFT"):
            discover_links(
                content=b'<main><a class="notice" href="/d/1">one</a></main>',
                media_type="text/html",
                base_url=BASE_URL,
                allowed_hosts=ALLOWED_HOSTS,
                recipe=recipe(**changes),
            )


def test_empty_or_wrong_media_content_is_unexpected() -> None:
    for content, media_type in ((b"", "text/html"), (b"{}", "application/json")):
        with pytest.raises(DiscoveryError, match="UNEXPECTED_DISCOVERY_CONTENT"):
            discover_links(
                content=content,
                media_type=media_type,
                base_url=BASE_URL,
                allowed_hosts=ALLOWED_HOSTS,
                recipe=recipe(),
            )


def test_json_discovery_uses_declarative_item_path_and_fields() -> None:
    values = load_recipe_manifest(VALID).recipes[0].model_dump(mode="json")
    expectations = values["expectations"]
    assert isinstance(expectations, dict)
    expectations.update(structured_kind="JSON", required_selectors=[])
    values["expected_media_types"] = ["application/json"]
    discovery = values["discovery"]
    assert isinstance(discovery, dict)
    discovery.update(
        kind="JSON_ITEMS",
        item_selector=None,
        detail_link_selector=None,
        attachment_link_selector=None,
        pagination_link_selector=None,
        structured_items_path=["data", "items"],
        structured_detail_url_field="url",
        structured_attachment_url_field="attachments",
        pagination_limit=0,
    )
    structured = SourceRecipe.model_validate(values)

    links = discover_links(
        content=b'{"data":{"items":[{"url":"/d/1","attachments":["/a/1.pdf"]}]}}',
        media_type="application/json",
        base_url=BASE_URL,
        allowed_hosts=ALLOWED_HOSTS,
        recipe=structured,
    )

    assert [(item.kind.value, str(item.url)) for item in links] == [
        ("DETAIL", "https://notices.example.gov/d/1"),
        ("ATTACHMENT", "https://notices.example.gov/a/1.pdf"),
    ]


def test_xml_discovery_uses_safe_parser_and_declarative_fields() -> None:
    payload = load_recipe_manifest(VALID).recipes[0].model_dump(mode="json")
    expectations = payload["expectations"]
    assert isinstance(expectations, dict)
    expectations["structured_kind"] = "XML"
    expectations["required_selectors"] = []
    payload["expected_media_types"] = ["application/xml"]
    payload["discovery"] = {
        "kind": "XML_ITEMS",
        "item_selector": None,
        "detail_link_selector": None,
        "attachment_link_selector": None,
        "pagination_link_selector": None,
        "structured_items_path": ["channel", "item"],
        "structured_detail_url_field": "link",
        "structured_attachment_url_field": "attachment",
        "detail_limit": 20,
        "attachment_limit": 10,
        "pagination_limit": 0,
    }
    structured = SourceRecipe.model_validate(payload)

    links = discover_links(
        content=(
            b"<rss><channel><item><link>/d/1</link>"
            b"<attachment>/a/1.pdf</attachment></item></channel></rss>"
        ),
        media_type="application/xml",
        base_url=BASE_URL,
        allowed_hosts=ALLOWED_HOSTS,
        recipe=structured,
    )

    assert [item.kind.value for item in links] == ["DETAIL", "ATTACHMENT"]


def test_manifest_contract_remains_strict_after_discovery_extensions() -> None:
    manifest = SourceRecipeManifest.model_validate(load_recipe_manifest(VALID).model_dump())
    assert manifest.recipes[0].discovery.kind == "HTML_LINKS"
