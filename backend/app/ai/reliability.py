from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.forecast import predict_next_day_consumption
from app.models.consumption import ConsumptionRecord


def assess_forecast_reliability(
    db: Session,
    item_id: uuid.UUID,
    location_id: uuid.UUID,
) -> dict[str, Any]:
    """
    Assess forecast reliability using two separate dimensions:

    1. Model confidence:
       How consistent the model's individual tree predictions are.

    2. Data freshness:
       How recently the latest consumption record was received.

    These are intentionally kept separate.
    """

    forecast = predict_next_day_consumption(
        db=db,
        item_id=item_id,
        location_id=location_id,
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

    # ConsumptionRecord stores the observation date rather
    # than a separate ingestion timestamp.
    latest_date = latest_record.consumption_date

    today = datetime.now(
        timezone.utc
    ).date()

    data_age_days = (
        today - latest_date
    ).days

    if data_age_days <= 1:
        freshness_status = "FRESH"
    elif data_age_days <= 3:
        freshness_status = "AGING"
    else:
        freshness_status = "STALE"

    model_confidence = float(
        forecast["confidence"]
    )

    if model_confidence >= 90:
        confidence_status = "HIGH"
    elif model_confidence >= 75:
        confidence_status = "MEDIUM"
    else:
        confidence_status = "LOW"

    if (
        confidence_status == "HIGH"
        and freshness_status == "FRESH"
    ):
        reliability_level = "HIGH"

    elif (
        confidence_status == "LOW"
        or freshness_status == "STALE"
    ):
        reliability_level = "LOW"

    else:
        reliability_level = "MEDIUM"

    return {
        "item_id": str(item_id),
        "location_id": str(location_id),
        "reliability_level": reliability_level,
        "model_confidence": round(
            model_confidence,
            2,
        ),
        "confidence_status": confidence_status,
        "latest_consumption_date": (
            latest_date.isoformat()
        ),
        "data_age_days": data_age_days,
        "freshness_status": freshness_status,
        "training_samples": forecast[
            "training_samples"
        ],
        "forecast_horizon": forecast[
            "forecast_horizon"
        ],
        "interpretation": (
            "High reliability: model confidence is high "
            "and the latest consumption data is fresh."
            if reliability_level == "HIGH"
            else (
                "Low reliability: review the underlying "
                "data or model before relying heavily on "
                "this forecast."
                if reliability_level == "LOW"
                else (
                    "Medium reliability: the forecast is "
                    "usable, but either model confidence "
                    "or data freshness warrants attention."
                )
            )
        ),
    }