from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.item import Item
from app.models.inventory import Inventory
from app.models.location import Location
from app.models.vehicle import Vehicle

from app.api.routes.ai import get_consumption_forecast
from app.api.routes.gis import get_distance_km

from app.optimization.models import (
    OptimizationInput,
    ScenarioInput,
    SupplyDestination,
    VehicleOption,
)

from app.optimization.planner import run_what_if_scenario


router = APIRouter(
    prefix="/api/optimization",
    tags=["Optimization"],
)


# ============================================================================
# REQUEST MODELS
# ============================================================================

class VehicleRequest(BaseModel):
    vehicle_id: str
    vehicle_code: str
    capacity: float
    capacity_unit: str
    status: str
    distance_km: Optional[float] = None
    estimated_travel_hours: Optional[float] = None
    current_location_id: Optional[str] = None
    is_active: bool = True


class DestinationRequest(BaseModel):
    destination_id: str
    destination_code: str
    current_stock: float
    minimum_stock: float
    maximum_stock: Optional[float] = None
    predicted_daily_consumption: float
    days_of_cover: Optional[float] = None
    planning_horizon_days: int = 7
    safety_buffer_days: float = 2.0
    distance_from_source_km: Optional[float] = None
    estimated_travel_hours: Optional[float] = None
    route_risk_level: str = "LOW"
    route_available: bool = True


class WhatIfRequest(BaseModel):
    item_id: str
    item_code: str
    item_name: str
    unit: str

    location_id: str
    location_code: str

    current_stock: float = Field(ge=0)
    minimum_stock: float = Field(ge=0)

    maximum_stock: Optional[float] = Field(
        default=None,
        ge=0,
    )

    predicted_daily_consumption: float = Field(
        ge=0,
    )

    days_of_cover: Optional[float] = Field(
        default=None,
        ge=0,
    )

    planning_horizon_days: int = Field(
        default=7,
        gt=0,
    )

    safety_buffer_days: float = Field(
        default=2.0,
        ge=0,
    )

    vehicles: list[VehicleRequest] = Field(
        default_factory=list,
    )

    destinations: list[DestinationRequest] = Field(
        default_factory=list,
    )

    max_route_distance_km: Optional[float] = Field(
        default=None,
        ge=0,
    )

    max_travel_hours: Optional[float] = Field(
        default=None,
        ge=0,
    )

    blocked_route_risk_levels: list[str] = Field(
        default_factory=list,
    )

    additional_supply: float = 0.0

    demand_change_percent: float = 0.0

    scenario_planning_horizon_days: Optional[int] = Field(
        default=None,
        gt=0,
    )

    scenario_safety_buffer_days: Optional[float] = Field(
        default=None,
        ge=0,
    )

    scenario_vehicle_id: Optional[str] = None

    scenario_route_available: Optional[bool] = None

    scenario_route_risk_level: Optional[str] = None


class OperationalWhatIfRequest(BaseModel):
    item_id: UUID

    location_id: UUID

    additional_supply: float = 0.0

    demand_change_percent: float = 0.0

    planning_horizon_days: Optional[int] = Field(
        default=None,
        gt=0,
    )

    safety_buffer_days: Optional[float] = Field(
        default=None,
        ge=0,
    )

    vehicle_id: Optional[UUID] = None

    destination_location_id: Optional[UUID] = None

    route_available: Optional[bool] = None

    route_risk_level: Optional[str] = None


# ============================================================================
# HELPERS
# ============================================================================

def _build_vehicle(
    vehicle: VehicleRequest,
) -> VehicleOption:

    return VehicleOption(
        vehicle_id=vehicle.vehicle_id,
        vehicle_code=vehicle.vehicle_code,
        capacity=vehicle.capacity,
        capacity_unit=vehicle.capacity_unit,
        status=vehicle.status,
        distance_km=vehicle.distance_km,
        estimated_travel_hours=(
            vehicle.estimated_travel_hours
        ),
        current_location_id=(
            vehicle.current_location_id
        ),
        is_active=vehicle.is_active,
    )


def _build_destination(
    destination: DestinationRequest,
) -> SupplyDestination:

    return SupplyDestination(
        destination_id=destination.destination_id,
        destination_code=destination.destination_code,
        current_stock=destination.current_stock,
        minimum_stock=destination.minimum_stock,
        maximum_stock=destination.maximum_stock,
        predicted_daily_consumption=(
            destination.predicted_daily_consumption
        ),
        days_of_cover=destination.days_of_cover,
        planning_horizon_days=(
            destination.planning_horizon_days
        ),
        safety_buffer_days=(
            destination.safety_buffer_days
        ),
        distance_from_source_km=(
            destination.distance_from_source_km
        ),
        estimated_travel_hours=(
            destination.estimated_travel_hours
        ),
        route_risk_level=(
            destination.route_risk_level
        ),
        route_available=(
            destination.route_available
        ),
    )


