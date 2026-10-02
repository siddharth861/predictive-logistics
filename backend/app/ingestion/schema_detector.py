import re
from difflib import SequenceMatcher
from typing import Any

from app.ingestion.aliases import CANONICAL_FIELDS


def normalize_text(value: str) -> str:
    value = value.strip().lower()

    value = re.sub(
        r"[^a-z0-9]+",
        "_",
        value,
    )

    value = re.sub(
        r"_+",
        "_",
        value,
    )

    return value.strip("_")


def tokenize(value: str) -> list[str]:
    normalized = normalize_text(value)

    return [
        token
        for token in normalized.split("_")
        if token
    ]


def similarity(
    first: str,
    second: str,
) -> float:
    return SequenceMatcher(
        None,
        normalize_text(first),
        normalize_text(second),
    ).ratio()


def get_sample_values(
    values: list[Any],
    limit: int = 10,
) -> list[Any]:
    samples = []

    for value in values:
        if value is None:
            continue

        if isinstance(value, float) and value != value:
            continue

        samples.append(value)

        if len(samples) >= limit:
            break

    return samples


def value_type_hint(
    canonical_field: str,
    values: list[Any],
) -> float:
    samples = get_sample_values(values)

    if not samples:
        return 0.0

    numeric_values = [
        value
        for value in samples
        if isinstance(value, (int, float))
    ]

    text_values = [
        value
        for value in samples
        if not isinstance(value, (int, float))
    ]

    numeric_ratio = (
        len(numeric_values) / len(samples)
    )

    text_ratio = (
        len(text_values) / len(samples)
    )

    if canonical_field in {
        "QUANTITY",
        "CONSUMPTION",
    }:
        return numeric_ratio

    if canonical_field in {
        "ITEM_NAME",
        "LOCATION",
        "VEHICLE_ID",
        "SHIPMENT_ID",
        "SOURCE_ID",
    }:
        return text_ratio

    if canonical_field == "LATITUDE":
        if not numeric_values:
            return 0.0

        valid = sum(
            -90 <= float(value) <= 90
            for value in numeric_values
        )

        return valid / len(numeric_values)

    if canonical_field == "LONGITUDE":
        if not numeric_values:
            return 0.0

        valid = sum(
            -180 <= float(value) <= 180
            for value in numeric_values
        )

        return valid / len(numeric_values)

    return 0.0


def token_score(
    column_name: str,
    canonical_field: str,
) -> float:
    column_tokens = set(
        tokenize(column_name)
    )

    expected_tokens = set(
        CANONICAL_FIELDS[
            canonical_field
        ].get("tokens", [])
    )

    if not column_tokens or not expected_tokens:
        return 0.0

    matches = column_tokens.intersection(
        expected_tokens
    )

    return len(matches) / len(
        column_tokens
    )


def alias_score(
    column_name: str,
    canonical_field: str,
) -> float:
    normalized_column = normalize_text(
        column_name
    )

    aliases = CANONICAL_FIELDS[
        canonical_field
    ]["aliases"]

    best_score = 0.0

    for alias in aliases:
        normalized_alias = normalize_text(
            alias
        )

        if normalized_column == normalized_alias:
            return 1.0

        score = similarity(
            normalized_column,
            normalized_alias,
        )

        best_score = max(
            best_score,
            score,
        )

    return best_score


def detect_column(
    column_name: str,
    values: list[Any],
) -> dict[str, Any]:

    candidates = []

    for canonical_field in CANONICAL_FIELDS:

        name_score = alias_score(
            column_name,
            canonical_field,
        )

        tokens_score = token_score(
            column_name,
            canonical_field,
        )

        type_score = value_type_hint(
            canonical_field,
            values,
        )

        if name_score == 1.0:
            confidence = 1.0

        else:
            confidence = (
                name_score * 0.60
                + tokens_score * 0.30
                + type_score * 0.10
            )

        candidates.append(
            {
                "field": canonical_field,
                "name_score": round(
                    name_score,
                    3,
                ),
                "token_score": round(
                    tokens_score,
                    3,
                ),
                "type_score": round(
                    type_score,
                    3,
                ),
                "confidence": round(
                    confidence,
                    3,
                ),
            }
        )

    candidates.sort(
        key=lambda item: item["confidence"],
        reverse=True,
    )

    best = candidates[0]

    if best["confidence"] >= 0.85:
        decision = "AUTO"

    elif best["confidence"] >= 0.60:
        decision = "SUGGEST"

    else:
        decision = "REVIEW"

    return {
        "column": column_name,
        "suggested_field": best["field"],
        "confidence": best["confidence"],
        "decision": decision,
        "candidates": candidates[:3],
        "sample_values": get_sample_values(
            values
        ),
    }


def detect_schema(
    columns: list[str],
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    results = []

    for column in columns:

        values = [
            row.get(column)
            for row in rows
        ]

        results.append(
            detect_column(
                column,
                values,
            )
        )

    return results
def detect_mapping_conflicts(
    detection_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Detect multiple source columns that are suggesting
    the same canonical field.
    """

    field_columns: dict[str, list[str]] = {}

    for result in detection_results:
        field = result["suggested_field"]
        column = result["column"]

        field_columns.setdefault(
            field,
            [],
        ).append(column)

    conflicts = []

    for field, columns in field_columns.items():

        if len(columns) <= 1:
            continue

        conflicts.append(
            {
                "canonical_field": field,
                "source_columns": columns,
                "message": (
                    f"Multiple source columns appear to "
                    f"represent {field}."
                ),
                "requires_review": True,
            }
        )

    return conflicts
def mark_unmapped_columns(
    detection_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Mark columns that do not have a sufficiently
    reliable canonical mapping.
    """

    for result in detection_results:

        if result["decision"] == "REVIEW":
            result["mapped"] = False
            result["status"] = "UNMAPPED"

        else:
            result["mapped"] = True
            result["status"] = "MAPPED"

    return detection_results