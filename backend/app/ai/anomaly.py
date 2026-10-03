from __future__ import annotations

import uuid
from typing import Any

from sklearn.ensemble import IsolationForest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.features import build_consumption_features
from app.models.consumption import ConsumptionRecord


def detect_consumption_anomalies(
    db: Session,
    item_id: uuid.UUID,
    location_id: uuid.UUID,
) -> dict[str, Any]:
    records = db.scalars(
        select(ConsumptionRecord)
        .where(
            ConsumptionRecord.item_id == item_id,
            ConsumptionRecord.location_id == location_id,
        )
        .order_by(
            ConsumptionRecord.consumption_date
        )
    ).all()

    if len(records) < 10:
        raise ValueError(
            "At least 10 consumption records are required "
            "for anomaly detection."
        )

    features = build_consumption_features(
        db=db,
        item_id=item_id,
        location_id=location_id,
    )

    feature_columns = [
        "quantity",
        "day_of_week",
        "lag_1",
        "lag_7",
        "rolling_mean_7",
        "rolling_std_7",
    ]

    model_data = features.dropna(
        subset=feature_columns
    ).copy()

    if len(model_data) < 10:
        raise ValueError(
            "Not enough complete feature records "
            "for anomaly detection."
        )

    model = IsolationForest(
        n_estimators=100,
        contamination=0.10,
        random_state=42,
    )

    predictions = model.fit_predict(
        model_data[feature_columns]
    )

    scores = model.decision_function(
        model_data[feature_columns]
    )

    model_data["prediction"] = predictions
    model_data["anomaly_score"] = scores

    anomaly_rows = model_data[
        model_data["prediction"] == -1
    ]

    latest = model_data.iloc[-1]

    latest_is_anomaly = (
        int(latest["prediction"]) == -1
    )

    if latest_is_anomaly:
        latest_level = "HIGH"
    else:
        latest_level = "NORMAL"

    anomalies = []

    for _, row in anomaly_rows.iterrows():
        anomalies.append(
            {
                "date": row["date"].isoformat(),
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
        "records_analyzed": len(model_data),
        "anomalies_detected": len(anomalies),
        "latest_record": {
            "date": latest["date"].isoformat(),
            "quantity": round(
                float(latest["quantity"]),
                2,
            ),
            "anomaly_score": round(
                float(latest["anomaly_score"]),
                4,
            ),
            "is_anomaly": latest_is_anomaly,
            "anomaly_level": latest_level,
        },
        "anomalies": anomalies,
    }