def _serialize_result(result):

    return {
        "success": True,
        "scenario": {
            "feasible": result.feasible,

            "baseline_quantity": (
                result.baseline_quantity
            ),

            "scenario_quantity": (
                result.scenario_quantity
            ),

            "baseline_stock": (
                result.baseline_stock
            ),

            "scenario_stock": (
                result.scenario_stock
            ),

            "baseline_days_of_cover": (
                result.baseline_days_of_cover
            ),

            "scenario_days_of_cover": (
                result.scenario_days_of_cover
            ),

            "baseline_risk_level": (
                result.baseline_risk_level
            ),

            "scenario_risk_level": (
                result.scenario_risk_level
            ),

            "decision": result.decision,

            "decision_reason": (
                result.decision_reason
            ),

            "key_changes": result.key_changes,

            "explanation": result.explanation,
        },

        "comparisons": [
            {
                "metric": comparison.metric,

                "baseline_value": (
                    comparison.baseline_value
                ),

                "scenario_value": (
                    comparison.scenario_value
                ),

                "change": comparison.change,

                "change_percent": (
                    comparison.change_percent
                ),
            }

            for comparison in result.comparisons
        ],

        "constraints": [
            {
                "code": constraint.code,

                "passed": constraint.passed,

                "message": constraint.message,
            }

            for constraint in result.constraints
        ],
    }


# ============================================================================
# MANUAL WHAT-IF API
# ============================================================================

@router.post("/what-if")
def what_if_scenario(
    request: WhatIfRequest,
):
    """
    Run a temporary what-if scenario using explicitly
    supplied operational values.

    This does not modify the database.
    """

    try:

        optimization_input = OptimizationInput(
            item_id=request.item_id,

            item_code=request.item_code,

            item_name=request.item_name,

            unit=request.unit,

            location_id=request.location_id,

            location_code=request.location_code,

            current_stock=request.current_stock,

            minimum_stock=request.minimum_stock,

            maximum_stock=request.maximum_stock,

            predicted_daily_consumption=(
                request.predicted_daily_consumption
            ),

            days_of_cover=request.days_of_cover,

            planning_horizon_days=(
                request.planning_horizon_days
            ),

            safety_buffer_days=(
                request.safety_buffer_days
            ),

            vehicles=[
                _build_vehicle(vehicle)
                for vehicle in request.vehicles
            ],

            destinations=[
                _build_destination(destination)
                for destination in request.destinations
            ],

            max_route_distance_km=(
                request.max_route_distance_km
            ),

            max_travel_hours=(
                request.max_travel_hours
            ),

            blocked_route_risk_levels=(
                request.blocked_route_risk_levels
            ),
        )

        scenario = ScenarioInput(
            additional_supply=(
                request.additional_supply
            ),

            demand_change_percent=(
                request.demand_change_percent
            ),

            planning_horizon_days=(
                request.scenario_planning_horizon_days
            ),

            safety_buffer_days=(
                request.scenario_safety_buffer_days
            ),

            vehicle_id=(
                request.scenario_vehicle_id
            ),

            route_available=(
                request.scenario_route_available
            ),

            route_risk_level=(
                request.scenario_route_risk_level
            ),
        )

        result = run_what_if_scenario(
            optimization_input,
            scenario,
        )

        return _serialize_result(result)

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                "What-if scenario processing failed: "
                f"{str(exc)}"
            ),
        ) from exc


# ============================================================================
# AI + GIS + DATABASE WHAT-IF API
# ============================================================================

