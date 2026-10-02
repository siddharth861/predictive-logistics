"""add postgis locations and routes

Revision ID: 1e71ff967c77
Revises: d54b66cd48da
Create Date: 2026-10-02

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import geoalchemy2


# revision identifiers, used by Alembic.
revision: str = "1e71ff967c77"
down_revision: Union[str, Sequence[str], None] = "d54b66cd48da"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "code",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(length=150),
            nullable=False,
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "location_type",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "geometry",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_index(
        op.f("ix_locations_code"),
        "locations",
        ["code"],
        unique=True,
    )

    op.create_index(
        op.f("ix_locations_location_type"),
        "locations",
        ["location_type"],
        unique=False,
    )

    op.create_index(
        op.f("ix_locations_is_active"),
        "locations",
        ["is_active"],
        unique=False,
    )

    op.create_table(
        "routes",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "code",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(length=150),
            nullable=False,
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "origin_location_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "destination_location_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "geometry",
            geoalchemy2.types.Geometry(
                geometry_type="LINESTRING",
                srid=4326,
                dimension=2,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["destination_location_id"],
            ["locations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["origin_location_id"],
            ["locations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_index(
        op.f("ix_routes_code"),
        "routes",
        ["code"],
        unique=True,
    )

    op.create_index(
        op.f("ix_routes_origin_location_id"),
        "routes",
        ["origin_location_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_routes_destination_location_id"),
        "routes",
        ["destination_location_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_routes_is_active"),
        "routes",
        ["is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_routes_is_active"),
        table_name="routes",
    )

    op.drop_index(
        op.f("ix_routes_destination_location_id"),
        table_name="routes",
    )

    op.drop_index(
        op.f("ix_routes_origin_location_id"),
        table_name="routes",
    )

    op.drop_index(
        op.f("ix_routes_code"),
        table_name="routes",
    )

    op.drop_table("routes")

    op.drop_index(
        op.f("ix_locations_is_active"),
        table_name="locations",
    )

    op.drop_index(
        op.f("ix_locations_location_type"),
        table_name="locations",
    )

    op.drop_index(
        op.f("ix_locations_code"),
        table_name="locations",
    )

    op.drop_table("locations")