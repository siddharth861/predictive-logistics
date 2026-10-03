from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.features import build_consumption_features
from app.ai.forecast import predict_next_day_consumption
from app.models.inventory import Inventory


def predict_stockout_risk(
    db: Session,
    item_id: uuid.UUID,
    location_id: uuid.UUID,
) -> dict:
    """
    Estimate short-term stockout risk using current inventory,
    minimum stock, forecasted consumption, and consumption variability.
    """

    inventory = db.scalar(
        select(Inventory).where(
            Inventory.item_id == item_id,
            Inventory.location_id == location_id,
        )
    )

    if inventory is None:
        raise ValueError(
            "Inventory record not found for this item and location."
        )

    forecast = predict_next_day_consumption(
        db=db,
        item_id=item_id,
        location_id=location_id,
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

    latest = features.iloc[-1]

    current_stock = float(inventory.quantity)
    minimum_stock = float(inventory.minimum_stock)

    predicted_daily_consumption = float(
        forecast["predicted_quantity"]
    )

    variability = float(
        latest["rolling_std_7"]
    )

    if predicted_daily_consumption <= 0:
        days_of_cover = None
    else:
        days_of_cover = (
            current_stock / predicted_daily_consumption
        )

    projected_stock_next_day = (
        current_stock - predicted_daily_consumption
    )

    if current_stock <= minimum_stock:
        risk_level = "CRITICAL"
    elif projected_stock_next_day <= minimum_stock:
        risk_level = "HIGH"
    elif days_of_cover is not None and days_of_cover <= 7:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    if days_of_cover is None:
        risk_message = (
            "Consumption forecast is not positive, so "
            "days of stock cover cannot be estimated."
        )
    else:
        risk_message = (
            f"Current inventory provides approximately "
            f"{days_of_cover:.1f} days of forecasted consumption."
        )

    return {
        "item_id": str(item_id),
        "location_id": str(location_id),
        "current_stock": round(current_stock, 2),
        "minimum_stock": round(minimum_stock, 2),
        "predicted_daily_consumption": round(
            predicted_daily_consumption,
            2,
        ),
        "projected_stock_next_day": round(
            projected_stock_next_day,
            2,
        ),
        "days_of_cover": (
            round(days_of_cover, 2)
            if days_of_cover is not None
            else None
        ),
        "consumption_variability_7d": round(
            variability,
            2,
        ),
        "forecast_confidence": forecast["confidence"],
        "risk_level": risk_level,
        "risk_message": risk_message,
    }
