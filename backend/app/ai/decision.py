from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.forecast import predict_next_day_consumption
from app.ai.risk import calculate_supply_risk
from app.ai.stockout import predict_stockout_risk
from app.models.inventory import Inventory


def analyze_what_if(
    db: Session,
    item_id: uuid.UUID,
    location_id: uuid.UUID,
    additional_supply: float = 0.0,
) -> dict[str, Any]:
    inventory = db.scalar(
        select(Inventory).where(
            Inventory.item_id == item_id,
            Inventory.location_id == location_id,
        )
    )

    if inventory is None:
        raise ValueError(
            "No inventory record found for this item and location."
        )

    if additional_supply < 0:
        raise ValueError(
            "Additional supply cannot be negative."
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

    risk = calculate_supply_risk(
        db=db,
        item_id=item_id,
        location_id=location_id,
    )

    current_stock = float(inventory.quantity)
    minimum_stock = float(inventory.minimum_stock)
    predicted_daily_consumption = float(
        forecast["predicted_quantity"]
    )

    projected_stock = (
        current_stock
        + additional_supply
        - predicted_daily_consumption
    )

    if predicted_daily_consumption > 0:
        projected_days_of_cover = (
            current_stock + additional_supply
        ) / predicted_daily_consumption
    else:
        projected_days_of_cover = None

    if projected_stock <= 0:
        projected_status = "STOCKOUT"
    elif projected_stock <= minimum_stock:
        projected_status = "BELOW_MINIMUM"
    else:
        projected_status = "HEALTHY"

    if projected_status == "STOCKOUT":
        decision = "URGENT_RESUPPLY"
    elif projected_status == "BELOW_MINIMUM":
        decision = "CONSIDER_RESUPPLY"
    else:
        decision = "NO_IMMEDIATE_ACTION"

    return {
        "item_id": str(item_id),
        "location_id": str(location_id),
        "current_state": {
            "current_stock": round(current_stock, 2),
            "minimum_stock": round(minimum_stock, 2),
            "predicted_daily_consumption": round(
                predicted_daily_consumption,
                2,
            ),
            "current_days_of_cover": stockout[
                "days_of_cover"
            ],
            "stockout_risk": stockout[
                "risk_level"
            ],
            "supply_risk": risk[
                "risk_level"
            ],
            "supply_risk_score": risk[
                "risk_score"
            ],
        },
        "scenario": {
            "additional_supply": round(
                additional_supply,
                2,
            ),
            "projected_stock_after_next_day": round(
                projected_stock,
                2,
            ),
            "projected_days_of_cover": (
                round(
                    projected_days_of_cover,
                    2,
                )
                if projected_days_of_cover is not None
                else None
            ),
            "projected_status": projected_status,
        },
        "decision": decision,
        "explanation": (
            f"Adding {additional_supply:.2f} units of supply "
            f"would result in approximately "
            f"{projected_stock:.2f} units remaining after "
            f"the next day's predicted consumption."
        ),
    }