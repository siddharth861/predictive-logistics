from typing import Any


REQUIRED_FIELDS = {
    "ITEM_CODE",
    "ITEM_NAME",
    "QUANTITY",
    "LOCATION",
}


def validate_required_fields(
    record: dict[str, Any],
) -> list[str]:
    errors = []

    for field in REQUIRED_FIELDS:
        value = record.get(field)

        if value is None:
            errors.append(
                f"{field} is required."
            )

        elif isinstance(value, str) and not value.strip():
            errors.append(
                f"{field} cannot be empty."
            )

    return errors


def validate_quantity(
    record: dict[str, Any],
) -> list[str]:
    errors = []

    quantity = record.get("QUANTITY")

    if quantity is None:
        return errors

    if not isinstance(quantity, (int, float)):
        errors.append(
            "QUANTITY must be numeric."
        )
        return errors

    if quantity < 0:
        errors.append(
            "QUANTITY cannot be negative."
        )

    return errors


def validate_record(
    record: dict[str, Any],
) -> dict[str, Any]:
    """
    Validate one canonical record.
    """

    errors = []

    errors.extend(
        validate_required_fields(record)
    )

    errors.extend(
        validate_quantity(record)
    )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }
def validate_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Validate multiple canonical records.
    """

    results = []

    for index, record in enumerate(records, start=1):
        validation = validate_record(record)

        results.append(
            {
                "record_number": index,
                "record": record,
                "valid": validation["valid"],
                "errors": validation["errors"],
            }
        )

    return results
def separate_valid_and_invalid(
    validation_results: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    Separate validated records into valid records
    and quarantined records.
    """

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
                    "status": "QUARANTINED",
                }
            )

    return {
        "valid": valid_records,
        "quarantined": quarantined_records,
    }
import json
import uuid

from sqlalchemy.orm import Session

from app.models.validation_error import ValidationError


def store_validation_errors(
    db: Session,
    ingestion_job_id: uuid.UUID,
    validation_results: list[dict[str, Any]],
) -> list[ValidationError]:
    """
    Persist validation errors for invalid records.
    """

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

            if "QUANTITY" in error_message:
                error_code = "INVALID_QUANTITY"
                field_name = "QUANTITY"

            elif "required" in error_message.lower():
                error_code = "REQUIRED_FIELD"
                field_name = None

                for field in (
                    "ITEM_CODE",
                    "ITEM_NAME",
                    "QUANTITY",
                    "LOCATION",
                ):
                    if field not in record:
                        field_name = field
                        break

            else:
                error_code = "VALIDATION_ERROR"
                field_name = None

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
    """
    Update staging record status based on validation results.
    """

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