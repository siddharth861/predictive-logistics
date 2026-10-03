from __future__ import annotations

import uuid
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.shipment import Shipment


MODEL_PATH = Path("/app/storage/models/shipment_eta.joblib")


FEATURE_COLUMNS = [
    "quantity",
    "departure_hour",
    "departure_day_of_week",
    "departure_delay_hours",
    "planned_duration_hours",
]


def build_shipment_features(
    db: Session,
) -> pd.DataFrame:
    """
    Build historical shipment features for ETA prediction.

    Only completed shipments with all required timestamps
    are used.
    """

    shipments = db.scalars(
        select(Shipment)
        .where(
            Shipment.status == "DELIVERED",
            Shipment.planned_departure.is_not(None),
            Shipment.actual_departure.is_not(None),
            Shipment.estimated_arrival.is_not(None),
            Shipment.actual_arrival.is_not(None),
        )
        .order_by(Shipment.actual_departure)
    ).all()

    rows = []

    for shipment in shipments:
        actual_duration_hours = (
            shipment.actual_arrival
            - shipment.actual_departure
        ).total_seconds() / 3600.0

        departure_delay_hours = (
            shipment.actual_departure
            - shipment.planned_departure
        ).total_seconds() / 3600.0

        planned_duration_hours = (
            shipment.estimated_arrival
            - shipment.planned_departure
        ).total_seconds() / 3600.0

        delay_hours = (
            actual_duration_hours
            + departure_delay_hours
            - planned_duration_hours
        )

        rows.append(
            {
                "shipment_id": str(shipment.id),
                "quantity": float(shipment.quantity),
                "departure_hour": (
                    shipment.actual_departure.hour
                ),
                "departure_day_of_week": (
                    shipment.actual_departure.weekday()
                ),
                "departure_delay_hours": (
                    departure_delay_hours
                ),
                "planned_duration_hours": (
                    planned_duration_hours
                ),
                "actual_duration_hours": (
                    actual_duration_hours
                ),
                "delay_hours": delay_hours,
                "delayed": (
                    1 if delay_hours > 1.0 else 0
                ),
            }
        )

    return pd.DataFrame(rows)


def train_eta_model(
    db: Session,
) -> dict:
    """
    Train a Random Forest model to predict shipment travel time.
    """

    data = build_shipment_features(db)

    if data.empty:
        raise ValueError(
            "No completed shipment data available."
        )

    if len(data) < 10:
        raise ValueError(
            "At least 10 completed shipments are required."
        )

    X = data[FEATURE_COLUMNS]
    y = data["actual_duration_hours"]

    from sklearn.ensemble import RandomForestRegressor

    model = RandomForestRegressor(
        n_estimators=100,
        random_state=42,
        max_depth=8,
    )

    model.fit(X, y)

    MODEL_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    joblib.dump(
        {
            "model": model,
            "feature_columns": FEATURE_COLUMNS,
        },
        MODEL_PATH,
    )

    return {
        "message": (
            "Shipment ETA model trained successfully."
        ),
        "model_path": str(MODEL_PATH),
        "training_samples": len(data),
        "features": FEATURE_COLUMNS,
    }


def predict_shipment_eta(
    db: Session,
    shipment_id: uuid.UUID,
) -> dict:
    """
    Predict travel duration and delay risk for a shipment.
    """

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            "Shipment ETA model has not been trained yet."
        )

    shipment = db.get(
        Shipment,
        shipment_id,
    )

    if shipment is None:
        raise ValueError(
            "Shipment not found."
        )

    if shipment.planned_departure is None:
        raise ValueError(
            "Shipment has no planned departure time."
        )

    if shipment.estimated_arrival is None:
        raise ValueError(
            "Shipment has no estimated arrival time."
        )

    departure_time = (
        shipment.actual_departure
        or shipment.planned_departure
    )

    departure_delay_hours = (
        (
            departure_time
            - shipment.planned_departure
        ).total_seconds()
        / 3600.0
    )

    planned_duration_hours = (
        (
            shipment.estimated_arrival
            - shipment.planned_departure
        ).total_seconds()
        / 3600.0
    )

    input_data = pd.DataFrame(
        [
            {
                "quantity": float(
                    shipment.quantity
                ),
                "departure_hour": (
                    departure_time.hour
                ),
                "departure_day_of_week": (
                    departure_time.weekday()
                ),
                "departure_delay_hours": (
                    departure_delay_hours
                ),
                "planned_duration_hours": (
                    planned_duration_hours
                ),
            }
        ]
    )

    model_data = joblib.load(
        MODEL_PATH
    )

    model = model_data["model"]

    tree_predictions = np.array(
        [
            estimator.predict(
                input_data[
                    FEATURE_COLUMNS
                ].to_numpy()
            )[0]
            for estimator in model.estimators_
        ]
    )

    predicted_duration_hours = float(
        np.mean(tree_predictions)
    )

    duration_std = float(
        np.std(tree_predictions)
    )

    predicted_arrival = (
        departure_time
        + pd.Timedelta(
            hours=predicted_duration_hours
        )
    )

    expected_delay_hours = (
        predicted_duration_hours
        - planned_duration_hours
    )

    if expected_delay_hours > 2:
        risk_level = "HIGH"
    elif expected_delay_hours > 1:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    confidence = max(
        0.0,
        min(
            100.0,
            100.0
            * (
                1.0
                - (
                    duration_std
                    / max(
                        predicted_duration_hours,
                        0.01,
                    )
                )
            ),
        ),
    )

    return {
        "shipment_id": str(
            shipment.id
        ),
        "predicted_travel_time_hours": round(
            predicted_duration_hours,
            2,
        ),
        "planned_travel_time_hours": round(
            planned_duration_hours,
            2,
        ),
        "expected_delay_hours": round(
            expected_delay_hours,
            2,
        ),
        "predicted_arrival": (
            predicted_arrival.isoformat()
        ),
        "confidence": round(
            confidence,
            2,
        ),
        "risk_level": risk_level,
        "explanation": {
            "shipment_quantity": round(
                float(shipment.quantity),
                2,
            ),
            "departure_delay_hours": round(
                departure_delay_hours,
                2,
            ),
            "planned_duration_hours": round(
                planned_duration_hours,
                2,
            ),
        },
    }