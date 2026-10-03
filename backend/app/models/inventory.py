import uuid

from sqlalchemy import Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Inventory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inventory"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    quantity: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
    )

    minimum_stock: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
    )

    maximum_stock: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    item: Mapped["Item"] = relationship(
        "Item",
        back_populates="inventories",
    )

    location: Mapped["Location"] = relationship(
        "Location",
    )