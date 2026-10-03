from uuid import UUID
from app.models.mapping_config import MappingConfig
from app.ingestion.mapping_engine import (
    apply_mapping_to_staging_records,
    build_mapping_configuration,
    save_mapping_configuration,
)
from app.ingestion.validator import (
    validate_records,
    update_staging_record_status,
    store_validation_errors,
)

from app.ingestion.schema_detector import (
    detect_schema,
    detect_mapping_conflicts,
    mark_unmapped_columns,
)

from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

import fitz
import pandas as pd

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db.dependencies import get_db

from app.models.data_source import (
    DataSource,
    DataSourceCategory,
    DataSourceStatus,
    DataSourceType,
)

from app.models.ingestion_job import (
    IngestionJob,
    IngestionJobStatus,
)

from app.models.staging_record import (
    StagingRecord,
    StagingRecordStatus,
)


router = APIRouter(
    prefix="/api/ingestion",
    tags=["Universal Ingestion"],
)


ALLOWED_EXTENSIONS = {
    ".csv",
    ".json",
    ".xlsx",
    ".pdf",
}


MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


RAW_STORAGE_DIR = Path("/app/storage/raw")


def read_tabular_file(
    file_path: str,
    extension: str,
) -> pd.DataFrame:
    if extension == ".csv":
        return pd.read_csv(file_path)

    if extension == ".json":
        return pd.read_json(file_path)

    if extension == ".xlsx":
        return pd.read_excel(file_path)

    raise ValueError("Unsupported tabular file format")


def read_pdf(
    file_path: str,
) -> tuple[int, str]:
    document = fitz.open(file_path)

    try:
        page_count = len(document)

        text_parts = []

        for page in document:
            text_parts.append(page.get_text())

        text = "\n".join(text_parts).strip()

        return page_count, text

    finally:
        document.close()


def detect_category(
    filename: str,
) -> DataSourceCategory:
    filename_lower = filename.lower()

    if "inventory" in filename_lower:
        return DataSourceCategory.INVENTORY

    if "consumption" in filename_lower:
        return DataSourceCategory.CONSUMPTION

    if "vehicle" in filename_lower or "vehicles" in filename_lower:
        return DataSourceCategory.VEHICLES

    if "shipment" in filename_lower or "shipments" in filename_lower:
        return DataSourceCategory.SHIPMENTS

    if "location" in filename_lower or "locations" in filename_lower:
        return DataSourceCategory.LOCATIONS

    if "route" in filename_lower or "routes" in filename_lower:
        return DataSourceCategory.ROUTES

    if "weather" in filename_lower:
        return DataSourceCategory.WEATHER

    if "demand" in filename_lower:
        return DataSourceCategory.DEMAND

    if "maintenance" in filename_lower:
        return DataSourceCategory.MAINTENANCE

    return DataSourceCategory.CUSTOM


def json_safe_value(value):
    """Convert pandas/NumPy values into JSON-safe Python values."""
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass

    if isinstance(value, (list, tuple)):
        return [json_safe_value(item) for item in value]

    if isinstance(value, dict):
        return {str(key): json_safe_value(item) for key, item in value.items()}

    return value


def dataframe_to_staging_records(
    dataframe: pd.DataFrame,
    ingestion_job_id,
) -> list[StagingRecord]:
    records = []

    for index, row in dataframe.iterrows():
        raw_data = {}

        for column, value in row.items():
            raw_data[str(column)] = json_safe_value(value)

        record = StagingRecord(
            ingestion_job_id=ingestion_job_id,
            row_number=index + 2,
            raw_data=raw_data,
            status=StagingRecordStatus.PENDING,
        )

        records.append(record)

    return records


def dataframe_preview(dataframe: pd.DataFrame, limit: int = 10) -> list[dict]:
    """Create a JSON-safe preview from a pandas DataFrame."""
    preview = []

    for _, row in dataframe.head(limit).iterrows():
        preview.append({
            str(column): json_safe_value(value)
            for column, value in row.items()
        })

    return preview


