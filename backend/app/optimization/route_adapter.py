from __future__ import annotations

from typing import Any, Optional

from app.optimization.models import SupplyDestination


def build_destination_from_gis_route(
    destination_id: str,
    destination_code: str,
    current_stock: float,
    minimum_stock: float,
    maximum_stock: Optional[float],
    predicted_daily_consumption: float,
    days_of_cover: Optional[float],
    route_result: dict[str, Any],
    planning_horizon_days: int = 7,
    safety_buffer_days: float = 2.0,
) -> SupplyDestination:
    """
    Convert a GIS route response into the optimization
    destination model.

    The optimizer therefore consumes a normalized route
    representation rather than depending directly on the
    GIS implementation.
    """

    distance_km = route_result.get("distance_km")

    estimated_travel_hours = route_result.get(
        "estimated_travel_hours"
    )

    route_risk_level = (
        route_result.get("risk_level")
        or route_result.get("route_risk_level")
        or "LOW"
    )

    route_available = route_result.get(
        "route_available",
        True,
    )

    status = str(
        route_result.get("status", "")
    ).upper()

    if status in {
        "BLOCKED",
        "UNAVAILABLE",
        "INACTIVE",
    }:
        route_available = False

    return SupplyDestination(
        destination_id=destination_id,
        destination_code=destination_code,
        current_stock=current_stock,
        minimum_stock=minimum_stock,
        maximum_stock=maximum_stock,
        predicted_daily_consumption=(
            predicted_daily_consumption
        ),
        days_of_cover=days_of_cover,
        planning_horizon_days=planning_horizon_days,
        safety_buffer_days=safety_buffer_days,
        distance_from_source_km=distance_km,
        estimated_travel_hours=estimated_travel_hours,
        route_risk_level=str(route_risk_level).upper(),
        route_available=bool(route_available),
    )