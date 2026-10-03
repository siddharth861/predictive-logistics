from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.forecast import predict_next_day_consumption
from app.ai.stockout import predict_stockout_risk
from app.models.inventory import Inventory


def calculate_supply_risk(
    db: Session,
    item_id: uuid.UUID,
    location_id: uuid.UUID,
) -> dict:
    """
    Calculate an explainable supply risk score.

    The score combines:
    - inventory coverage
    - stockout risk
    - demand pressure
    - forecast uncertainty

    This is a prototype decision-support score, not a
    calibrated probability of operational failure.
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

    stockout = predict_stockout_risk(
        db=db,
        item_id=item_id,
        location_id=location_id,
    )

    current_stock = float(
        inventory.quantity
    )

    minimum_stock = float(
        inventory.minimum_stock
    )

    predicted_consumption = float(
        forecast["predicted_quantity"]
    )

    days_of_cover = stockout["days_of_cover"]

    forecast_confidence = float(
        forecast["confidence"]
    )

    variability = float(
        stockout["consumption_variability_7d"]
    )

    # ---------------------------------------------------------
    # 1. Inventory risk: 0-40 points
    # ---------------------------------------------------------

    if days_of_cover is None:
        inventory_risk = 40.0
    elif days_of_cover <= 2:
        inventory_risk = 40.0
    elif days_of_cover <= 5:
        inventory_risk = 30.0
    elif days_of_cover <= 7:
        inventory_risk = 20.0
    elif days_of_cover <= 14:
        inventory_risk = 10.0
    else:
        inventory_risk = 0.0

    # ---------------------------------------------------------
    # 2. Demand pressure: 0-25 points
    # ---------------------------------------------------------

    if current_stock <= 0:
        demand_pressure = 25.0

    elif minimum_stock > 0:
        stock_ratio = (
            current_stock / minimum_stock
        )

        if stock_ratio <= 1:
            demand_pressure = 25.0
        elif stock_ratio <= 1.5:
            demand_pressure = 18.0
        elif stock_ratio <= 2:
            demand_pressure = 10.0
        else:
            demand_pressure = 0.0

    else:
        demand_pressure = 0.0

    # ---------------------------------------------------------
    # 3. Consumption variability: 0-20 points
    # ---------------------------------------------------------

    if predicted_consumption <= 0:
        variability_risk = 0.0
    else:
        variability_ratio = (
            variability
            / predicted_consumption
        )

        if variability_ratio >= 0.30:
            variability_risk = 20.0
        elif variability_ratio >= 0.20:
            variability_risk = 15.0
        elif variability_ratio >= 0.10:
            variability_risk = 8.0
        else:
            variability_risk = 0.0

    # ---------------------------------------------------------
    # 4. Forecast uncertainty: 0-15 points
    # ---------------------------------------------------------

    uncertainty_risk = (
        max(
            0.0,
            min(
                15.0,
                (100.0 - forecast_confidence)
                * 0.15,
            ),
        )
    )

    # ---------------------------------------------------------
    # Final score
    # ---------------------------------------------------------

    total_score = (
        inventory_risk
        + demand_pressure
        + variability_risk
        + uncertainty_risk
    )

    total_score = min(
        100.0,
        max(
            0.0,
            total_score,
        ),
    )

    if total_score >= 75:
        risk_level = "CRITICAL"
    elif total_score >= 50:
        risk_level = "HIGH"
    elif total_score >= 25:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return {
        "item_id": str(item_id),
        "location_id": str(location_id),
        "risk_score": round(
            total_score,
            2,
        ),
        "risk_level": risk_level,
        "components": {
            "inventory_risk": round(
                inventory_risk,
                2,
            ),
            "demand_pressure": round(
                demand_pressure,
                2,
            ),
            "variability_risk": round(
                variability_risk,
                2,
            ),
            "uncertainty_risk": round(
                uncertainty_risk,
                2,
            ),
        },
        "supporting_metrics": {
            "current_stock": round(
                current_stock,
                2,
            ),
            "minimum_stock": round(
                minimum_stock,
                2,
            ),
            "predicted_daily_consumption": round(
                predicted_consumption,
                2,
            ),
            "days_of_cover": (
                round(
                    days_of_cover,
                    2,
                )
                if days_of_cover is not None
                else None
            ),
            "forecast_confidence": round(
                forecast_confidence,
                2,
            ),
            "consumption_variability_7d": round(
                variability,
                2,
            ),
            "stockout_risk_level": stockout[
                "risk_level"
            ],
        },
    }