@router.post(
    "/upload",
    status_code=status.HTTP_200_OK,
)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    extension = Path(file.filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unsupported file format. "
                "Allowed formats: CSV, JSON, XLSX, PDF"
            ),
        )

    contents = await file.read()

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the 10 MB upload limit",
        )

    if not contents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    RAW_STORAGE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_id = uuid4()
    safe_filename = Path(file.filename).name

    stored_filename = f"{file_id}{extension}"

    stored_file_path = RAW_STORAGE_DIR / stored_filename

    data_source = DataSource(
        name=safe_filename,
        source_type=DataSourceType.FILE,
        data_category=detect_category(safe_filename),
        description="Uploaded through Universal Data Hub",
        status=DataSourceStatus.ACTIVE,
        config={
            "original_filename": safe_filename,
            "stored_filename": stored_filename,
            "file_extension": extension,
            "content_type": file.content_type,
            "storage": "local",
        },
        schema_version="1.0",
    )

    db.add(data_source)
    db.flush()

    ingestion_job = IngestionJob(
        source_id=data_source.id,
        status=IngestionJobStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )

    db.add(ingestion_job)
    db.flush()

    temporary_file = None

    try:
        stored_file_path.write_bytes(contents)

        temporary_file = NamedTemporaryFile(
            delete=False,
            suffix=extension,
        )

        temporary_file.write(contents)
        temporary_file.close()

        if extension == ".pdf":
            page_count, text = read_pdf(
                temporary_file.name
            )

            ingestion_job.records_received = 1
            ingestion_job.records_processed = 1
            ingestion_job.status = IngestionJobStatus.COMPLETED
            ingestion_job.completed_at = datetime.now(
                timezone.utc
            )

            data_source.last_sync_at = datetime.now(
                timezone.utc
            )
            data_source.last_error = None

            db.commit()

            return {
                "message": "PDF uploaded and parsed successfully",
                "source_id": str(data_source.id),
                "ingestion_job_id": str(ingestion_job.id),
                "filename": safe_filename,
                "file_type": "pdf",
                "file_size_bytes": len(contents),
                "page_count": page_count,
                "text_length": len(text),
                "preview": text[:5000],
            }

        dataframe = read_tabular_file(
            temporary_file.name,
            extension,
        )

        columns = [
            str(column)
            for column in dataframe.columns
        ]

        preview = dataframe_preview(dataframe)

        staging_records = dataframe_to_staging_records(
            dataframe,
            ingestion_job.id,
        )

        db.add_all(staging_records)

        ingestion_job.records_received = len(dataframe)
        ingestion_job.records_processed = len(
            staging_records
        )
        ingestion_job.status = IngestionJobStatus.COMPLETED
        ingestion_job.completed_at = datetime.now(
            timezone.utc
        )

        data_source.last_sync_at = datetime.now(
            timezone.utc
        )
        data_source.last_error = None

        db.commit()

        return {
            "message": "File uploaded and staged successfully",
            "source_id": str(data_source.id),
            "ingestion_job_id": str(ingestion_job.id),
            "filename": safe_filename,
            "file_type": extension.lstrip("."),
            "file_size_bytes": len(contents),
            "row_count": len(dataframe),
            "staged_record_count": len(staging_records),
            "column_count": len(columns),
            "columns": columns,
            "preview": preview,
        }

    except Exception as exc:
        db.rollback()

        ingestion_job = db.get(
            IngestionJob,
            ingestion_job.id,
        )

        data_source = db.get(
            DataSource,
            data_source.id,
        )

        if ingestion_job:
            ingestion_job.status = IngestionJobStatus.FAILED
            ingestion_job.completed_at = datetime.now(
                timezone.utc
            )
            ingestion_job.error_message = str(exc)

        if data_source:
            data_source.status = DataSourceStatus.ERROR
            data_source.last_error = str(exc)

        db.commit()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to process uploaded file: {str(exc)}",
        ) from exc

    finally:
        if temporary_file is not None:
            Path(temporary_file.name).unlink(
                missing_ok=True
            )


@router.post("/detect-schema")
def detect_uploaded_schema(
    source_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Detect the schema of the latest ingestion job
    belonging to a data source.
    """

    data_source = (
        db.query(DataSource)
        .filter(DataSource.id == source_id)
        .first()
    )

    if not data_source:
        raise HTTPException(
            status_code=404,
            detail="Data source not found.",
        )

    ingestion_job = (
        db.query(IngestionJob)
        .filter(
            IngestionJob.source_id == source_id
        )
        .order_by(
            IngestionJob.created_at.desc()
        )
        .first()
    )

    if not ingestion_job:
        raise HTTPException(
            status_code=404,
            detail="No ingestion job found for this source.",
        )

    staging_records = (
        db.query(StagingRecord)
        .filter(
            StagingRecord.ingestion_job_id
            == ingestion_job.id
        )
        .order_by(
            StagingRecord.row_number
        )
        .all()
    )

    if not staging_records:
        raise HTTPException(
            status_code=400,
            detail="No staging records available for schema detection.",
        )

    rows = [
        record.raw_data
        for record in staging_records
    ]

    columns = list(
        rows[0].keys()
    )

    detection_results = detect_schema(
        columns,
        rows,
    )

    detection_results = (
        mark_unmapped_columns(
            detection_results
        )
    )

    conflicts = detect_mapping_conflicts(
        detection_results
    )

    return {
        "source_id": str(source_id),
        "ingestion_job_id": str(
            ingestion_job.id
        ),
        "columns": columns,
        "row_count": len(rows),
        "detections": detection_results,
        "conflicts": conflicts,
    }

@router.post("/assistant")
def data_assistant(
    source_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Analyze the latest staged data and return Data Assistant
    mapping suggestions with confidence and decision levels.
    """

    data_source = (
        db.query(DataSource)
        .filter(DataSource.id == source_id)
        .first()
    )

    if not data_source:
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
        .filter(
            StagingRecord.ingestion_job_id == ingestion_job.id
        )
        .order_by(StagingRecord.row_number)
        .all()
    )

    if not staging_records:
        raise HTTPException(
            status_code=400,
            detail="No staging records available for Data Assistant.",
        )

    rows = [
        record.raw_data
        for record in staging_records
    ]

    columns = list(rows[0].keys())

    detection_results = detect_schema(
        columns,
        rows,
    )

    detection_results = mark_unmapped_columns(
        detection_results
    )

    conflicts = detect_mapping_conflicts(
        detection_results
    )

    mapping_configuration = build_mapping_configuration(
        detection_results
    )

    auto_count = sum(
        1
        for result in detection_results
        if result["decision"] == "AUTO"
    )

    suggested_count = sum(
        1
        for result in detection_results
        if result["decision"] == "SUGGEST"
    )

    review_count = sum(
        1
        for result in detection_results
        if result["decision"] == "REVIEW"
    )

    return {
        "assistant": "Data Assistant",
        "source_id": str(source_id),
        "ingestion_job_id": str(ingestion_job.id),
        "columns": columns,
        "row_count": len(rows),
        "summary": {
            "total_columns": len(detection_results),
            "auto_mapped": auto_count,
            "suggestions": suggested_count,
            "needs_review": review_count,
            "conflicts": len(conflicts),
        },
        "suggestions": detection_results,
        "mapping_configuration": mapping_configuration,
        "conflicts": conflicts,
    }


