from typing import Any
import json
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.validation_error import ValidationError


REQUIRED_FIELDS = {
    "ITEM_CODE",
    "ITEM_NAME",
    "QUANTITY",
    "LOCATION",
}


QUALITY_RULES = {
    "REQUIRED_FIELD": {
        "name": "Required Field",
        "severity": "ERROR",
    },
    "EMPTY_FIELD": {
        "name": "Empty Field",
        "severity": "ERROR",
    },
    "INVALID_QUANTITY": {
        "name": "Invalid Quantity",
        "severity": "ERROR",
    },
    "INVALID_DATE": {
        "name": "Invalid Date",
        "severity": "ERROR",
    },
    "INVALID_TYPE": {
        "name": "Invalid Type",
        "severity": "ERROR",
    },
    "VALIDATION_ERROR": {
        "name": "Validation Error",
        "severity": "ERROR",
    },
}


def validate_required_fields(
    record: dict[str, Any],
) -> list[str]:
    errors = []

    for field in REQUIRED_FIELDS:
        value = record.get(field)

        if value is None:
            errors.append(f"{field} is required.")

        elif isinstance(value, str) and not value.strip():
            errors.append(f"{field} cannot be empty.")

    return errors


def validate_quantity(
    record: dict[str, Any],
) -> list[str]:
    errors = []

    quantity = record.get("QUANTITY")

    if quantity is None:
        return errors

    if isinstance(quantity, bool):
        errors.append("QUANTITY must be numeric.")
        return errors

    if not isinstance(quantity, (int, float)):
        errors.append("QUANTITY must be numeric.")
        return errors

    if quantity < 0:
        errors.append("QUANTITY cannot be negative.")

    return errors


def validate_dates(
    record: dict[str, Any],
) -> list[str]:
    errors = []

    date_fields = [
        "DATE",
        "CONSUMPTION_DATE",
        "SHIPMENT_DATE",
    ]

    for field in date_fields:
        value = record.get(field)

        if value is None:
            continue

        if isinstance(value, datetime):
            continue

        if isinstance(value, str):
            try:
                datetime.fromisoformat(
                    value.replace("Z", "+00:00")
                )
            except ValueError:
                errors.append(
                    f"{field} must contain a valid date."
                )

    return errors


def get_rule_for_error(
    error_message: str,
) -> dict[str, Any]:

    if "is required" in error_message:
        return {
            "rule_code": "REQUIRED_FIELD",
            "severity": "ERROR",
        }

    if "cannot be empty" in error_message:
        return {
            "rule_code": "EMPTY_FIELD",
            "severity": "ERROR",
        }

    if "QUANTITY" in error_message:
        return {
            "rule_code": "INVALID_QUANTITY",
            "severity": "ERROR",
        }

    if "must contain a valid date" in error_message:
        return {
            "rule_code": "INVALID_DATE",
            "severity": "ERROR",
        }

    return {
        "rule_code": "VALIDATION_ERROR",
        "severity": "ERROR",
    }


def validate_record(
    record: dict[str, Any],
) -> dict[str, Any]:

    errors = []

    errors.extend(
        validate_required_fields(record)
    )

    errors.extend(
        validate_quantity(record)
    )

    errors.extend(
        validate_dates(record)
    )

    structured_errors = []

    for error_message in errors:
        rule = get_rule_for_error(
            error_message
        )

        structured_errors.append(
            {
                "message": error_message,
                "rule_code": rule["rule_code"],
                "severity": rule["severity"],
            }
        )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "rule_results": structured_errors,
    }


def validate_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    results = []

    for index, record in enumerate(
        records,
        start=1,
    ):
        validation = validate_record(record)

        results.append(
            {
                "record_number": index,
                "record": record,
                "valid": validation["valid"],
                "errors": validation["errors"],
                "rule_results": validation[
                    "rule_results"
                ],
            }
        )

    return results


def separate_valid_and_invalid(
    validation_results: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:

    valid_records = []
    quarantined_records = []

    for result in validation_results:

        if result["valid"]:
            valid_records.append(result)

        else:
            quarantined_records.append(
                {
                    "record_number": result[
                        "record_number"
                    ],
                    "record": result["record"],
                    "errors": result["errors"],
                    "rule_results": result[
                        "rule_results"
                    ],
                    "status": "QUARANTINED",
                }
            )

    return {
        "valid": valid_records,
        "quarantined": quarantined_records,
    }


def store_validation_errors(
    db: Session,
    ingestion_job_id: uuid.UUID,
    validation_results: list[dict[str, Any]],
) -> list[ValidationError]:

    errors = []

    for result in validation_results:

        if result["valid"]:
            continue

        row_number = result.get(
            "record_number"
        )

        record = result.get(
            "record",
            {},
        )

        for error_message in result["errors"]:

            rule = get_rule_for_error(
                error_message
            )

            error_code = rule["rule_code"]
            field_name = None

            for field in (
                "ITEM_CODE",
                "ITEM_NAME",
                "QUANTITY",
                "LOCATION",
                "DATE",
                "CONSUMPTION_DATE",
                "SHIPMENT_DATE",
            ):
                if field in error_message:
                    field_name = field
                    break

            if (
                field_name is None
                and error_code == "REQUIRED_FIELD"
            ):
                for field in REQUIRED_FIELDS:
                    if record.get(field) is None:
                        field_name = field
                        break

            raw_value = None

            if field_name:
                value = record.get(field_name)

                if value is not None:
                    raw_value = json.dumps(
                        value,
                        default=str,
                    )

            validation_error = ValidationError(
                ingestion_job_id=ingestion_job_id,
                row_number=row_number,
                field_name=field_name,
                raw_value=raw_value,
                error_code=error_code,
                error_message=error_message,
                status="OPEN",
            )

            db.add(validation_error)
            errors.append(validation_error)

    db.flush()

    return errors


def update_staging_record_status(
    staging_records: list[Any],
    validation_results: list[dict[str, Any]],
) -> None:

    for staging_record, result in zip(
        staging_records,
        validation_results,
    ):

        if result["valid"]:
            staging_record.status = "PROCESSED"
            staging_record.error_message = None

        else:
            staging_record.status = "QUARANTINED"
            staging_record.error_message = (
                "; ".join(result["errors"])
            )