"""Extend data sources for universal ingestion

Revision ID: c4b4ce7f3cf3
Revises: 362a204a8fee
Create Date: 2026-10-02 18:29:43.152567

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4b4ce7f3cf3"
down_revision: Union[str, Sequence[str], None] = "362a204a8fee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


data_source_category_enum = sa.Enum(
    "INVENTORY",
    "CONSUMPTION",
    "VEHICLES",
    "SHIPMENTS",
    "LOCATIONS",
    "ROUTES",
    "WEATHER",
    "DEMAND",
    "MAINTENANCE",
    "CUSTOM",
    name="data_source_category",
)


def upgrade() -> None:
    """Upgrade schema."""

    # Create the PostgreSQL enum type first.
    data_source_category_enum.create(
        op.get_bind(),
        checkfirst=True,
    )

    # Add the new category column.
    op.add_column(
        "data_sources",
        sa.Column(
            "data_category",
            data_source_category_enum,
            nullable=True,
        ),
    )

    # Existing rows need a valid category.
    op.execute(
        """
        UPDATE data_sources
        SET data_category = 'CUSTOM'
        WHERE data_category IS NULL
        """
    )

    # Make the column mandatory after existing rows are populated.
    op.alter_column(
        "data_sources",
        "data_category",
        nullable=False,
    )

    # Add source-specific configuration.
    op.add_column(
        "data_sources",
        sa.Column(
            "config",
            sa.JSON(),
            nullable=True,
        ),
    )

    # Add schema version tracking.
    op.add_column(
        "data_sources",
        sa.Column(
            "schema_version",
            sa.String(length=50),
            nullable=True,
        ),
    )

    # Existing sources start at schema version 1.0.
    op.execute(
        """
        UPDATE data_sources
        SET schema_version = '1.0'
        WHERE schema_version IS NULL
        """
    )

    # Make schema version mandatory.
    op.alter_column(
        "data_sources",
        "schema_version",
        nullable=False,
    )

    # Store the latest source/ingestion error.
    op.add_column(
        "data_sources",
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column(
        "data_sources",
        "last_error",
    )

    op.drop_column(
        "data_sources",
        "schema_version",
    )

    op.drop_column(
        "data_sources",
        "config",
    )

    op.drop_column(
        "data_sources",
        "data_category",
    )

    data_source_category_enum.drop(
        op.get_bind(),
        checkfirst=True,
    )