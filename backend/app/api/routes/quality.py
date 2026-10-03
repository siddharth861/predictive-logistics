from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.ingestion.mapping_engine import apply_mapping_to_staging_records
from app.ingestion.validator import validate_record
from app.models.ingestion_job import IngestionJob
from app.models.mapping_config import MappingConfig
from app.models.staging_record import StagingRecord, StagingRecordStatus
from app.models.validation_error import ValidationError, ValidationErrorStatus
from app.models.data_source import DataSource


router = APIRouter(
    prefix="/api/quality",
    tags=["Data Quality"],
)


@router.get("/quarantine/{ingestion_job_id}")
def list_quarantined_records(
    ingestion_job_id: UUID,
    db: Session = Depends(get_db),
):
    records = (
        db.query(StagingRecord)
        .filter(
            StagingRecord.ingestion_job_id == ingestion_job_id,
            StagingRecord.status == StagingRecordStatus.QUARANTINED,
        )
        .order_by(StagingRecord.row_number)
        .all()
    )

    return {
        "ingestion_job_id": str(ingestion_job_id),
        "count": len(records),
        "records": [
            {
                "id": str(record.id),
                "row_number": record.row_number,
                "raw_data": record.raw_data,
                "status": record.status.value,
                "error_message": record.error_message,
            }
            for record in records
        ],
    }


@router.post("/reprocess/{record_id}")
def reprocess_record(
    record_id: UUID,
    db: Session = Depends(get_db),
):
    staging_record = (
        db.query(StagingRecord)
        .filter(StagingRecord.id == record_id)
        .first()
    )

    if not staging_record:
        raise HTTPException(
            status_code=404,
            detail="Staging record not found",
        )

    if staging_record.status != StagingRecordStatus.QUARANTINED:
        raise HTTPException(
            status_code=400,
            detail="Only quarantined records can be reprocessed",
        )

    ingestion_job = (
        db.query(IngestionJob)
        .filter(IngestionJob.id == staging_record.ingestion_job_id)
        .first()
    )

    if not ingestion_job:
        raise HTTPException(
            status_code=404,
            detail="Ingestion job not found",
        )

    mapping_config = (
        db.query(MappingConfig)
        .filter(
            MappingConfig.source_id == ingestion_job.source_id,
            MappingConfig.is_active.is_(True),
        )
        .order_by(MappingConfig.version.desc())
        .first()
    )

    if not mapping_config:
        raise HTTPException(
            status_code=400,
            detail="No active mapping configuration found",
        )

    canonical_records = apply_mapping_to_staging_records(
        [staging_record],
        mapping_config.mapping_definition,
    )

    if not canonical_records:
        raise HTTPException(
            status_code=400,
            detail="Unable to apply mapping to staging record",
        )

    canonical_record = canonical_records[0]["data"]

    validation = validate_record(canonical_record)

    if validation["valid"]:
        staging_record.status = StagingRecordStatus.PROCESSED
        staging_record.error_message = None

        db.query(ValidationError).filter(
            ValidationError.ingestion_job_id
            == staging_record.ingestion_job_id,
            ValidationError.row_number == staging_record.row_number,
            ValidationError.status == ValidationErrorStatus.OPEN,
        ).update(
            {"status": ValidationErrorStatus.RESOLVED},
            synchronize_session=False,
        )

        db.commit()

        return {
            "record_id": str(record_id),
            "record_number": staging_record.row_number,
            "reprocessed": True,
            "status": "PROCESSED",
            "valid": True,
            "canonical_record": canonical_record,
            "errors": [],
            "rule_results": [],
        }

    staging_record.status = StagingRecordStatus.QUARANTINED
    staging_record.error_message = "; ".join(
        validation["errors"]
    )

    db.commit()

    return {
        "record_id": str(record_id),
        "record_number": staging_record.row_number,
        "reprocessed": True,
        "status": "QUARANTINED",
        "valid": False,
        "canonical_record": canonical_record,
        "errors": validation["errors"],
        "rule_results": validation["rule_results"],
    }


@router.get("/summary/{ingestion_job_id}")
def quality_summary(
    ingestion_job_id: UUID,
    db: Session = Depends(get_db),
):
    ingestion_job = (
        db.query(IngestionJob)
        .filter(IngestionJob.id == ingestion_job_id)
        .first()
    )

    if not ingestion_job:
        raise HTTPException(
            status_code=404,
            detail="Ingestion job not found",
        )

    source = (
        db.query(DataSource)
        .filter(DataSource.id == ingestion_job.source_id)
        .first()
    )

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Data source not found",
        )

    staging_records = (
        db.query(StagingRecord)
        .filter(
            StagingRecord.ingestion_job_id == ingestion_job_id
        )
        .all()
    )

    validation_errors = (
        db.query(ValidationError)
        .filter(
            ValidationError.ingestion_job_id == ingestion_job_id
        )
        .all()
    )

    total_records = len(staging_records)

    processed_records = sum(
        1
        for record in staging_records
        if record.status == StagingRecordStatus.PROCESSED
    )

    quarantined_records = sum(
        1
        for record in staging_records
        if record.status == StagingRecordStatus.QUARANTINED
    )

    pending_records = sum(
        1
        for record in staging_records
        if record.status == StagingRecordStatus.PENDING
    )

    open_errors = sum(
        1
        for error in validation_errors
        if error.status == ValidationErrorStatus.OPEN
    )

    resolved_errors = sum(
        1
        for error in validation_errors
        if error.status == ValidationErrorStatus.RESOLVED
    )

    quality_score = (
        (processed_records / total_records) * 100
        if total_records
        else 100.0
    )

    if quality_score >= 90:
        grade = "A"
    elif quality_score >= 75:
        grade = "B"
    elif quality_score >= 60:
        grade = "C"
    elif quality_score >= 40:
        grade = "D"
    else:
        grade = "F"

    return {
        "ingestion_job_id": str(ingestion_job.id),
        "source": {
            "id": str(source.id),
            "name": source.name,
            "type": source.source_type.value,
            "category": (
                source.data_category.value
                if source.data_category
                else None
            ),
            "status": source.status.value,
            "last_sync_at": (
                source.last_sync_at.isoformat()
                if source.last_sync_at
                else None
            ),
        },
        "quality": {
            "score": round(quality_score, 2),
            "grade": grade,
            "total_records": total_records,
            "processed_records": processed_records,
            "quarantined_records": quarantined_records,
            "pending_records": pending_records,
        },
        "validation_errors": {
            "total": len(validation_errors),
            "open": open_errors,
            "resolved": resolved_errors,
        },
    }