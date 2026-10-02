import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, JSON, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StagingRecordStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"


class StagingRecord(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "staging_records"

    ingestion_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "ingestion_jobs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    row_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    raw_data: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )

    status: Mapped[StagingRecordStatus] = mapped_column(
        Enum(
            StagingRecordStatus,
            name="staging_record_status",
        ),
        nullable=False,
        default=StagingRecordStatus.PENDING,
        index=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    ingestion_job: Mapped["IngestionJob"] = relationship(
        "IngestionJob",
        back_populates="staging_records",
    )