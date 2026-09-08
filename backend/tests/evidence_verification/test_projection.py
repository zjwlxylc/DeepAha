from random import Random

from deepaha.evidence_verification.adapters.projection import (
    TextPart,
    canonical_html_text,
    text_projection,
)
from deepaha.evidence_verification.contracts import SourceSpan


def test_traced_projection_preserves_established_c14n_across_node_splits() -> None:
    random = Random(20260908)
    alphabet = "学历A9、 \r\n\t\u00a0\u200b\ufeff\u200c\u200d"
    for _ in range(2000):
        text = "".join(random.choice(alphabet) for _ in range(random.randrange(30)))
        split = random.randrange(len(text) + 1)
        parts = tuple(
            TextPart(value, SourceSpan(f"node:{number}", 0, len(value)))
            for number, value in enumerate((text[:split], text[split:]))
            if value
        )
        projection = text_projection("combined", parts, html=True)
        assert (projection.text if projection else "") == canonical_html_text(text)
        if projection:
            for run in projection.runs:
                assert all(span.start < span.end for span in run.sources)


def test_collapsed_space_across_text_nodes_maps_both_original_ranges() -> None:
    projection = text_projection(
        "combined",
        (
            TextPart("A \t", SourceSpan("left", 0, 3)),
            TextPart("\n B", SourceSpan("right", 0, 3)),
        ),
    )
    assert projection is not None and projection.text == "A B"
    assert projection.source_spans(1, 2) == (SourceSpan("left", 1, 3), SourceSpan("right", 0, 2))
