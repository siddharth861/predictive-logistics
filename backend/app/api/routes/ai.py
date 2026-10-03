from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.forecast import predict_next_day_consumption
from app.ai.stockout import predict_stockout_risk
from app.db.session import get_db


router = APIRouter(
    prefix="/api/ai",
    tags=["AI"],
)


@router.get("/forecast/{item_id}/{location_id}")
def get_consumption_forecast(
    item_id: UUID,
    location_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return predict_next_day_consumption(
            db=db,
            item_id=item_id,
            location_id=location_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Forecast model has not been trained yet.",
        ) from exc


@router.get("/stockout/{item_id}/{location_id}")
def get_stockout_risk(
    item_id: UUID,
    location_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return predict_stockout_risk(
            db=db,
            item_id=item_id,
            location_id=location_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Forecast model has not been trained yet.",
        ) from exc