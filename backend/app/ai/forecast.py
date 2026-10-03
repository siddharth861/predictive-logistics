from __future__ import annotations

from pathlib import Path
import uuid

import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.ai.features import build_consumption_features
from app.ai.training import FEATURE_COLUMNS, prepare_training_data
from app.models.item import Item


MODEL_PATH = Path("/app/storage/models/consumption_forecast.joblib")


def train_consumption_model(
    db: Session,
    item_id: uuid.UUID,
    location_id: uuid.UUID,
) -> dict:
    """
    Train a Random Forest model to predict NEXT-DAY consumption.

    Each training row uses historical information available on day D
    to predict consumption on day D+1.
    """

    features = build_consumption_features(
        db=db,
        item_id=item_id,
        location_id=location_id,
    )

    if features.empty:
        raise ValueError("No consumption data available for training.")

    # Target = next day's consumption.
    features = features.copy()
    features["target_next_day"] = features["quantity"].shift(-1)

    # Remove the final row because there is no known next-day target.
    features = features.dropna(
        subset=FEATURE_COLUMNS + ["target_next_day"]
    )

    if len(features) < 10:
        raise ValueError(
            "At least 10 training samples are required."
        )

    X = features[FEATURE_COLUMNS]
    y = features["target_next_day"]

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
            "item_id": str(item_id),
            "location_id": str(location_id),
            "feature_columns": FEATURE_COLUMNS,
        },
        MODEL_PATH,
    )

    return {
        "message": "Consumption forecast model trained successfully.",
        "model_path": str(MODEL_PATH),
        "item_id": str(item_id),
        "location_id": str(location_id),
        "training_samples": len(X),
        "features": FEATURE_COLUMNS,
    }


def predict_next_day_consumption(
    db: Session,
    item_id: uuid.UUID,
    location_id: uuid.UUID,
) -> dict:
    """
    Predict consumption for the next day using the latest available
    historical consumption data.
    """

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            "Forecast model has not been trained yet."
        )

    features = build_consumption_features(
        db=db,
        item_id=item_id,
        location_id=location_id,
    )

    if features.empty:
        raise ValueError(
            "No historical consumption data available."
        )

    latest = features.iloc[[-1]][FEATURE_COLUMNS]

    model_data = joblib.load(MODEL_PATH)
    model = model_data["model"]

    # Use individual trees to estimate prediction uncertainty.
    tree_predictions = np.array(
        [
            estimator.predict(latest.to_numpy())[0]
            for estimator in model.estimators_
        ]
    )

    predicted_quantity = float(
        np.mean(tree_predictions)
    )

    prediction_std = float(
        np.std(tree_predictions)
    )

    lower_bound = max(
        0.0,
        predicted_quantity - (1.96 * prediction_std),
    )

    upper_bound = max(
        0.0,
        predicted_quantity + (1.96 * prediction_std),
    )

    if predicted_quantity > 0:
        confidence = max(
            0.0,
            min(
                100.0,
                100.0 * (
                    1.0 - (
                        prediction_std
                        / predicted_quantity
                    )
                ),
            ),
        )
    else:
        confidence = 0.0

    item = db.get(Item, item_id)

    unit = (
        item.unit
        if item is not None
        else "UNIT"
    )

    previous_day_consumption = float(
        features.iloc[-1]["quantity"]
    )

    previous_week_consumption = (
        float(features.iloc[-8]["quantity"])
        if len(features) >= 8
        else None
    )

    recent_7_day_average = float(
        features.iloc[-1]["rolling_mean_7"]
    )

    recent_7_day_variability = float(
        features.iloc[-1]["rolling_std_7"]
    )

    recent_14_day_average = float(
        features.iloc[-1]["rolling_mean_14"]
    )

    recent_30_day_average = float(
        features.iloc[-1]["rolling_mean_30"]
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
        "training_samples": len(
            features.dropna(
                subset=FEATURE_COLUMNS
            )
        ),
        "forecast_horizon": "NEXT_DAY",
        "explanation": {
            "previous_day_consumption": round(
                previous_day_consumption,
                2,
            ),
            "previous_week_consumption": (
                round(
                    previous_week_consumption,
                    2,
                )
                if previous_week_consumption is not None
                else None
            ),
            "recent_7_day_average": round(
                recent_7_day_average,
                2,
            ),
            "recent_7_day_variability": round(
                recent_7_day_variability,
                2,
            ),
            "recent_14_day_average": round(
                recent_14_day_average,
                2,
            ),
            "recent_30_day_average": round(
                recent_30_day_average,
                2,
            ),
        },
    }