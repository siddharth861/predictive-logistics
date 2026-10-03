from __future__ import annotations

import uuid

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.features import build_consumption_features


def detect_consumption_anomalies(
    db: Session,
    item_id: uuid.UUID,
    location_id: uuid.UUID,
) -> dict:
    """
    Detect unusual consumption values using Isolation Forest.

    The model learns the normal consumption pattern from the
    available historical consumption records.
    """

    features = build_consumption_features(
        db=db,
        item_id=item_id,
        location_id=location_id,
    )

    if features.empty:
        raise ValueError(
            "No historical consumption data available."
        )

    data = features.copy()

    required_columns = [
        "quantity",
        "day_of_week",
        "lag_1",
        "lag_7",
        "rolling_mean_7",
        "rolling_std_7",
    ]

    data = data.dropna(
        subset=required_columns
    )

    if len(data) < 10:
        raise ValueError(
            "At least 10 consumption records are required "
            "for anomaly detection."
        )

    X = data[required_columns]

    from sklearn.ensemble import IsolationForest

    model = IsolationForest(
        n_estimators=100,
        contamination=0.10,
        random_state=42,
    )

    predictions = model.fit_predict(X)

    scores = model.decision_function(X)

    data["anomaly_prediction"] = predictions
    data["anomaly_score"] = scores

    anomalies = data[
        data["anomaly_prediction"] == -1
    ]

    latest = data.iloc[-1]

    latest_is_anomaly = (
        int(latest["anomaly_prediction"]) == -1
    )

    latest_score = float(
        latest["anomaly_score"]
    )

    if latest_is_anomaly:
        anomaly_level = "HIGH"
    elif latest_score < 0.10:
        anomaly_level = "MEDIUM"
    else:
        anomaly_level = "NORMAL"

    anomaly_records = []

    for _, row in anomalies.iterrows():
        anomaly_records.append(
            {
                "date": (
                    row["date"].isoformat()
                    if hasattr(
                        row["date"],
                        "isoformat",
                    )
                    else str(row["date"])
                ),
                "quantity": round(
                    float(row["quantity"]),
                    2,
                ),
                "anomaly_score": round(
                    float(row["anomaly_score"]),
                    4,
                ),
                "rolling_mean_7": round(
                    float(row["rolling_mean_7"]),
                    2,
                ),
            }
        )

    return {
        "item_id": str(item_id),
        "location_id": str(location_id),
        "records_analyzed": len(data),
        "anomalies_detected": len(anomalies),
        "latest_record": {
            "date": (
                latest["date"].isoformat()
                if hasattr(
                    latest["date"],
                    "isoformat",
                )
                else str(latest["date"])
            ),
            "quantity": round(
                float(latest["quantity"]),
                2,
            ),
            "anomaly_score": round(
                latest_score,
                4,
            ),
            "is_anomaly": latest_is_anomaly,
            "anomaly_level": anomaly_level,
        },
        "anomalies": anomaly_records,
    }