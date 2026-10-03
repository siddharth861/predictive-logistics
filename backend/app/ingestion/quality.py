from typing import Any


def calculate_quality_score(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Calculate an overall data quality score from validation results.

    The score is based on:
    - Percentage of valid records
    - Number of ERROR rules
    - Number of WARNING rules

    The result is designed to be consumed by the API
    and later by the Data Observatory frontend.
    """

    total_records = len(results)

    if total_records == 0:
        return {
            "score": 100.0,
            "grade": "A",
            "total_records": 0,
            "valid_records": 0,
            "invalid_records": 0,
            "error_count": 0,
            "warning_count": 0,
        }

    valid_records = sum(
        1
        for result in results
        if result.get("valid") is True
    )

    invalid_records = (
        total_records - valid_records
    )

    error_count = 0
    warning_count = 0

    for result in results:
        for rule in result.get(
            "rule_results",
            [],
        ):
            severity = str(
                rule.get(
                    "severity",
                    "ERROR",
                )
            ).upper()

            if severity == "ERROR":
                error_count += 1

            elif severity == "WARNING":
                warning_count += 1

    # Base score:
    # percentage of records that passed validation.
    score = (
        valid_records
        / total_records
    ) * 100

    # Warnings reduce the score slightly,
    # but errors are already reflected through invalid records.
    warning_penalty = min(
        warning_count * 2,
        10,
    )

    score = max(
        0.0,
        score - warning_penalty,
    )

    score = round(
        score,
        2,
    )

    if score >= 90:
        grade = "A"
    elif score >= 75:
        grade = "B"
    elif score >= 60:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"

    return {
        "score": score,
        "grade": grade,
        "total_records": total_records,
        "valid_records": valid_records,
        "invalid_records": invalid_records,
        "error_count": error_count,
        "warning_count": warning_count,
    }