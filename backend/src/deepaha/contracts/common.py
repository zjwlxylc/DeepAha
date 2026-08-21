from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, Field, StringConstraints


def require_uuid7(value: UUID) -> UUID:
    if value.version != 7:
        raise ValueError("value must be an RFC 9562 UUIDv7")
    return value


def normalize_instant(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("instant must include timezone information")
    return value.astimezone(UTC)


EntityId = Annotated[UUID, AfterValidator(require_uuid7)]
Instant = Annotated[datetime, AfterValidator(normalize_instant)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
SourcePublicId = Annotated[str, StringConstraints(pattern=r"^src_[0-9a-f]{32}$")]
OpportunityPublicId = Annotated[str, StringConstraints(pattern=r"^opp_[0-9a-f]{32}$")]
S3Uri = Annotated[
    str,
    StringConstraints(pattern=r"^s3://[a-z0-9][a-z0-9.-]*/[^\s]+$"),
]
Confidence = Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1"))]
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
LanguageTag = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$"),
]
PositiveByteSize = Annotated[int, Field(gt=0)]
VersionNumber = Annotated[int, Field(ge=1)]
HttpStatus = Annotated[int, Field(ge=100, le=599)]
