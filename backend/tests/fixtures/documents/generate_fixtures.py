import argparse
import json
from hashlib import sha256
from pathlib import Path

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
    return manifest


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
