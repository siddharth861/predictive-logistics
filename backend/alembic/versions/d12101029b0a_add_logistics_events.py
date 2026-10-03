"""Add logistics events

Revision ID: d12101029b0a
Revises: 92da356f28c3
Create Date: 2026-10-03 13:22:48.619013

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d12101029b0a"
down_revision: Union[str, Sequence[str], None] = "92da356f28c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "logistics_events",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "event_type",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.String(length=20),
            nullable=False,
            server_default="INFO",
        ),
        sa.Column(
            "title",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "location_id",
            sa.UUID(),
            nullable=True,
        ),
        sa.Column(
            "vehicle_id",
            sa.UUID(),
            nullable=True,
        ),
        sa.Column(
            "shipment_id",
            sa.UUID(),
            nullable=True,
        ),
        sa.Column(
            "is_resolved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["shipment_id"],
            ["shipments.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_logistics_events_event_type",
        "logistics_events",
        ["event_type"],
    )

    op.create_index(
        "ix_logistics_events_severity",
        "logistics_events",
        ["severity"],
    )

    op.create_index(
        "ix_logistics_events_location_id",
        "logistics_events",
        ["location_id"],
    )

    op.create_index(
        "ix_logistics_events_vehicle_id",
        "logistics_events",
        ["vehicle_id"],
    )

    op.create_index(
        "ix_logistics_events_shipment_id",
        "logistics_events",
        ["shipment_id"],
    )

    op.create_index(
        "ix_logistics_events_is_resolved",
        "logistics_events",
        ["is_resolved"],
    )


def downgrade() -> None:
    op.drop_table("logistics_events")