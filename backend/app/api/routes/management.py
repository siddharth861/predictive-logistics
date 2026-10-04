from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.models.data_source import (
    DataSource,
    DataSourceCategory,
    DataSourceStatus,
    DataSourceType,
)
from app.models.ingestion_job import IngestionJob
from app.models.mapping_config import MappingConfig


router = APIRouter(
    prefix="/api/management",
    tags=["Source & Mapping Management"],
)


class SourceRegistrationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    source_type: DataSourceType
    data_category: DataSourceCategory = DataSourceCategory.CUSTOM
    description: str | None = None
    config: dict[str, Any] | None = None


@router.post("/sources", status_code=201)
def register_source(
    request: SourceRegistrationRequest,
    db: Session = Depends(get_db),
):
    config = dict(request.config or {})

    # Never persist credentials or secret material through the source-registration UI.
    for secret_key in (
        "password",
        "secret",
        "secret_key",
        "api_key",
        "access_token",
        "refresh_token",
    ):
        config.pop(secret_key, None)

    source = DataSource(
        name=request.name.strip(),
        source_type=request.source_type,
        data_category=request.data_category,
        description=request.description,
        config=config,
        schema_version="1.0",
        status=DataSourceStatus.ACTIVE,
    )

    db.add(source)
    db.commit()
    db.refresh(source)

    return {
        "message": "Data source registered successfully",
        "id": str(source.id),
        "name": source.name,
        "source_type": source.source_type.value,
        "data_category": source.data_category.value,
        "status": source.status.value,
        "config": source.config or {},
    }


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)):
    sources = (
        db.query(DataSource)
        .order_by(DataSource.created_at.desc())
        .all()
    )

    return {
        "count": len(sources),
        "sources": [
            {
                "id": str(source.id),
                "name": source.name,
                "source_type": source.source_type.value,
                "data_category": source.data_category.value,
                "status": source.status.value,
                "schema_version": source.schema_version,
                "last_sync_at": (
                    source.last_sync_at.isoformat()
                    if source.last_sync_at
                    else None
                ),
                "last_error": source.last_error,
                "created_at": source.created_at.isoformat(),
            }
            for source in sources
        ],
    }


@router.get("/sources/{source_id}")
def get_source(
    source_id: str,
    db: Session = Depends(get_db),
):
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

    safe_config = dict(source.config or {})
    for secret_key in (
        "password",
        "secret",
        "secret_key",
        "api_key",
        "access_token",
        "refresh_token",
    ):
        safe_config.pop(secret_key, None)

    return {
        "id": str(source.id),
        "name": source.name,
        "source_type": source.source_type.value,
        "data_category": source.data_category.value,
        "description": source.description,
        "config": safe_config,
        "schema_version": source.schema_version,
        "status": source.status.value,
        "last_sync_at": (
            source.last_sync_at.isoformat()
            if source.last_sync_at
            else None
        ),
        "last_error": source.last_error,
        "created_at": source.created_at.isoformat(),
    }


@router.get("/sources/{source_id}/ingestion-history")
def ingestion_history(
    source_id: str,
    db: Session = Depends(get_db),
):
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

    jobs = (
        db.query(IngestionJob)
        .filter(IngestionJob.source_id == source_id)
        .order_by(IngestionJob.created_at.desc())
        .all()
    )

    return {
        "source_id": str(source.id),
        "count": len(jobs),
        "jobs": [
            {
                "id": str(job.id),
                "status": job.status.value,
                "started_at": (
                    job.started_at.isoformat()
                    if job.started_at
                    else None
                ),
                "completed_at": (
                    job.completed_at.isoformat()
                    if job.completed_at
                    else None
                ),
                "created_at": job.created_at.isoformat(),
            }
            for job in jobs
        ],
    }


@router.get("/sources/{source_id}/mappings")
def list_mappings(
    source_id: str,
    db: Session = Depends(get_db),
):
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

    mappings = (
        db.query(MappingConfig)
        .filter(MappingConfig.source_id == source_id)
        .order_by(MappingConfig.version.desc())
        .all()
    )

    return {
        "source_id": str(source.id),
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
