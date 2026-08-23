import argparse
import json
import re
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from openpyxl import Workbook

PDF_FIXTURES = {
    "minimal-text.pdf": ("Synthetic PDF page one.", "Synthetic PDF page two."),
    "empty-text.pdf": ("",),
}


def build_pdf(page_texts: tuple[str, ...]) -> bytes:
    if not page_texts:
        raise ValueError("PDF fixture requires at least one page")
    if any(not text.isascii() for text in page_texts):
        raise ValueError("PDF fixture text must be ASCII")

    font_id = 3 + 2 * len(page_texts)
    page_ids = [3 + 2 * index for index in range(len(page_texts))]
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        (
            b"<< /Type /Pages /Kids ["
            + b" ".join(f"{page_id} 0 R".encode() for page_id in page_ids)
            + f"] /Count {len(page_texts)} >>".encode()
        ),
    ]
    for page_id, text in zip(page_ids, page_texts, strict=True):
        content_id = page_id + 1
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode()
        )
        command = (
            f"BT /F1 12 Tf 72 720 Td ({_escape_pdf_string(text)}) Tj ET".encode() if text else b""
        )
        objects.append(
            f"<< /Length {len(command)} >>\nstream\n".encode() + command + b"\nendstream"
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode())
        output.extend(body)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    return bytes(output)


def generate(output_directory: Path) -> dict[str, object]:
    output_directory.mkdir(parents=True, exist_ok=True)
    fixtures: list[dict[str, object]] = []
    for name, page_texts in PDF_FIXTURES.items():
        content = build_pdf(page_texts)
        (output_directory / name).write_bytes(content)
        fixtures.append(
            {
                "path": name,
                "byte_size": len(content),
                "content_sha256": sha256(content).hexdigest(),
                "synthetic": True,
                "business_facts": False,
            }
        )
    manifest: dict[str, object] = {
        "schema_version": "1.0.0",
        "generator": "tests/fixtures/documents/generate_fixtures.py",
        "fixtures": fixtures,
    }
    (output_directory / "pdf-fixtures.manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    workbook = build_xlsx()
    workbook_name = "minimal-table.xlsx"
    (output_directory / workbook_name).write_bytes(workbook)
    xlsx_manifest: dict[str, object] = {
        "schema_version": "1.0.0",
        "generator": "tests/fixtures/documents/generate_fixtures.py",
        "fixtures": [
            {
                "path": workbook_name,
                "byte_size": len(workbook),
                "content_sha256": sha256(workbook).hexdigest(),
                "synthetic": True,
                "business_facts": False,
                "contains_macros": False,
                "external_links": False,
            }
        ],
    }
    (output_directory / "xlsx-fixtures.manifest.json").write_text(
        json.dumps(xlsx_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {"pdf": manifest, "xlsx": xlsx_manifest}


def build_xlsx() -> bytes:
    workbook = Workbook()
    workbook.properties.created = datetime(2026, 8, 21, 0, 0, 0)
    workbook.properties.modified = datetime(2026, 8, 21, 0, 0, 0)
    workbook.properties.creator = "DeepAha synthetic fixture generator"
    workbook.properties.lastModifiedBy = "DeepAha synthetic fixture generator"

    positions = workbook.active
    if positions is None:
        raise RuntimeError("new workbook has no active worksheet")
    positions.title = "岗位表"
    positions.append(["名称", "数量", "日期", "公式"])
    positions.append(["合成岗位", 2, "2026-08-21", "=B2*2"])
    positions["A4"] = "合并说明"
    positions.merge_cells("A4:B4")

    notes = workbook.create_sheet("说明")
    notes["A1"] = "仅用于格式边界测试"

    raw = BytesIO()
    workbook.save(raw)
    workbook.close()
    return _normalize_zip(raw.getvalue())


def _normalize_zip(content: bytes) -> bytes:
    output = BytesIO()
    with (
        ZipFile(BytesIO(content), "r") as source,
        ZipFile(
            output,
            "w",
            compression=ZIP_DEFLATED,
            compresslevel=9,
        ) as target,
    ):
        for source_info in sorted(source.infolist(), key=lambda value: value.filename):
            normalized = ZipInfo(source_info.filename, date_time=(1980, 1, 1, 0, 0, 0))
            normalized.compress_type = ZIP_DEFLATED
            normalized.create_system = 0
            normalized.external_attr = 0
            normalized.extra = b""
            normalized.comment = b""
            entry_content = source.read(source_info.filename)
            if source_info.filename == "docProps/core.xml":
                entry_content, replacements = re.subn(
                    rb"(<dcterms:modified\b[^>]*>)[^<]*(</dcterms:modified>)",
                    rb"\g<1>2026-08-21T00:00:00Z\g<2>",
                    entry_content,
                )
                if replacements != 1:
                    raise RuntimeError("expected exactly one workbook modified timestamp")
            target.writestr(
                normalized,
                entry_content,
                compress_type=ZIP_DEFLATED,
                compresslevel=9,
            )
    return output.getvalue()


def _escape_pdf_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic PDF fixtures")
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(__file__).parent,
    )
    arguments = parser.parse_args()
    generate(arguments.output_directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
