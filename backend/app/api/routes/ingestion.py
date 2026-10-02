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


def dataframe_to_staging_records(
    dataframe: pd.DataFrame,
    ingestion_job_id,
) -> list[StagingRecord]:
    records = []

    for index, row in dataframe.iterrows():
        raw_data = {}

        for column, value in row.items():
            if pd.isna(value):
                raw_data[str(column)] = None
            else:
                raw_data[str(column)] = value

        record = StagingRecord(
            ingestion_job_id=ingestion_job_id,
            row_number=index + 2,
            raw_data=raw_data,
            status=StagingRecordStatus.PENDING,
        )

        records.append(record)

    return records


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

        preview = (
            dataframe
            .head(10)
            .where(pd.notna(dataframe), None)
            .to_dict(orient="records")
        )

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