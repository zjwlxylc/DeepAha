"""Format-independent, versioned projection anchors; legacy schemas stay unchanged."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

READER_BLOCK_CONTRACT = "reader-document-block-contract-v1"
READER_BLOCK_PARSER = "deepaha-evidence-reader"
READER_EVIDENCE_VERSION = "0.9.0"

Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
IdentityText = Annotated[str, StringConstraints(min_length=1, max_length=1024)]


class ReaderIdentitySchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: IdentityText
    version: IdentityText
    parse_contract: IdentityText
    comparison_version: IdentityText


class ReaderAnchor(BaseModel):
    """A Reader projection, not an original-file byte offset or a fact assertion.

    The representation hash pins the complete character-to-origin trace. An
    anchor becomes usable only after the registered Reader replays it from raw
    bytes. Format-specific coordinates live in that Reader, not arbitrary JSON.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["reader_anchor"] = "reader_anchor"
    anchor_schema: Literal["reader-projection/1"] = "reader-projection/1"
    reader: ReaderIdentitySchema
    artifact_sha256: Digest
    representation_sha256: Digest
    projection_id: Annotated[str, StringConstraints(min_length=1, max_length=16384)]
    projection_sha256: Digest
    text_start: Annotated[int, Field(ge=0, le=0)]
    text_end: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def whole_projection(self) -> Self:
        if self.text_start != 0:
            raise ValueError("a document block must anchor the whole projection")
        return self
