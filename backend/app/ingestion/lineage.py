from typing import Any

from sqlalchemy.orm import Session

from app.models.data_lineage import DataLineage
from app.models.staging_record import StagingRecord


def create_ingestion_lineage(
    db: Session,
    ingestion_job_id,
    staging_records: list[StagingRecord],
    mapping_config,
    validation_results: list[dict[str, Any]],
) -> int:
    """
    Create or update lineage records for ingestion validation.

    Lineage is idempotent:
    running validation multiple times updates the existing lineage
    record instead of creating duplicates.
    """

    validation_by_number = {
        result["record_number"]: result
        for result in validation_results
    }

    created_or_updated_count = 0

    for record in staging_records:
        validation = validation_by_number.get(record.row_number)

        if validation is None:
            continue

        existing_lineage = (
            db.query(DataLineage)
            .filter(
                DataLineage.ingestion_job_id == ingestion_job_id,
                DataLineage.target_entity == "STAGING_RECORD",
                DataLineage.target_record_id == str(record.id),
            )
            .first()
        )

        transformation_details = {
            "mapping_config_id": str(mapping_config.id),
            "mapping_version": mapping_config.version,
            "validation_status": (
                "VALID"
                if validation["valid"]
                else "QUARANTINED"
            ),
            "rule_results": validation.get("rule_results", []),
        }

        if existing_lineage:
            existing_lineage.source_record_identifier = (
                f"row-{record.row_number}"
            )
            existing_lineage.transformation_details = (
                transformation_details
            )
            existing_lineage.notes = (
                "Lineage updated during ingestion validation."
            )
        else:
            lineage = DataLineage(
                ingestion_job_id=ingestion_job_id,
                source_record_identifier=f"row-{record.row_number}",
                target_entity="STAGING_RECORD",
                target_record_id=str(record.id),
                transformation_details=transformation_details,
                notes="Lineage created during ingestion validation.",
            )

            db.add(lineage)

        created_or_updated_count += 1

    return created_or_updated_count