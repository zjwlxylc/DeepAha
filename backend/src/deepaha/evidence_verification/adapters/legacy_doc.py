"""Isolated legacy Word reading, explicitly requiring a human layout check.

DocBook node coordinates refer to a pinned converter's reading of original DOC
bytes, not to Word page numbers or to a newly acquired official document.
"""

import re
import subprocess
from contextlib import suppress
from hashlib import sha256
from tempfile import TemporaryFile
from uuid import uuid4

from lxml import etree

from deepaha.documents.parser import ExpectedParseError
from deepaha.evidence_verification.adapters.html_text import html_text_parts
from deepaha.evidence_verification.adapters.projection import canonical_html_text, text_projection
from deepaha.evidence_verification.contracts import (
    LocatorStatus,
    Projection,
    ReaderIdentity,
    Representation,
    ScopeResolution,
)

MAX_DOC_BYTES = 10_000_000
MAX_XML_BYTES = 20_000_000
_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
_TAGS = {
    "book",
    "bookinfo",
    "chapter",
    "title",
    "date",
    "para",
    "emphasis",
    "section",
    "sect1",
    "sect2",
    "sect3",
    "itemizedlist",
    "orderedlist",
    "listitem",
    "table",
    "informaltable",
    "tgroup",
    "colspec",
    "thead",
    "tbody",
    "row",
    "entry",
}


def convert_doc(content: bytes, image_id: str) -> bytes:
    name = "deepaha-doc-read-" + uuid4().hex
    command = [
        "docker",
        "run",
        "--name",
        name,
        "--rm",
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=32m",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        "128m",
        "--cpus",
        "1",
        "--pids-limit",
        "32",
        "--log-driver",
        "none",
        "--user",
        "65534:65534",
        "--entrypoint",
        "antiword",
        "-i",
        image_id,
        "-x",
        "db",
        "-",
    ]
    with TemporaryFile() as output, TemporaryFile() as errors:
        try:
            completed = subprocess.run(
                command,
                input=content,
                stdout=output,
                stderr=errors,
                timeout=30,
                check=False,
            )
        except FileNotFoundError as error:
            raise ExpectedParseError("DOC_READER_UNAVAILABLE") from error
        except subprocess.TimeoutExpired as error:
            # Killing the Docker client does not necessarily stop its container.
            with suppress(OSError, subprocess.TimeoutExpired):
                subprocess.run(
                    ["docker", "rm", "--force", name],
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
            raise ExpectedParseError("DOC_READER_TIMEOUT") from error
        except OSError as error:
            raise ExpectedParseError("DOC_READER_UNAVAILABLE") from error
        output.seek(0)
        errors.seek(0)
        if completed.returncode or errors.read(1):
            raise ExpectedParseError("DOC_CONVERSION_FAILED")
        content_xml = output.read(MAX_XML_BYTES + 1)
        if len(content_xml) > MAX_XML_BYTES:
            raise ExpectedParseError("DOC_TEXT_LIMIT_EXCEEDED")
        return content_xml


class LegacyDocAdapter:
    media_types = ("application/msword",)

    def __init__(self, image_id: str) -> None:
        if _IMAGE_ID.fullmatch(image_id) is None:
            raise ValueError("legacy DOC reader requires an immutable local image ID")
        self.image_id = image_id
        self.identity = ReaderIdentity(
            "legacy_doc_antiword",
            "1",
            "antiword-docbook/1;image=" + image_id,
            "html-quote-c14n/1",
        )

    def normalize_quote(self, quote: str) -> str:
        return canonical_html_text(quote)

    def read(self, content: bytes) -> Representation:
        if len(content) > MAX_DOC_BYTES:
            raise ExpectedParseError("DOC_SIZE_LIMIT_EXCEEDED")
        if len(content) < 512 or not content.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            raise ExpectedParseError("DOC_SIGNATURE_INVALID")
        xml = convert_doc(content, self.image_id)
        if len(xml) > MAX_XML_BYTES:
            raise ExpectedParseError("DOC_TEXT_LIMIT_EXCEEDED")
        try:
            root = etree.fromstring(xml, etree.XMLParser(resolve_entities=False, no_network=True))
        except etree.XMLSyntaxError as error:
            raise ExpectedParseError("DOC_CONVERSION_INVALID") from error
        if root.tag != "book":
            raise ExpectedParseError("DOC_CONVERSION_INVALID")
        elements = list(root.iter())
        if len(elements) > 100_000:
            raise ExpectedParseError("DOC_ELEMENT_LIMIT_EXCEEDED")
        if any(node.tag not in _TAGS for node in elements):
            raise ExpectedParseError("DOC_CONTENT_REQUIRES_MANUAL_READING")
        projections: list[Projection] = []
        for node in elements:
            if node.tag not in {"para", "title"} or any(
                parent.tag == "bookinfo" for parent in node.iterancestors()
            ):
                continue
            projection = text_projection(
                root.getroottree().getpath(node),
                html_text_parts(node),
                html=True,
            )
            if projection:
                projections.append(projection)
        if not projections:
            raise ExpectedParseError("DOC_TEXT_EMPTY")
        return Representation(self.identity, sha256(content).hexdigest(), tuple(projections))

    def resolve_scope(
        self,
        representation: Representation,
        locator: dict[str, object],
        *,
        source_url: str,
    ) -> ScopeResolution:
        keys = set(locator) - {"human_verify"}
        ids = tuple(p.projection_id for p in representation.projections)
        if keys == {"url"}:
            status: LocatorStatus = "VERIFIED" if locator["url"] == source_url else "MISMATCH"
            return ScopeResolution(
                status,
                ids,
                "ARTIFACT",
                requires_human_review=True,
                reason_codes=("DOC_LAYOUT_REQUIRES_HUMAN_REVIEW",),
            )
        return ScopeResolution(
            "UNSUPPORTED" if keys else "UNBOUND",
            ids,
            "ARTIFACT",
            requires_human_review=True,
            reason_codes=("DOC_LAYOUT_REQUIRES_HUMAN_REVIEW",),
        )
