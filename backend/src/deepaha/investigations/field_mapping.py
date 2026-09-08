"""Versioned candidate normalization; this module never verifies or approves facts."""

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import JsonValue

from deepaha.contracts.phase4 import EducationLevel, StudentStatus
from deepaha.documents.normalization import normalize_text
from deepaha.investigations.delivery import DeliveryFact

FIELD_MAPPING_VERSION = "direct-wma-field-mapping/2.0.0"
_UNKNOWN_VALUES = frozenset({"unknown", "null", "n/a", "未知", "未说明", "未提供", "不详"})
_ALIASES = {
    "canonical_title": "canonical_title",
    "opportunity_name": "canonical_title",
    "公告名称": "canonical_title",
    "issuer_name": "issuer_name",
    "publish_unit": "issuer_name",
    "发布单位": "issuer_name",
    "education_requirements": "education_requirements",
    "学历要求": "education_requirements",
    "学历": "education_requirements",
    "major_requirements": "major_requirements",
    "专业要求": "major_requirements",
    "专业": "major_requirements",
    "age_requirements": "age_requirements",
    "年龄要求": "age_requirements",
    "credential_requirements": "credential_requirements",
    "证书要求": "credential_requirements",
    "household_registration_requirements": "household_registration_requirements",
    "户籍要求": "household_registration_requirements",
    "applicant_scope": "applicant_scope",
    "报考对象": "applicant_scope",
}
_EDUCATION_MINIMUM = {
    "大专及以上": "ASSOCIATE",
    "专科及以上": "ASSOCIATE",
    "本科及以上": "BACHELOR",
    "硕士及以上": "MASTER",
    "硕士研究生及以上": "MASTER",
    "博士研究生及以上": "DOCTORATE",
}
_LIST_FIELDS = {
    "major_requirements": "allowed_codes",
    "credential_requirements": "required_certificates",
    "household_registration_requirements": "allowed_regions",
    "applicant_scope": "student_statuses",
}


@dataclass(frozen=True, slots=True)
class FieldTarget:
    entity_id: str
    entity_kind: Literal["announcement", "unit", "position"]


@dataclass(frozen=True, slots=True)
class MappedFieldCandidate:
    entity_id: str
    original_field: str
    original_status: str
    mapping_version: str
    target_scope: Literal["OPPORTUNITY", "UNIT"] | None
    field_name: str | None
    raw_value: str | None
    normalized_value_candidate: JsonValue | None
    confidence: None
    abstained: bool
    candidate_reason_code: str
    issue_codes: tuple[str, ...]


def map_field_candidate(
    fact: DeliveryFact,
    *,
    target: FieldTarget,
) -> MappedFieldCandidate:
    """Keep candidate, source scope and unsupported conditions separate.

    target describes the WMA entity itself, not a descendant to inherit into.
    This maps values only. Evidence binding and eligibility for persistence are
    checked by the caller against the common verification receipt; this module
    cannot approve a field, prove evidence or produce a qualification.
    """
    issues: list[str] = []
    scope: Literal["OPPORTUNITY", "UNIT"] | None = None
    if target.entity_id != fact.entity_id:
        issues.append("UNKNOWN_ENTITY_TARGET_MISMATCH")
    elif target.entity_kind == "announcement":
        scope = "OPPORTUNITY"
    elif target.entity_kind == "position":
        scope = "UNIT"
    else:
        issues.append("UNKNOWN_ENTITY_GROUP_NOT_TARGETABLE")
    field_name = _ALIASES.get(fact.field.strip())
    if field_name is None:
        issues.append("UNKNOWN_FIELD_UNSUPPORTED")
    if fact.status != "CONFIRMED":
        issues.append(
            f"UNKNOWN_WMA_{fact.status}"
            if fact.status in {"CONFLICT", "UNKNOWN", "INSUFFICIENT", "UNPROCESSED"}
            else "UNKNOWN_WMA_STATUS_UNSUPPORTED"
        )
    value = None if fact.value is None else normalize_text(fact.value).strip()
    if not value or value.casefold() in _UNKNOWN_VALUES:
        issues.append("UNKNOWN_VALUE_MISSING")
    normalized = _normalize_value(field_name, value) if field_name and value else None
    if field_name is not None and value and normalized is None:
        issues.append("UNKNOWN_NORMALIZATION_UNSUPPORTED")
    return MappedFieldCandidate(
        entity_id=fact.entity_id,
        original_field=fact.field,
        original_status=fact.status,
        mapping_version=FIELD_MAPPING_VERSION,
        target_scope=scope,
        field_name=field_name,
        raw_value=fact.value,
        normalized_value_candidate=None if issues else normalized,
        confidence=None,
        abstained=bool(issues),
        candidate_reason_code=issues[0] if issues else "WMA_CANDIDATE_MAPPED",
        issue_codes=tuple(dict.fromkeys(issues)),
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate structured candidate key")
        result[key] = value
    return result


def _normalize_value(field_name: str, value: str) -> JsonValue | None:
    if field_name in {"canonical_title", "issuer_name"}:
        return value
    if field_name == "education_requirements" and value in _EDUCATION_MINIMUM:
        return {"minimum_level": _EDUCATION_MINIMUM[value]}
    if field_name == "major_requirements":
        match = re.fullmatch(r"专业代码[：:]\s*([0-9]+(?:[、,，][0-9]+)*)", value)
        if match:
            codes = re.split("[、,，]", match[1])
            if _major_codes(codes):
                return {"allowed_codes": sorted(codes)}
    try:
        structured = json.loads(value, object_pairs_hook=_unique_object)
    except ValueError, RecursionError:
        return None
    if not isinstance(structured, dict):
        return None
    if field_name == "education_requirements":
        level = structured.get("minimum_level")
        if (
            set(structured) == {"minimum_level"}
            and isinstance(level, str)
            and level in EducationLevel
        ):
            return {"minimum_level": level}
    elif field_name in _LIST_FIELDS:
        key = _LIST_FIELDS[field_name]
        items = structured.get(key)
        if (
            set(structured) == {key}
            and isinstance(items, list)
            and items
            and all(isinstance(item, str) and item and item == item.strip() for item in items)
            and len(items) == len(set(items))
            and (field_name != "major_requirements" or _major_codes(items))
            and (field_name != "applicant_scope" or all(item in StudentStatus for item in items))
        ):
            return {key: sorted(items)}
    elif field_name == "age_requirements":
        dates = structured.get("birth_date_between")
        if (
            set(structured) == {"birth_date_between"}
            and isinstance(dates, list)
            and len(dates) == 2
            and all(
                isinstance(item, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", item) for item in dates
            )
        ):
            try:
                if date.fromisoformat(dates[0]) <= date.fromisoformat(dates[1]):
                    return {"birth_date_between": dates}
            except ValueError:
                pass
    return None


def _major_codes(values: list[str]) -> bool:
    return len(values) == len(set(values)) and all(
        re.fullmatch(r"(?:[0-9]{4}|[0-9]{6})", value) is not None for value in values
    )
