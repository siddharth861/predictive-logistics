from datetime import datetime
import hashlib
import math
from typing import Any

from sqlalchemy.orm import Session

from app.models.staging_record import StagingRecord, StagingRecordStatus
from app.models.validation_error import (
    ValidationError,
    ValidationErrorStatus,
)


REQUIRED_FIELDS = {
    "ITEM_CODE",
    "ITEM_NAME",
    "QUANTITY",
    "LOCATION",
}


QUALITY_RULES = {
    "REQUIRED_FIELD": {
        "description": "Required field is missing.",
        "severity": "ERROR",
    },
    "EMPTY_FIELD": {
        "description": "Field is empty.",
        "severity": "ERROR",
    },
    "INVALID_QUANTITY": {
        "description": "Quantity must be a non-negative number.",
        "severity": "ERROR",
    },
    "INVALID_DATE": {
        "description": "Date must be a valid ISO date.",
        "severity": "ERROR",
    },
    "DUPLICATE_RECORD": {
        "description": "Duplicate record detected.",
        "severity": "WARNING",
    },
    "VALIDATION_ERROR": {
        "description": "Validation error.",
        "severity": "ERROR",
    },
}


def validate_required_fields(record: dict[str, Any]) -> list[str]:
    errors = []

    for field in REQUIRED_FIELDS:
        value = record.get(field)

        if value is None:
            errors.append(f"{field} is required.")
        elif isinstance(value, str) and not value.strip():
            errors.append(f"{field} cannot be empty.")

    return errors


def validate_quantity(record: dict[str, Any]) -> list[str]:
    errors = []

    quantity = record.get("QUANTITY")

    if quantity is None:
        return errors

    try:
        numeric_quantity = float(quantity)

        if math.isnan(numeric_quantity) or math.isinf(numeric_quantity):
            errors.append("QUANTITY must be a valid number.")
        elif numeric_quantity < 0:
            errors.append("QUANTITY cannot be negative.")

    except (TypeError, ValueError):
        errors.append("QUANTITY must be a valid number.")

    return errors


def validate_dates(record: dict[str, Any]) -> list[str]:
    errors = []

    date_fields = [
        "DATE",
        "CONSUMPTION_DATE",
        "SHIPMENT_DATE",
    ]

    for field in date_fields:
        value = record.get(field)

        if value is None or value == "":
            continue

        try:
            datetime.fromisoformat(str(value))
        except ValueError:
            errors.append(
                f"{field} must be a valid ISO date."
            )

    return errors


def build_record_fingerprint(record: dict[str, Any]) -> str:
    item_code = str(record.get("ITEM_CODE", "")).strip().lower()
    item_name = str(record.get("ITEM_NAME", "")).strip().lower()
    location = str(record.get("LOCATION", "")).strip().lower()

    fingerprint_source = (
        f"{item_code}|{item_name}|{location}"
    )

    return hashlib.sha256(
        fingerprint_source.encode("utf-8")
    ).hexdigest()


def detect_duplicates(
    records: list[dict[str, Any]],
) -> dict[int, str]:
    fingerprints: dict[str, int] = {}
    duplicates: dict[int, str] = {}

    for index, record in enumerate(records, start=1):
        fingerprint = build_record_fingerprint(record)

        if fingerprint in fingerprints:
            duplicates[index] = fingerprint
        else:
            fingerprints[fingerprint] = index

    return duplicates


def get_rule_for_error(error_message: str) -> dict[str, str]:
    message = error_message.lower()

    if "cannot be negative" in message:
        rule_code = "INVALID_QUANTITY"

    elif "quantity must be a valid number" in message:
        rule_code = "INVALID_QUANTITY"

    elif "is required" in message:
        rule_code = "REQUIRED_FIELD"

    elif "cannot be empty" in message:
        rule_code = "EMPTY_FIELD"

    elif "must be a valid iso date" in message:
        rule_code = "INVALID_DATE"

    elif "duplicate record" in message:
        rule_code = "DUPLICATE_RECORD"

    else:
        rule_code = "VALIDATION_ERROR"

    return {
        "rule_code": rule_code,
        "severity": QUALITY_RULES[rule_code]["severity"],
    }


def validate_record(record: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []

    errors.extend(
        validate_required_fields(record)
    )

    errors.extend(
        validate_quantity(record)
    )

    errors.extend(
        validate_dates(record)
    )

    rule_results = []

    for error in errors:
        rule = get_rule_for_error(error)

        rule_results.append(
            {
                "message": error,
                "rule_code": rule["rule_code"],
                "severity": rule["severity"],
            }
        )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "rule_results": rule_results,
    }


def validate_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    duplicate_map = detect_duplicates(records)

    results = []

    for record_number, record in enumerate(
        records,
        start=1,
    ):
        validation = validate_record(record)

        if record_number in duplicate_map:
            duplicate_message = "Duplicate record detected."

            validation["errors"].append(
                duplicate_message
            )

            validation["rule_results"].append(
                {
                    "message": duplicate_message,
                    "rule_code": "DUPLICATE_RECORD",
                    "severity": "WARNING",
                }
            )

            validation["valid"] = False

        results.append(
            {
                "record_number": record_number,
                "valid": validation["valid"],
                "errors": validation["errors"],
                "rule_results": validation["rule_results"],
            }
        )

    return results


def separate_valid_and_invalid(
    records: list[dict[str, Any]],
    validation_results: list[dict[str, Any]],
):
    valid_records = []
    invalid_records = []

    for record, result in zip(
        records,
        validation_results,
    ):
        if result["valid"]:
            valid_records.append(record)
        else:
            invalid_records.append(record)

    return valid_records, invalid_records


def store_validation_errors(
    db: Session,
    ingestion_job_id,
    validation_results: list[dict[str, Any]],
):
    for result in validation_results:
        row_number = result["record_number"]

        existing_errors = (
            db.query(ValidationError)
            .filter(
                ValidationError.ingestion_job_id
                == ingestion_job_id,
                ValidationError.row_number
                == row_number,
            )
            .all()
        )

        existing_by_code = {
            error.error_code: error
            for error in existing_errors
        }

        current_rule_codes = set()

        for rule in result.get(
            "rule_results",
            [],
        ):
            rule_code = rule["rule_code"]
            current_rule_codes.add(rule_code)

            error = existing_by_code.get(
                rule_code
            )

            message = rule["message"]

            if error:
                error.raw_value = None
                error.error_message = message
                error.status = ValidationErrorStatus.OPEN
            else:
                error = ValidationError(
                    ingestion_job_id=ingestion_job_id,
                    row_number=row_number,
                    field_name=None,
                    raw_value=None,
                    error_code=rule_code,
                    error_message=message,
                    status=ValidationErrorStatus.OPEN,
                )

                db.add(error)

        for error in existing_errors:
            if (
                error.error_code
                not in current_rule_codes
            ):
                error.status = (
                    ValidationErrorStatus.RESOLVED
                )


def update_staging_record_status(
    db: Session,
    staging_record: StagingRecord,
    valid: bool,
):
    if valid:
        staging_record.status = (
            StagingRecordStatus.PROCESSED
        )
        staging_record.error_message = None

    else:
        staging_record.status = (
            StagingRecordStatus.QUARANTINED
        )