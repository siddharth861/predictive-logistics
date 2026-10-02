import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DataSourceType(str, enum.Enum):
    FILE = "FILE"
    API = "API"
    DATABASE = "DATABASE"
    DEVICE = "DEVICE"
    MANUAL = "MANUAL"


class DataSourceStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ERROR = "ERROR"


class DataSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "data_sources"

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    source_type: Mapped[DataSourceType] = mapped_column(
        Enum(DataSourceType, name="data_source_type"),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[DataSourceStatus] = mapped_column(
        Enum(DataSourceStatus, name="data_source_status"),
        nullable=False,
        default=DataSourceStatus.ACTIVE,
    )

    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    ingestion_jobs: Mapped[list["IngestionJob"]] = relationship(
        "IngestionJob",
        back_populates="source",
    )

    mapping_configs: Mapped[list["MappingConfig"]] = relationship(
        "MappingConfig",
        back_populates="source",
    )