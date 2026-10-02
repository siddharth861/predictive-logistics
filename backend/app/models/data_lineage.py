import uuid

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DataLineage(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "data_lineage"

    ingestion_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_jobs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    source_record_identifier: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    target_entity: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    target_record_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    transformation_details: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )