from deepaha.evidence_verification.adapters.html import HtmlAdapter
from deepaha.evidence_verification.adapters.pdf import PdfAdapter
from deepaha.evidence_verification.adapters.spreadsheet import SpreadsheetAdapter
from deepaha.evidence_verification.registry import AdapterRegistry


def default_registry() -> AdapterRegistry:
    return AdapterRegistry((HtmlAdapter(), PdfAdapter(), SpreadsheetAdapter()))