@router.post("/what-if/operational")
def operational_what_if_scenario(
    request: OperationalWhatIfRequest,
    db: Session = Depends(get_db),
):
    """
    Run a what-if scenario using the actual platform state.

    PostgreSQL:
        -> inventory
        -> item
        -> location
        -> vehicles

    AI:
        -> consumption forecast

    GIS:
        -> route distance
        -> estimated travel time

    Optimization:
        -> scenario simulation
        -> comparison
        -> decision

    The operational database is never modified.
    """

    try:

        # ------------------------------------------------------------------
        # 1. Load item
        # ------------------------------------------------------------------

        item = db.scalar(
            select(Item).where(
                Item.id == request.item_id
            )
        )

        if item is None:

            raise HTTPException(
                status_code=404,
                detail="Item not found.",
            )


        # ------------------------------------------------------------------
        # 2. Load source location
        # ------------------------------------------------------------------

        location = db.scalar(
            select(Location).where(
                Location.id == request.location_id
            )
        )

        if location is None:

            raise HTTPException(
                status_code=404,
                detail="Location not found.",
            )

        if not location.is_active:

            raise HTTPException(
                status_code=400,
                detail="Location is inactive.",
            )


        # ------------------------------------------------------------------
        # 3. Load inventory
        # ------------------------------------------------------------------

        inventory = db.scalar(
            select(Inventory).where(
                Inventory.item_id == request.item_id,

                Inventory.location_id == request.location_id,
            )
        )

        if inventory is None:

            raise HTTPException(
                status_code=404,
                detail="Inventory record not found.",
            )


        # ------------------------------------------------------------------
        # 4. Get AI demand forecast
        # ------------------------------------------------------------------

        forecast = get_consumption_forecast(
            request.item_id,
            request.location_id,
            db,
        )

        predicted_daily_consumption = (
            forecast.get(
                "predicted_daily_consumption"
            )
        )

        if predicted_daily_consumption is None:

            predicted_daily_consumption = (
                forecast.get(
                    "predicted_quantity"
                )
            )

        if predicted_daily_consumption is None:

            predicted_daily_consumption = (
                forecast.get(
                    "forecast"
                )
            )

        if isinstance(
            predicted_daily_consumption,
            dict,
        ):

            predicted_daily_consumption = (
                predicted_daily_consumption.get(
                    "value"
                )
            )

        if predicted_daily_consumption is None:

            raise HTTPException(
                status_code=500,
                detail=(
                    "AI forecast did not return "
                    "a daily consumption value."
                ),
            )

        predicted_daily_consumption = float(
            predicted_daily_consumption
        )


        # ------------------------------------------------------------------
        # 5. Load active vehicles
        # ------------------------------------------------------------------

        vehicles = db.scalars(
            select(Vehicle).where(
                Vehicle.is_active.is_(True)
            )
        ).all()

        vehicle_options = []

        for vehicle in vehicles:

            distance_km = None

            estimated_travel_hours = None

            if request.destination_location_id:

                distance_km = get_distance_km(
                    db,
                    request.location_id,
                    request.destination_location_id,
                )

                if distance_km is not None:

                    estimated_travel_hours = (
                        distance_km / 40.0
                    )

            vehicle_options.append(
                VehicleOption(
                    vehicle_id=str(
                        vehicle.id
                    ),

                    vehicle_code=(
                        vehicle.vehicle_code
                    ),

                    capacity=float(
                        vehicle.capacity
                    ),

                    capacity_unit=(
                        vehicle.capacity_unit
                    ),

                    status=vehicle.status,

                    distance_km=distance_km,

                    estimated_travel_hours=(
                        estimated_travel_hours
                    ),

                    current_location_id=(
                        str(
                            vehicle.current_location_id
                        )
                        if vehicle.current_location_id
                        else None
                    ),

                    is_active=(
                        vehicle.is_active
                    ),
                )
            )


        # ------------------------------------------------------------------
        # 6. Build GIS destination context
        #
        # IMPORTANT:
        # The destination is used ONLY for GIS / route context here.
        #
        # We do NOT pass it into OptimizationInput.destinations.
        # Otherwise the planner switches into multi-location allocation
        # mode and the baseline resupply calculation becomes incorrect.
        # ------------------------------------------------------------------

        destinations = []

        if request.destination_location_id:

            destination = db.scalar(
                select(Location).where(
                    Location.id
                    == request.destination_location_id
                )
            )

            if destination is None:

                raise HTTPException(
                    status_code=404,
                    detail=(
                        "Destination location not found."
                    ),
                )

            if not destination.is_active:

                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Destination location is inactive."
                    ),
                )

            distance_km = get_distance_km(
                db,
                request.location_id,
                request.destination_location_id,
            )

            estimated_travel_hours = None

            if distance_km is not None:

                estimated_travel_hours = (
                    distance_km / 40.0
                )

            destination_inventory = db.scalar(
                select(Inventory).where(
                    Inventory.item_id
                    == request.item_id,

                    Inventory.location_id
                    == request.destination_location_id,
                )
            )

            if destination_inventory:

                destination_stock = float(
                    destination_inventory.quantity
                )

                destination_minimum = float(
                    destination_inventory.minimum_stock
                )

                destination_maximum = (
                    float(
                        destination_inventory.maximum_stock
                    )
                    if (
                        destination_inventory.maximum_stock
                        is not None
                    )
                    else None
                )

            else:

                destination_stock = 0.0

                destination_minimum = 0.0

                destination_maximum = None

            destinations.append(
                SupplyDestination(
                    destination_id=str(
                        destination.id
                    ),

                    destination_code=(
                        destination.code
                    ),

                    current_stock=(
                        destination_stock
                    ),

                    minimum_stock=(
                        destination_minimum
                    ),

                    maximum_stock=(
                        destination_maximum
                    ),

                    predicted_daily_consumption=(
                        predicted_daily_consumption
                    ),

                    days_of_cover=None,

                    planning_horizon_days=(
                        request.planning_horizon_days
                        or 7
                    ),

                    safety_buffer_days=(
                        request.safety_buffer_days
                        if (
                            request.safety_buffer_days
                            is not None
                        )
                        else 2.0
                    ),

                    distance_from_source_km=(
                        distance_km
                    ),

                    estimated_travel_hours=(
                        estimated_travel_hours
                    ),

                    route_risk_level=(
                        request.route_risk_level
                        or "LOW"
                    ),

                    route_available=(
                        request.route_available
                        if (
                            request.route_available
                            is not None
                        )
                        else True
                    ),
                )
            )


        # ------------------------------------------------------------------
        # 7. Build canonical optimization input
        #
        # IMPORTANT:
        # destinations=[] keeps this as a SOURCE resupply problem.
        # GIS destination information remains available separately.
        # ------------------------------------------------------------------

        optimization_input = OptimizationInput(
            item_id=str(item.id),

            item_code=item.item_code,

            item_name=item.name,

            unit=item.unit,

            location_id=str(location.id),

            location_code=location.code,

            current_stock=float(
                inventory.quantity
            ),

            minimum_stock=float(
                inventory.minimum_stock
            ),

            maximum_stock=(
                float(
                    inventory.maximum_stock
                )
                if (
                    inventory.maximum_stock
                    is not None
                )
                else None
            ),

            predicted_daily_consumption=(
                predicted_daily_consumption
            ),

            days_of_cover=(
                (
                    float(inventory.quantity)
                    / predicted_daily_consumption
                )
                if predicted_daily_consumption > 0
                else None
            ),

            planning_horizon_days=(
                request.planning_horizon_days
                or 7
            ),

            safety_buffer_days=(
                request.safety_buffer_days
                if (
                    request.safety_buffer_days
                    is not None
                )
                else 2.0
            ),

            vehicles=vehicle_options,

            # DO NOT pass GIS destination here.
            destinations=[],
        )


        # ------------------------------------------------------------------
        # 8. Build scenario
        # ------------------------------------------------------------------

        scenario = ScenarioInput(
            additional_supply=(
                request.additional_supply
            ),

            demand_change_percent=(
                request.demand_change_percent
            ),

            planning_horizon_days=(
                request.planning_horizon_days
            ),

            safety_buffer_days=(
                request.safety_buffer_days
            ),

            vehicle_id=(
                str(request.vehicle_id)
                if request.vehicle_id
                else None
            ),

            route_available=(
                request.route_available
            ),

            route_risk_level=(
                request.route_risk_level
            ),
        )


        # ------------------------------------------------------------------
        # 9. Run simulation
        # ------------------------------------------------------------------

        result = run_what_if_scenario(
            optimization_input,
            scenario,
        )

        response = _serialize_result(
            result
        )


        # ------------------------------------------------------------------
        # 10. Add operational context
        # ------------------------------------------------------------------

        response["operational_context"] = {

            "item": {
                "id": str(item.id),

                "code": item.item_code,

                "name": item.name,

                "unit": item.unit,
            },

            "location": {
                "id": str(location.id),

                "code": location.code,

                "name": location.name,
            },

            "inventory": {
                "current_stock": float(
                    inventory.quantity
                ),

                "minimum_stock": float(
                    inventory.minimum_stock
                ),

                "maximum_stock": (
                    float(
                        inventory.maximum_stock
                    )
                    if (
                        inventory.maximum_stock
                        is not None
                    )
                    else None
                ),
            },

            "ai": {
                "forecast": forecast,

                "predicted_daily_consumption": (
                    predicted_daily_consumption
                ),
            },

            "gis": {
                "destination_location_id": (
                    str(
                        request.destination_location_id
                    )
                    if request.destination_location_id
                    else None
                ),

                "route_distance_km": (
                    destinations[0].distance_from_source_km
                    if destinations
                    else None
                ),

                "estimated_travel_hours": (
                    destinations[0].estimated_travel_hours
                    if destinations
                    else None
                ),

                "route_risk_level": (
                    destinations[0].route_risk_level
                    if destinations
                    else None
                ),

                "route_available": (
                    destinations[0].route_available
                    if destinations
                    else None
                ),
            },
        }


        return response


    except HTTPException:

        raise


    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                "Operational what-if scenario "
                "processing failed: "
                f"{str(exc)}"
            ),
        ) from exc