from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.ai.anomaly import detect_consumption_anomalies
from app.ai.decision import analyze_what_if
from app.ai.eta import predict_shipment_eta
from app.ai.explain import explain_supply_risk
from app.ai.forecast import predict_next_day_consumption
from app.ai.reliability import assess_forecast_reliability
from app.ai.risk import calculate_supply_risk
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
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            404,
            "Forecast model has not been trained yet.",
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
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            404,
            "Forecast model has not been trained yet.",
        ) from exc


@router.get("/eta/{shipment_id}")
def get_shipment_eta(
    shipment_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return predict_shipment_eta(
            db=db,
            shipment_id=shipment_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            404,
            "Shipment ETA model has not been trained yet.",
        ) from exc


@router.get("/risk/{item_id}/{location_id}")
def get_supply_risk(
    item_id: UUID,
    location_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return calculate_supply_risk(
            db=db,
            item_id=item_id,
            location_id=location_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            404,
            "Required AI model has not been trained yet.",
        ) from exc


@router.get("/anomaly/{item_id}/{location_id}")
def get_consumption_anomalies(
    item_id: UUID,
    location_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return detect_consumption_anomalies(
            db=db,
            item_id=item_id,
            location_id=location_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/risk/{item_id}/{location_id}/explanation")
def get_supply_risk_explanation(
    item_id: UUID,
    location_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        risk_result = calculate_supply_risk(
            db=db,
            item_id=item_id,
            location_id=location_id,
        )

        return explain_supply_risk(risk_result)

    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            404,
            "Required AI model has not been trained yet.",
        ) from exc


@router.get("/reliability/{item_id}/{location_id}")
def get_forecast_reliability(
    item_id: UUID,
    location_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return assess_forecast_reliability(
            db=db,
            item_id=item_id,
            location_id=location_id,
        )

    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            404,
            "Forecast model has not been trained yet.",
        ) from exc


@router.get("/what-if/{item_id}/{location_id}")
def get_what_if_analysis(
    item_id: UUID,
    location_id: UUID,
    additional_supply: float = Query(
        default=0.0,
        ge=0.0,
        description="Additional supply to simulate.",
    ),
    db: Session = Depends(get_db),
):
    try:
        return analyze_what_if(
            db=db,
            item_id=item_id,
            location_id=location_id,
            additional_supply=additional_supply,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Required AI model has not been trained yet.",
        ) from exc