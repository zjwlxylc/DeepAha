import os

from deepaha.evidence_verification.adapters.html import HtmlAdapter
from deepaha.evidence_verification.adapters.json_notice import JsonNoticeAdapter
from deepaha.evidence_verification.adapters.legacy_doc import LegacyDocAdapter
from deepaha.evidence_verification.adapters.pdf import PdfAdapter
from deepaha.evidence_verification.adapters.spreadsheet import SpreadsheetAdapter
from deepaha.evidence_verification.registry import AdapterRegistry


def default_registry() -> AdapterRegistry:
    image_id = os.environ.get("DEEPAHA_DOC_READER_IMAGE")
    return AdapterRegistry(
        (
            HtmlAdapter(),
            PdfAdapter(),
            SpreadsheetAdapter(),
            JsonNoticeAdapter(),
            *((LegacyDocAdapter(image_id),) if image_id else ()),
        )
    )
