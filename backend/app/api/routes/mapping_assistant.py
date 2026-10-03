from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.ingestion.mapping_engine import (
    apply_mapping_override,
    build_mapping_configuration,
    save_mapping_configuration,
    validate_mapping_configuration,
)
from app.ingestion.schema_detector import (
    detect_mapping_conflicts,
    detect_schema,
    mark_unmapped_columns,
)
from app.models.data_source import DataSource
from app.models.ingestion_job import IngestionJob
from app.models.mapping_config import MappingConfig
from app.models.staging_record import StagingRecord


router = APIRouter(
    prefix="/api/ingestion",
    tags=["Data Assistant"],
)


class MappingConfirmationRequest(BaseModel):
    source_id: UUID
    overrides: dict[str, str | None] = Field(default_factory=dict)
    name: str = "Data Assistant confirmed mapping"


def _get_latest_staging_data(source_id: UUID, db: Session):
    source = (
        db.query(DataSource)
        .filter(DataSource.id == source_id)
        .first()
    )

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Data source not found.",
        )

    ingestion_job = (
        db.query(IngestionJob)
        .filter(IngestionJob.source_id == source_id)
        .order_by(IngestionJob.created_at.desc())
        .first()
    )

    if not ingestion_job:
        raise HTTPException(
            status_code=404,
            detail="No ingestion job found for this source.",
        )

    staging_records = (
        db.query(StagingRecord)
        .filter(StagingRecord.ingestion_job_id == ingestion_job.id)
        .order_by(StagingRecord.row_number)
        .all()
    )

    if not staging_records:
        raise HTTPException(
            status_code=400,
            detail="No staging records available for mapping.",
        )

    rows = [record.raw_data for record in staging_records]
    columns = list(rows[0].keys())

    return source, ingestion_job, staging_records, rows, columns


@router.post("/confirm-mapping")
def confirm_mapping(
    request: MappingConfirmationRequest,
    db: Session = Depends(get_db),
):
    """
    Apply user overrides to the Data Assistant's detected mapping
    and save the confirmed mapping as a new active version.
    """

    source, ingestion_job, staging_records, rows, columns = (
        _get_latest_staging_data(request.source_id, db)
    )

    detection_results = detect_schema(columns, rows)
    detection_results = mark_unmapped_columns(detection_results)

    conflicts = detect_mapping_conflicts(detection_results)

    if conflicts and not request.overrides:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Mapping conflicts detected. Provide overrides before confirming.",
                "conflicts": conflicts,
            },
        )

    mapping_configuration = build_mapping_configuration(
        detection_results
    )

    mapping_configuration = apply_mapping_override(
        mapping_configuration,
        request.overrides,
    )

    validation = validate_mapping_configuration(
        mapping_configuration
    )

    if not validation["valid"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Confirmed mapping is invalid.",
                "errors": validation["errors"],
                "warnings": validation["warnings"],
            },
        )

    try:
        mapping_config = save_mapping_configuration(
            db=db,
            source_id=request.source_id,
            name=request.name,
            mapping_configuration=mapping_configuration,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return {
        "message": "Mapping confirmed and saved successfully.",
        "source_id": str(request.source_id),
        "ingestion_job_id": str(ingestion_job.id),
        "mapping_config_id": str(mapping_config.id),
        "version": mapping_config.version,
        "is_active": mapping_config.is_active,
        "mapping_definition": mapping_config.mapping_definition,
        "validation": validation,
    }


@router.get("/mapping-versions")
def mapping_versions(
    source_id: UUID,
    db: Session = Depends(get_db),
):
    """Return saved mapping versions for a source."""
    mappings = (
        db.query(MappingConfig)
        .filter(MappingConfig.source_id == source_id)
        .order_by(MappingConfig.version.desc())
        .all()
    )

    if not mappings:
        raise HTTPException(
            status_code=404,
            detail="No mapping configurations found for this source.",
        )

    return {
        "source_id": str(source_id),
        "count": len(mappings),
        "mappings": [
            {
                "id": str(mapping.id),
                "name": mapping.name,
                "version": mapping.version,
                "is_active": mapping.is_active,
                "mapping_definition": mapping.mapping_definition,
                "created_at": mapping.created_at.isoformat(),
            }
            for mapping in mappings
        ],
    }
