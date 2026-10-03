from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session
from sklearn.ensemble import RandomForestRegressor

from app.ai.features import build_consumption_features
from app.models.consumption import ConsumptionRecord
from app.models.item import Item


MODEL_PATH = Path(
    "/app/storage/models/consumption_forecast.joblib"
)

FEATURE_COLUMNS = [
    "day_of_week",
    "lag_1",
    "lag_7",
    "rolling_mean_7",
    "rolling_std_7",
    "rolling_mean_14",
    "rolling_mean_30",
]


def train_consumption_model(
    db: Session,
    item_id: uuid.UUID,
    location_id: uuid.UUID,
) -> dict[str, Any]:
    features = build_consumption_features(
        db=db,
        item_id=item_id,
        location_id=location_id,
    )

    features["target_next_day"] = (
        features["quantity"].shift(-1)
    )

    training_data = features.dropna(
        subset=FEATURE_COLUMNS + ["target_next_day"]
    )

    if len(training_data) < 10:
        raise ValueError(
            "At least 10 complete records are required "
            "to train the consumption model."
        )

    X = training_data[FEATURE_COLUMNS]
    y = training_data["target_next_day"]

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
            "training_samples": len(training_data),
        },
        MODEL_PATH,
    )

    return {
        "status": "trained",
        "training_samples": len(training_data),
        "features": FEATURE_COLUMNS,
        "model_path": str(MODEL_PATH),
    }


def predict_next_day_consumption(
    db: Session,
    item_id: uuid.UUID,
    location_id: uuid.UUID,
) -> dict[str, Any]:
    if not MODEL_PATH.exists():
        train_consumption_model(
            db=db,
            item_id=item_id,
            location_id=location_id,
        )

    artifact = joblib.load(MODEL_PATH)

    model = artifact["model"]
    feature_columns = artifact["feature_columns"]

    features = build_consumption_features(
        db=db,
        item_id=item_id,
        location_id=location_id,
    )

    latest = features.dropna(
        subset=feature_columns
    ).iloc[-1]

    X_latest = latest[
        feature_columns
    ].to_frame().T

    predicted_quantity = float(
        model.predict(X_latest)[0]
    )

    training_data = features.copy()

    training_data["target_next_day"] = (
        training_data["quantity"].shift(-1)
    )

    training_data = training_data.dropna(
        subset=feature_columns + ["target_next_day"]
    )

    training_samples = len(training_data)

    residuals = (
        training_data["target_next_day"]
        - model.predict(
            training_data[feature_columns]
        )
    )

    residual_std = float(
        np.std(residuals)
    )

    if residual_std <= 0:
        residual_std = max(
            predicted_quantity * 0.10,
            1.0,
        )

    lower_bound = max(
        0.0,
        predicted_quantity
        - (1.38 * residual_std),
    )

    upper_bound = (
        predicted_quantity
        + (1.38 * residual_std)
    )

    interval_width = (
        upper_bound - lower_bound
    )

    confidence = max(
        0.0,
        min(
            99.0,
            100.0
            - (
                interval_width
                / max(
                    predicted_quantity,
                    1.0,
                )
                * 100.0
            ),
        ),
    )

    latest_record = db.scalar(
        select(ConsumptionRecord)
        .where(
            ConsumptionRecord.item_id == item_id,
            ConsumptionRecord.location_id == location_id,
        )
        .order_by(
            ConsumptionRecord.consumption_date.desc()
        )
    )

    if latest_record is None:
        raise ValueError(
            "No consumption data available."
        )

    item = db.scalar(
        select(Item).where(
            Item.id == item_id
        )
    )

    unit = (
        item.unit
        if item is not None
        else None
    )

    return {
        "item_id": str(item_id),
        "location_id": str(location_id),
        "predicted_quantity": round(
            predicted_quantity,
            2,
        ),
        "lower_bound": round(
            lower_bound,
            2,
        ),
        "upper_bound": round(
            upper_bound,
            2,
        ),
        "confidence": round(
            confidence,
            2,
        ),
        "unit": unit,
        "training_samples": training_samples,
        "forecast_horizon": "NEXT_DAY",
        "explanation": {
            "previous_day_consumption": round(
                float(
                    latest["lag_1"]
                ),
                2,
            ),
            "previous_week_consumption": round(
                float(
                    latest["lag_7"]
                ),
                2,
            ),
            "recent_7_day_average": round(
                float(
                    latest["rolling_mean_7"]
                ),
                2,
            ),
            "recent_7_day_variability": round(
                float(
                    latest["rolling_std_7"]
                ),
                2,
            ),
            "recent_14_day_average": round(
                float(
                    latest["rolling_mean_14"]
                ),
                2,
            ),
            "recent_30_day_average": round(
                float(
                    latest["rolling_mean_30"]
                ),
                2,
            ),
        },
    }