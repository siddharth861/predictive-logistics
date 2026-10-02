import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ValidationErrorStatus(str, enum.Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    IGNORED = "IGNORED"


class ValidationError(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "validation_errors"

    ingestion_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    row_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    field_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    raw_value: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    error_code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    error_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    status: Mapped[ValidationErrorStatus] = mapped_column(
        Enum(
            ValidationErrorStatus,
            name="validation_error_status",
        ),
        nullable=False,
        default=ValidationErrorStatus.OPEN,
        index=True,
    )

    ingestion_job: Mapped["IngestionJob"] = relationship(
        "IngestionJob",
        back_populates="validation_errors",
    )