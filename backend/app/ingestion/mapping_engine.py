from typing import Any


def build_mapping_configuration(
    detection_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Convert schema detection results into a
    structured mapping configuration.

    This does not transform database records yet.
    It only defines how source columns should map
    to canonical fields.
    """

    mappings = []

    for result in detection_results:
        mappings.append(
            {
                "source_column": result["column"],
                "canonical_field": (
                    result["suggested_field"]
                    if result["decision"] != "REVIEW"
                    else None
                ),
                "confidence": result["confidence"],
                "decision": result["decision"],
                "status": result["status"]
                if "status" in result
                else (
                    "MAPPED"
                    if result["decision"] != "REVIEW"
                    else "UNMAPPED"
                ),
            }
        )

    return {
        "version": "1.0",
        "mappings": mappings,
    }
def apply_mapping(
    row: dict[str, Any],
    mapping_configuration: dict[str, Any],
) -> dict[str, Any]:
    """
    Transform one source row into canonical fields.

    Unmapped source columns are preserved separately
    under the '_unmapped' key.
    """

    canonical_row: dict[str, Any] = {}
    unmapped: dict[str, Any] = {}

    mappings = mapping_configuration.get(
        "mappings",
        [],
    )

    for mapping in mappings:
        source_column = mapping["source_column"]
        canonical_field = mapping["canonical_field"]

        value = row.get(source_column)

        if canonical_field:
            canonical_row[canonical_field] = value
        else:
            unmapped[source_column] = value

    if unmapped:
        canonical_row["_unmapped"] = unmapped

    return canonical_row
def apply_mapping_override(
    mapping_configuration: dict[str, Any],
    overrides: dict[str, str | None],
) -> dict[str, Any]:
    """
    Apply user-approved mapping decisions.

    overrides example:
    {
        "mat_code": "ITEM_CODE",
        "mat_desc": "ITEM_NAME",
        "mystery_xyz": None
    }
    """

    mappings = mapping_configuration.get(
        "mappings",
        [],
    )

    for mapping in mappings:
        source_column = mapping["source_column"]

        if source_column not in overrides:
            continue

        canonical_field = overrides[
            source_column
        ]

        mapping["canonical_field"] = (
            canonical_field
        )

        if canonical_field:
            mapping["status"] = "MAPPED"
            mapping["decision"] = "MANUAL"
        else:
            mapping["status"] = "UNMAPPED"
            mapping["decision"] = "MANUAL"

    return mapping_configuration
def validate_mapping_configuration(
    mapping_configuration: dict[str, Any],
) -> dict[str, Any]:
    """
    Validate a mapping configuration before it is saved
    or applied to canonical data.
    """

    mappings = mapping_configuration.get(
        "mappings",
        [],
    )

    errors = []
    warnings = []

    seen_fields: dict[str, list[str]] = {}

    valid_fields = set()

    from app.ingestion.aliases import CANONICAL_FIELDS

    valid_fields.update(
        CANONICAL_FIELDS.keys()
    )

    for mapping in mappings:
        source_column = mapping.get(
            "source_column"
        )

        canonical_field = mapping.get(
            "canonical_field"
        )

        if not source_column:
            errors.append(
                "A mapping is missing source_column."
            )
            continue

        if canonical_field is None:
            continue

        if canonical_field not in valid_fields:
            errors.append(
                f"Invalid canonical field "
                f"'{canonical_field}' for "
                f"source column '{source_column}'."
            )
            continue

        seen_fields.setdefault(
            canonical_field,
            [],
        ).append(source_column)

    # Detect duplicate canonical mappings.
    for field, source_columns in seen_fields.items():

        if len(source_columns) > 1:
            errors.append(
                f"Multiple source columns map to "
                f"{field}: {source_columns}"
            )

    # Warn about completely unmapped columns.
    unmapped_columns = [
        mapping["source_column"]
        for mapping in mappings
        if mapping.get("canonical_field") is None
    ]

    if unmapped_columns:
        warnings.append(
            f"Unmapped source columns: "
            f"{unmapped_columns}"
        )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.mapping_config import MappingConfig


def save_mapping_configuration(
    db: Session,
    source_id: UUID,
    name: str,
    mapping_configuration: dict[str, Any],
) -> MappingConfig:
    """
    Save a validated mapping configuration.

    Existing active mappings for the same source are
    deactivated before creating the new version.
    """

    validation = validate_mapping_configuration(
        mapping_configuration
    )

    if not validation["valid"]:
        raise ValueError(
            "Invalid mapping configuration: "
            + "; ".join(validation["errors"])
        )

    latest_version = (
        db.query(MappingConfig)
        .filter(
            MappingConfig.source_id == source_id
        )
        .order_by(
            MappingConfig.version.desc()
        )
        .first()
    )

    next_version = (
        latest_version.version + 1
        if latest_version
        else 1
    )

    (
        db.query(MappingConfig)
        .filter(
            MappingConfig.source_id == source_id,
            MappingConfig.is_active.is_(True),
        )
        .update(
            {
                MappingConfig.is_active: False
            }
        )
    )

    mapping_config = MappingConfig(
        source_id=source_id,
        name=name,
        version=next_version,
        mapping_definition=mapping_configuration,
        is_active=True,
    )

    db.add(mapping_config)
    db.flush()

    return mapping_config
def apply_mapping_to_staging_records(
    staging_records: list[Any],
    mapping_configuration: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Apply an approved mapping configuration to staging records.

    Raw staging records are not modified.
    The function returns transformed canonical records.
    """

    canonical_records = []

    for staging_record in staging_records:
        canonical_row = apply_mapping(
            staging_record.raw_data,
            mapping_configuration,
        )

        canonical_records.append(
            {
                "staging_record_id": str(
                    staging_record.id
                ),
                "row_number": (
                    staging_record.row_number
                ),
                "data": canonical_row,
            }
        )

    return canonical_records