@router.post("/save-mapping")
def save_detected_mapping(
    source_id: UUID,
    name: str = "Auto-detected mapping",
    db: Session = Depends(get_db),
):
    """
    Detect the latest source schema and persist the resulting
    mapping configuration.
    """

    data_source = (
        db.query(DataSource)
        .filter(DataSource.id == source_id)
        .first()
    )

    if not data_source:
        raise HTTPException(
            status_code=404,
            detail="Data source not found.",
        )

    ingestion_job = (
        db.query(IngestionJob)
        .filter(
            IngestionJob.source_id == source_id
        )
        .order_by(
            IngestionJob.created_at.desc()
        )
        .first()
    )

    if not ingestion_job:
        raise HTTPException(
            status_code=404,
            detail="No ingestion job found for this source.",
        )

    staging_records = (
        db.query(StagingRecord)
        .filter(
            StagingRecord.ingestion_job_id
            == ingestion_job.id
        )
        .order_by(
            StagingRecord.row_number
        )
        .all()
    )

    if not staging_records:
        raise HTTPException(
            status_code=400,
            detail="No staging records available for mapping.",
        )

    rows = [
        record.raw_data
        for record in staging_records
    ]

    columns = list(rows[0].keys())

    detection_results = detect_schema(
        columns,
        rows,
    )

    detection_results = mark_unmapped_columns(
        detection_results
    )

    conflicts = detect_mapping_conflicts(
        detection_results
    )

    if conflicts:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Mapping conflicts detected. Resolve them before saving.",
                "conflicts": conflicts,
            },
        )

    from app.ingestion.mapping_engine import (
        build_mapping_configuration,
    )

    mapping_configuration = build_mapping_configuration(
        detection_results
    )

    try:
        mapping_config = save_mapping_configuration(
            db=db,
            source_id=source_id,
            name=name,
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
        "message": "Mapping configuration saved successfully.",
        "mapping_config_id": str(mapping_config.id),
        "source_id": str(source_id),
        "ingestion_job_id": str(ingestion_job.id),
        "name": mapping_config.name,
        "version": mapping_config.version,
        "is_active": mapping_config.is_active,
        "mapping_definition": mapping_config.mapping_definition,
    }

@router.post("/validate")
def validate_ingestion(
    ingestion_job_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Validate all staged records belonging to an ingestion job.
    """

    staging_records = (
        db.query(StagingRecord)
        .filter(
            StagingRecord.ingestion_job_id
            == ingestion_job_id
        )
        .order_by(
            StagingRecord.row_number
        )
        .all()
    )

    if not staging_records:
        raise HTTPException(
            status_code=404,
            detail="No staging records found.",
        )

    mapping_config = (
        db.query(MappingConfig)
        .filter(
            MappingConfig.source_id == (
                db.query(IngestionJob.source_id)
                .filter(IngestionJob.id == ingestion_job_id)
                .scalar_subquery()
            ),
            MappingConfig.is_active.is_(True),
        )
        .order_by(
            MappingConfig.version.desc()
        )
        .first()
    )

    if not mapping_config:
        raise HTTPException(
            status_code=400,
            detail="No active mapping configuration found for this ingestion source.",
        )

    mapping_configuration = mapping_config.mapping_definition

    canonical_records = (
        apply_mapping_to_staging_records(
            staging_records,
            mapping_configuration,
        )
    )

    records = [
        item["data"]
        for item in canonical_records
    ]

    validation_results = validate_records(
        records
    )

    update_staging_record_status(
        staging_records,
        validation_results,
    )

    store_validation_errors(
        db,
        ingestion_job_id,
        validation_results,
    )

    db.commit()

    valid_count = sum(
        1
        for result in validation_results
        if result["valid"]
    )

    invalid_count = (
        len(validation_results)
        - valid_count
    )

    return {
        "ingestion_job_id": str(
            ingestion_job_id
        ),
        "total_records": len(
            validation_results
        ),
        "valid_records": valid_count,
        "quarantined_records": invalid_count,
        "results": validation_results,
    }