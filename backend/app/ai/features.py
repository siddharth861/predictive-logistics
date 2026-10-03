from __future__ import annotations

import uuid

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.consumption import ConsumptionRecord


def build_consumption_features(
    db: Session,
    item_id: uuid.UUID,
    location_id: uuid.UUID,
) -> pd.DataFrame:
    """
    Build ML-ready time-series features from historical consumption.

    The returned dataframe contains one row per consumption date.
    """

    statement = (
        select(
            ConsumptionRecord.consumption_date,
            ConsumptionRecord.quantity,
        )
        .where(
            ConsumptionRecord.item_id == item_id,
            ConsumptionRecord.location_id == location_id,
        )
        .order_by(ConsumptionRecord.consumption_date)
    )

    rows = db.execute(statement).all()

    if not rows:
        return pd.DataFrame(
            columns=[
                "date",
                "quantity",
                "day_of_week",
                "lag_1",
                "lag_7",
                "rolling_mean_7",
                "rolling_std_7",
                "rolling_mean_14",
                "rolling_mean_30",
            ]
        )

    df = pd.DataFrame(
        [
            {
                "date": row.consumption_date,
                "quantity": row.quantity,
            }
            for row in rows
        ]
    )

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    df["day_of_week"] = df["date"].dt.dayofweek

    df["lag_1"] = df["quantity"].shift(1)
    df["lag_7"] = df["quantity"].shift(7)

    df["rolling_mean_7"] = (
        df["quantity"]
        .rolling(window=7, min_periods=1)
        .mean()
    )

    df["rolling_std_7"] = (
        df["quantity"]
        .rolling(window=7, min_periods=1)
        .std()
        .fillna(0)
    )

    df["rolling_mean_14"] = (
        df["quantity"]
        .rolling(window=14, min_periods=1)
        .mean()
    )

    df["rolling_mean_30"] = (
        df["quantity"]
        .rolling(window=30, min_periods=1)
        .mean()
    )

    return df