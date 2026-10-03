from __future__ import annotations

from typing import Optional

from app.optimization.models import (
    AllocationResult,
    OptimizationConstraint,
    OptimizationInput,
    OptimizationResult,
    RouteConstraint,
    ScenarioComparison,
    ScenarioInput,
    ScenarioResult,
    SupplyDestination,
    VehicleOption,
)


def calculate_destination_need(
    destination: SupplyDestination,
) -> float:
    expected_consumption = (
        destination.predicted_daily_consumption
        * destination.planning_horizon_days
    )

    safety_buffer = (
        destination.predicted_daily_consumption
        * destination.safety_buffer_days
    )

    demand_based_target = (
        destination.minimum_stock
        + expected_consumption
        + safety_buffer
    )

    if destination.maximum_stock is not None:
        target_stock = min(
            destination.maximum_stock,
            demand_based_target,
        )
    else:
        target_stock = demand_based_target

    return max(
        0.0,
        target_stock - destination.current_stock,
    )


def calculate_recommended_quantity(
    current_stock: float,
    minimum_stock: float,
    maximum_stock: Optional[float],
    predicted_daily_consumption: float,
    planning_horizon_days: int = 7,
    safety_buffer_days: float = 2.0,
) -> tuple[float, float, float, float]:

    if planning_horizon_days <= 0:
        raise ValueError(
            "Planning horizon must be greater than zero."
        )

    if safety_buffer_days < 0:
        raise ValueError(
            "Safety buffer cannot be negative."
        )

    if current_stock < 0:
        raise ValueError(
            "Current stock cannot be negative."
        )

    if minimum_stock < 0:
        raise ValueError(
            "Minimum stock cannot be negative."
        )

    if predicted_daily_consumption < 0:
        raise ValueError(
            "Predicted consumption cannot be negative."
        )

    expected_consumption = (
        predicted_daily_consumption
        * planning_horizon_days
    )

    safety_buffer_quantity = (
        predicted_daily_consumption
        * safety_buffer_days
    )

    demand_based_target = (
        minimum_stock
        + expected_consumption
        + safety_buffer_quantity
    )

    if maximum_stock is not None:
        target_stock = min(
            maximum_stock,
            demand_based_target,
        )
    else:
        target_stock = demand_based_target

    recommended_quantity = max(
        0.0,
        target_stock - current_stock,
    )

    return (
        recommended_quantity,
        expected_consumption,
        safety_buffer_quantity,
        target_stock,
    )


def select_vehicle(
    vehicles: list[VehicleOption],
    recommended_quantity: float,
) -> Optional[VehicleOption]:

    eligible = [
        vehicle
        for vehicle in vehicles
        if vehicle.is_active
        and vehicle.status.upper() == "AVAILABLE"
        and vehicle.capacity >= recommended_quantity
    ]

    if not eligible:
        return None

    eligible.sort(
        key=lambda vehicle: (
            vehicle.distance_km
            if vehicle.distance_km is not None
            else float("inf"),
            vehicle.estimated_travel_hours
            if vehicle.estimated_travel_hours is not None
            else float("inf"),
            vehicle.capacity,
        )
    )

    return eligible[0]


def evaluate_route_constraints(
    destination: SupplyDestination,
    max_route_distance_km: Optional[float] = None,
    max_travel_hours: Optional[float] = None,
    blocked_route_risk_levels: Optional[list[str]] = None,
) -> list[RouteConstraint]:

    constraints: list[RouteConstraint] = []

    blocked_risks = {
        value.upper()
        for value in (blocked_route_risk_levels or [])
    }

    if not destination.route_available:
        constraints.append(
            RouteConstraint(
                code="ROUTE_UNAVAILABLE",
                passed=False,
                message=(
                    f"Route to {destination.destination_code} "
                    "is unavailable."
                ),
                severity="HIGH",
            )
        )
    else:
        constraints.append(
            RouteConstraint(
                code="ROUTE_AVAILABLE",
                passed=True,
                message=(
                    f"Route to {destination.destination_code} "
                    "is available."
                ),
                severity="INFO",
            )
        )

    if (
        max_route_distance_km is not None
        and destination.distance_from_source_km is not None
    ):
        passed = (
            destination.distance_from_source_km
            <= max_route_distance_km
        )

        constraints.append(
            RouteConstraint(
                code="MAX_ROUTE_DISTANCE",
                passed=passed,
                message=(
                    f"Route distance "
                    f"{destination.distance_from_source_km:.2f} km "
                    f"must be <= "
                    f"{max_route_distance_km:.2f} km."
                ),
                severity="HIGH" if not passed else "INFO",
            )
        )

    if (
        max_travel_hours is not None
        and destination.estimated_travel_hours is not None
    ):
        passed = (
            destination.estimated_travel_hours
            <= max_travel_hours
        )

        constraints.append(
            RouteConstraint(
                code="MAX_TRAVEL_TIME",
                passed=passed,
                message=(
                    f"Estimated travel time "
                    f"{destination.estimated_travel_hours:.2f} h "
                    f"must be <= "
                    f"{max_travel_hours:.2f} h."
                ),
                severity="HIGH" if not passed else "INFO",
            )
        )

    if blocked_risks:
        risk = destination.route_risk_level.upper()
        passed = risk not in blocked_risks

        constraints.append(
            RouteConstraint(
                code="ROUTE_RISK",
                passed=passed,
                message=(
                    f"Route risk level {risk} "
                    f"is {'allowed' if passed else 'blocked'}."
                ),
                severity="HIGH" if not passed else "INFO",
            )
        )

    return constraints


def is_route_feasible(
    destination: SupplyDestination,
    max_route_distance_km: Optional[float] = None,
    max_travel_hours: Optional[float] = None,
    blocked_route_risk_levels: Optional[list[str]] = None,
) -> bool:

    constraints = evaluate_route_constraints(
        destination=destination,
        max_route_distance_km=max_route_distance_km,
        max_travel_hours=max_travel_hours,
        blocked_route_risk_levels=blocked_route_risk_levels,
    )

    return all(
        constraint.passed
        for constraint in constraints
    )


def allocate_supply(
    available_supply: float,
    destinations: list[SupplyDestination],
    max_route_distance_km: Optional[float] = None,
    max_travel_hours: Optional[float] = None,
    blocked_route_risk_levels: Optional[list[str]] = None,
) -> list[AllocationResult]:

    if available_supply < 0:
        raise ValueError(
            "Available supply cannot be negative."
        )

    destination_needs = []

    for index, destination in enumerate(destinations):

        requested_quantity = calculate_destination_need(
            destination
        )

        route_constraints = evaluate_route_constraints(
            destination=destination,
            max_route_distance_km=max_route_distance_km,
            max_travel_hours=max_travel_hours,
            blocked_route_risk_levels=blocked_route_risk_levels,
        )

        route_feasible = all(
            constraint.passed
            for constraint in route_constraints
        )

        destination_needs.append(
            (
                index,
                destination,
                requested_quantity,
                route_feasible,
            )
        )

    destination_needs.sort(
        key=lambda entry: (
            -entry[2],
            entry[0],
        )
    )

    remaining_supply = available_supply
    results: list[AllocationResult] = []

    for (
        _,
        destination,
        requested_quantity,
        route_feasible,
    ) in destination_needs:

        if not route_feasible:
            allocated_quantity = 0.0
        else:
            allocated_quantity = min(
                requested_quantity,
                remaining_supply,
            )

        remaining_need = max(
            0.0,
            requested_quantity - allocated_quantity,
        )

        if route_feasible and allocated_quantity > 0:
            remaining_supply -= allocated_quantity

        feasible = (
            route_feasible
            and remaining_need <= 0.000001
        )

        if not route_feasible:
            explanation = (
                "Destination could not receive supply "
                "because route constraints were not satisfied."
            )
        elif feasible:
            explanation = (
                "Destination demand can be fully satisfied "
                "within the available supply."
            )
        else:
            explanation = (
                "Destination route is feasible, but available "
                "supply is insufficient to satisfy the full need."
            )

        results.append(
            AllocationResult(
                destination_id=destination.destination_id,
                destination_code=destination.destination_code,
                requested_quantity=requested_quantity,
                allocated_quantity=allocated_quantity,
                remaining_need=remaining_need,
                feasible=feasible,
                explanation=explanation,
                route_distance_km=(
                    destination.distance_from_source_km
                ),
                estimated_travel_hours=(
                    destination.estimated_travel_hours
                ),
                route_risk_level=(
                    destination.route_risk_level
                ),
            )
        )

    results.sort(
        key=lambda result: next(
            (
                index
                for index, destination in enumerate(
                    destinations
                )
                if destination.destination_id
                == result.destination_id
            ),
            0,
        )
    )

    return results


def select_route_compatible_vehicle(
    vehicles: list[VehicleOption],
    recommended_quantity: float,
    destination: SupplyDestination,
) -> Optional[VehicleOption]:

    eligible = []

    for vehicle in vehicles:

        if not vehicle.is_active:
            continue

        if vehicle.status.upper() != "AVAILABLE":
            continue

        if vehicle.capacity < recommended_quantity:
            continue

        if (
            destination.distance_from_source_km is not None
            and vehicle.distance_km is not None
            and vehicle.distance_km
            > destination.distance_from_source_km
        ):
            continue

        if (
            destination.estimated_travel_hours is not None
            and vehicle.estimated_travel_hours is not None
            and vehicle.estimated_travel_hours
            > destination.estimated_travel_hours
        ):
            continue

        eligible.append(vehicle)

    if not eligible:
        return None

    eligible.sort(
        key=lambda vehicle: (
            vehicle.distance_km
            if vehicle.distance_km is not None
            else float("inf"),
            vehicle.estimated_travel_hours
            if vehicle.estimated_travel_hours is not None
            else float("inf"),
            vehicle.capacity,
        )
    )

    return eligible[0]


def build_optimization_plan(
    optimization_input: OptimizationInput,
) -> OptimizationResult:

    (
        recommended_quantity,
        expected_consumption,
        safety_buffer_quantity,
        target_stock,
    ) = calculate_recommended_quantity(
        current_stock=optimization_input.current_stock,
        minimum_stock=optimization_input.minimum_stock,
        maximum_stock=optimization_input.maximum_stock,
        predicted_daily_consumption=(
            optimization_input.predicted_daily_consumption
        ),
        planning_horizon_days=(
            optimization_input.planning_horizon_days
        ),
        safety_buffer_days=(
            optimization_input.safety_buffer_days
        ),
    )

    constraints: list[OptimizationConstraint] = [
        OptimizationConstraint(
            code="DEMAND_FORECAST",
            passed=(
                optimization_input.predicted_daily_consumption
                >= 0
            ),
            message=(
                "Demand forecast is available for planning."
            ),
        ),
        OptimizationConstraint(
            code="SAFETY_BUFFER",
            passed=(
                optimization_input.safety_buffer_days
                >= 0
            ),
            message="Safety buffer is valid.",
        ),
        OptimizationConstraint(
            code="STOCK_TARGET",
            passed=True,
            message=(
                f"Target stock calculated at "
                f"{target_stock:.2f} "
                f"{optimization_input.unit}."
            ),
        ),
    ]

    allocations: list[AllocationResult] = []

    if optimization_input.destinations:

        allocations = allocate_supply(
            available_supply=(
                optimization_input.current_stock
            ),
            destinations=optimization_input.destinations,
            max_route_distance_km=(
                optimization_input.max_route_distance_km
            ),
            max_travel_hours=(
                optimization_input.max_travel_hours
            ),
            blocked_route_risk_levels=(
                optimization_input.blocked_route_risk_levels
            ),
        )

        total_allocated = sum(
            allocation.allocated_quantity
            for allocation in allocations
        )

        total_requested = sum(
            allocation.requested_quantity
            for allocation in allocations
        )

        feasible_allocations = [
            allocation
            for allocation in allocations
            if allocation.allocated_quantity > 0
        ]

        selected_vehicle = None

        if feasible_allocations:

            first_allocation = feasible_allocations[0]

            destination = next(
                (
                    destination
                    for destination
                    in optimization_input.destinations
                    if destination.destination_id
                    == first_allocation.destination_id
                ),
                None,
            )

            if destination is not None:
                selected_vehicle = (
                    select_route_compatible_vehicle(
                        vehicles=optimization_input.vehicles,
                        recommended_quantity=total_allocated,
                        destination=destination,
                    )
                )

        vehicle_passed = (
            total_allocated <= 0
            or selected_vehicle is not None
        )

        constraints.append(
            OptimizationConstraint(
                code="VEHICLE_ALLOCATION",
                passed=vehicle_passed,
                message=(
                    "A compatible vehicle is available."
                    if vehicle_passed
                    else
                    "No compatible vehicle can transport "
                    "the allocated supply."
                ),
            )
        )

        route_constraints: list[RouteConstraint] = []

        for destination in optimization_input.destinations:
            route_constraints.extend(
                evaluate_route_constraints(
                    destination=destination,
                    max_route_distance_km=(
                        optimization_input.max_route_distance_km
                    ),
                    max_travel_hours=(
                        optimization_input.max_travel_hours
                    ),
                    blocked_route_risk_levels=(
                        optimization_input.blocked_route_risk_levels
                    ),
                )
            )

        if selected_vehicle is not None:
            constraints.append(
                OptimizationConstraint(
                    code="VEHICLE_ROUTE_COMPATIBILITY",
                    passed=True,
                    message=(
                        f"Selected vehicle "
                        f"{selected_vehicle.vehicle_code} "
                        "is compatible with the route."
                    ),
                )
            )
        else:
            route_blocked = any(
                not route_constraint.passed
                for route_constraint in route_constraints
            )

            constraints.append(
                OptimizationConstraint(
                    code="VEHICLE_ROUTE_COMPATIBILITY",
                    passed=(
                        total_allocated <= 0
                        and not route_blocked
                    ),
                    message=(
                        "No route-compatible vehicle was required."
                        if total_allocated <= 0
                        and not route_blocked
                        else
                        "No route-compatible vehicle is available "
                        "because route constraints are not satisfied."
                    ),
                )
            )

        feasible = (
            total_allocated > 0
            and total_allocated
            <= optimization_input.current_stock
            and vehicle_passed
            and all(
                allocation.feasible
                for allocation in allocations
                if allocation.allocated_quantity > 0
            )
        )

        explanation = (
            f"Allocated {total_allocated:.2f} "
            f"of {total_requested:.2f} requested units "
            f"across {len(allocations)} destinations."
        )

        return OptimizationResult(
            feasible=feasible,
            recommended_quantity=total_allocated,
            selected_vehicle_id=(
                selected_vehicle.vehicle_id
                if selected_vehicle
                else None
            ),
            selected_vehicle_code=(
                selected_vehicle.vehicle_code
                if selected_vehicle
                else None
            ),
            planning_horizon_days=(
                optimization_input.planning_horizon_days
            ),
            expected_consumption=expected_consumption,
            safety_buffer_quantity=safety_buffer_quantity,
            target_stock=target_stock,
            selected_vehicle_capacity=(
                selected_vehicle.capacity
                if selected_vehicle
                else None
            ),
            selected_vehicle_capacity_unit=(
                selected_vehicle.capacity_unit
                if selected_vehicle
                else None
            ),
            selected_vehicle_distance_km=(
                selected_vehicle.distance_km
                if selected_vehicle
                else None
            ),
            selected_vehicle_travel_hours=(
                selected_vehicle.estimated_travel_hours
                if selected_vehicle
                else None
            ),
            allocations=allocations,
            route_constraints=route_constraints,
            constraints=constraints,
            explanation=explanation,
        )

    selected_vehicle = select_vehicle(
        vehicles=optimization_input.vehicles,
        recommended_quantity=recommended_quantity,
    )

    vehicle_capacity_passed = (
        recommended_quantity <= 0
        or selected_vehicle is not None
    )

    constraints.append(
        OptimizationConstraint(
            code="VEHICLE_ALLOCATION",
            passed=vehicle_capacity_passed,
            message=(
                "A suitable vehicle is available."
                if vehicle_capacity_passed
                else
                "No available vehicle has sufficient capacity."
            ),
        )
    )

    if recommended_quantity > 0:
        constraints.append(
            OptimizationConstraint(
                code="VEHICLE_CAPACITY",
                passed=selected_vehicle is not None,
                message=(
                    "Selected vehicle capacity is sufficient."
                    if selected_vehicle
                    else
                    "Vehicle capacity is insufficient."
                ),
            )
        )

    if selected_vehicle is not None:

        constraints.append(
            OptimizationConstraint(
                code="ROUTE_DISTANCE",
                passed=True,
                message=(
                    "Vehicle route distance is available."
                    if selected_vehicle.distance_km
                    is not None
                    else
                    "Route distance was not provided."
                ),
            )
        )

        constraints.append(
            OptimizationConstraint(
                code="TRAVEL_TIME",
                passed=True,
                message=(
                    "Vehicle travel time is available."
                    if selected_vehicle.estimated_travel_hours
                    is not None
                    else
                    "Travel time was not provided."
                ),
            )
        )

    feasible = (
        recommended_quantity <= 0
        or selected_vehicle is not None
    )

    if recommended_quantity <= 0:
        explanation = (
            "Current stock is sufficient for the "
            "planning horizon."
        )
    elif selected_vehicle is not None:
        explanation = (
            f"Recommend {recommended_quantity:.2f} "
            f"{optimization_input.unit} of "
            f"{optimization_input.item_name}."
        )
    else:
        explanation = (
            f"Recommend {recommended_quantity:.2f} "
            f"{optimization_input.unit}, but no suitable "
            "vehicle is currently available."
        )

    return OptimizationResult(
        feasible=feasible,
        recommended_quantity=recommended_quantity,
        selected_vehicle_id=(
            selected_vehicle.vehicle_id
            if selected_vehicle
            else None
        ),
        selected_vehicle_code=(
            selected_vehicle.vehicle_code
            if selected_vehicle
            else None
        ),
        planning_horizon_days=(
            optimization_input.planning_horizon_days
        ),
        expected_consumption=expected_consumption,
        safety_buffer_quantity=safety_buffer_quantity,
        target_stock=target_stock,
        selected_vehicle_capacity=(
            selected_vehicle.capacity
            if selected_vehicle
            else None
        ),
        selected_vehicle_capacity_unit=(
            selected_vehicle.capacity_unit
            if selected_vehicle
            else None
        ),
        selected_vehicle_distance_km=(
            selected_vehicle.distance_km
            if selected_vehicle
            else None
        ),
        selected_vehicle_travel_hours=(
            selected_vehicle.estimated_travel_hours
            if selected_vehicle
            else None
        ),
        allocations=[],
        route_constraints=[],
        constraints=constraints,
        explanation=explanation,
    )


def _calculate_days_of_cover(
    stock: float,
    predicted_daily_consumption: float,
) -> Optional[float]:

    if predicted_daily_consumption <= 0:
        return None

    return stock / predicted_daily_consumption


def _determine_scenario_risk(
    stock: float,
    minimum_stock: float,
    predicted_daily_consumption: float,
) -> str:

    if stock <= 0:
        return "CRITICAL"

    if stock < minimum_stock:
        return "HIGH"

    days_of_cover = _calculate_days_of_cover(
        stock=stock,
        predicted_daily_consumption=(
            predicted_daily_consumption
        ),
    )

    if days_of_cover is not None:

        if days_of_cover < 3:
            return "HIGH"

        if days_of_cover < 7:
            return "MEDIUM"

    return "LOW"


def _calculate_change_percent(
    baseline: float,
    scenario: float,
) -> Optional[float]:

    if baseline == 0:
        return None

    return (
        (scenario - baseline)
        / abs(baseline)
    ) * 100.0


def _build_comparison(
    metric: str,
    baseline_value: float,
    scenario_value: float,
) -> ScenarioComparison:

    change = scenario_value - baseline_value

    return ScenarioComparison(
        metric=metric,
        baseline_value=baseline_value,
        scenario_value=scenario_value,
        change=change,
        change_percent=_calculate_change_percent(
            baseline=baseline_value,
            scenario=scenario_value,
        ),
    )


def run_what_if_scenario(
    optimization_input: OptimizationInput,
    scenario: ScenarioInput,
) -> ScenarioResult:

    baseline_result = build_optimization_plan(
        optimization_input
    )

    baseline_daily_consumption = (
        optimization_input.predicted_daily_consumption
    )

    baseline_stock = (
        optimization_input.current_stock
    )

    baseline_days_of_cover = _calculate_days_of_cover(
        stock=baseline_stock,
        predicted_daily_consumption=(
            baseline_daily_consumption
        ),
    )

    baseline_risk_level = _determine_scenario_risk(
        stock=baseline_stock,
        minimum_stock=optimization_input.minimum_stock,
        predicted_daily_consumption=(
            baseline_daily_consumption
        ),
    )

    demand_multiplier = (
        1.0
        + (
            scenario.demand_change_percent
            / 100.0
        )
    )

    if demand_multiplier < 0:
        demand_multiplier = 0.0

    scenario_daily_consumption = (
        baseline_daily_consumption
        * demand_multiplier
    )

    scenario_stock = (
        baseline_stock
        + scenario.additional_supply
    )

    scenario_horizon = (
        scenario.planning_horizon_days
        if scenario.planning_horizon_days is not None
        else optimization_input.planning_horizon_days
    )

    scenario_buffer_days = (
        scenario.safety_buffer_days
        if scenario.safety_buffer_days is not None
        else optimization_input.safety_buffer_days
    )

    scenario_destinations: list[
        SupplyDestination
    ] = []

    for destination in optimization_input.destinations:

        destination_copy = SupplyDestination(
            destination_id=destination.destination_id,
            destination_code=destination.destination_code,
            current_stock=destination.current_stock,
            minimum_stock=destination.minimum_stock,
            maximum_stock=destination.maximum_stock,
            predicted_daily_consumption=(
                destination.predicted_daily_consumption
                * demand_multiplier
            ),
            days_of_cover=destination.days_of_cover,
            planning_horizon_days=scenario_horizon,
            safety_buffer_days=scenario_buffer_days,
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

        if scenario.route_available is not None:
            destination_copy.route_available = (
                scenario.route_available
            )

        if scenario.route_risk_level is not None:
            destination_copy.route_risk_level = (
                scenario.route_risk_level.upper()
            )

        scenario_destinations.append(
            destination_copy
        )

    # Single-destination scenario route simulation
    if (
        not scenario_destinations
        and (
            scenario.route_available is not None
            or scenario.route_risk_level is not None
        )
    ):

        temporary_destination = SupplyDestination(
            destination_id=(
                f"{optimization_input.location_id}-SCENARIO"
            ),
            destination_code=(
                f"{optimization_input.location_code}-SCENARIO"
            ),
            current_stock=optimization_input.current_stock,
            minimum_stock=optimization_input.minimum_stock,
            maximum_stock=optimization_input.maximum_stock,
            predicted_daily_consumption=(
                scenario_daily_consumption
            ),
            days_of_cover=optimization_input.days_of_cover,
            planning_horizon_days=scenario_horizon,
            safety_buffer_days=scenario_buffer_days,
            distance_from_source_km=(
                optimization_input.vehicles[0].distance_km
                if optimization_input.vehicles
                and optimization_input.vehicles[0].distance_km
                is not None
                else None
            ),
            estimated_travel_hours=(
                optimization_input.vehicles[0]
                .estimated_travel_hours
                if optimization_input.vehicles
                and optimization_input.vehicles[0]
                .estimated_travel_hours is not None
                else None
            ),
            route_risk_level=(
                scenario.route_risk_level.upper()
                if scenario.route_risk_level is not None
                else "LOW"
            ),
            route_available=(
                scenario.route_available
                if scenario.route_available is not None
                else True
            ),
        )

        scenario_destinations.append(
            temporary_destination
        )

    scenario_vehicles: list[VehicleOption] = []

    for vehicle in optimization_input.vehicles:

        vehicle_copy = VehicleOption(
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

        if scenario.vehicle_id is not None:

            if vehicle_copy.vehicle_id == scenario.vehicle_id:
                vehicle_copy.status = "AVAILABLE"
            else:
                vehicle_copy.status = "INACTIVE"

        scenario_vehicles.append(
            vehicle_copy
        )

    scenario_input = OptimizationInput(
        item_id=optimization_input.item_id,
        item_code=optimization_input.item_code,
        item_name=optimization_input.item_name,
        unit=optimization_input.unit,
        location_id=optimization_input.location_id,
        location_code=optimization_input.location_code,
        current_stock=scenario_stock,
        minimum_stock=optimization_input.minimum_stock,
        maximum_stock=optimization_input.maximum_stock,
        predicted_daily_consumption=(
            scenario_daily_consumption
        ),
        days_of_cover=optimization_input.days_of_cover,
        planning_horizon_days=scenario_horizon,
        safety_buffer_days=scenario_buffer_days,
        vehicles=scenario_vehicles,
        destinations=scenario_destinations,
        max_route_distance_km=(
            optimization_input.max_route_distance_km
        ),
        max_travel_hours=(
            optimization_input.max_travel_hours
        ),
        blocked_route_risk_levels=(
            optimization_input.blocked_route_risk_levels.copy()
        ),
    )

    scenario_result = build_optimization_plan(
        scenario_input
    )

    scenario_days_of_cover = _calculate_days_of_cover(
        stock=scenario_stock,
        predicted_daily_consumption=(
            scenario_daily_consumption
        ),
    )

    scenario_risk_level = _determine_scenario_risk(
        stock=scenario_stock,
        minimum_stock=optimization_input.minimum_stock,
        predicted_daily_consumption=(
            scenario_daily_consumption
        ),
    )

    comparisons = [
        _build_comparison(
            metric="recommended_quantity",
            baseline_value=(
                baseline_result.recommended_quantity
            ),
            scenario_value=(
                scenario_result.recommended_quantity
            ),
        ),
        _build_comparison(
            metric="stock",
            baseline_value=baseline_stock,
            scenario_value=scenario_stock,
        ),
        _build_comparison(
            metric="daily_consumption",
            baseline_value=(
                baseline_daily_consumption
            ),
            scenario_value=(
                scenario_daily_consumption
            ),
        ),
    ]

    if (
        baseline_days_of_cover is not None
        and scenario_days_of_cover is not None
    ):
        comparisons.append(
            _build_comparison(
                metric="days_of_cover",
                baseline_value=(
                    baseline_days_of_cover
                ),
                scenario_value=(
                    scenario_days_of_cover
                ),
            )
        )

    explanation_parts = []

    if scenario.additional_supply != 0:
        explanation_parts.append(
            f"Additional supply changes stock by "
            f"{scenario.additional_supply:.2f}."
        )

    if scenario.demand_change_percent != 0:
        explanation_parts.append(
            f"Demand was adjusted by "
            f"{scenario.demand_change_percent:+.1f}%."
        )

    if scenario.vehicle_id is not None:
        explanation_parts.append(
            f"Vehicle scenario selected "
            f"{scenario.vehicle_id}."
        )

    if scenario.route_available is not None:
        explanation_parts.append(
            "Route availability was changed for the scenario."
        )

    if scenario.route_risk_level is not None:
        explanation_parts.append(
            f"Route risk was changed to "
            f"{scenario.route_risk_level.upper()}."
        )

    if not explanation_parts:
        explanation_parts.append(
            "No scenario changes were applied."
        )

    explanation_parts.append(
        f"Baseline risk was {baseline_risk_level}; "
        f"scenario risk is {scenario_risk_level}."
    )

    explanation_parts.append(
        f"Baseline recommendation was "
        f"{baseline_result.recommended_quantity:.2f}; "
        f"scenario recommendation is "
        f"{scenario_result.recommended_quantity:.2f}."
    )

    key_changes: list[str] = []

    if scenario_stock > baseline_stock:
        key_changes.append(
            f"Stock increases by {scenario_stock - baseline_stock:.2f}."
        )
    elif scenario_stock < baseline_stock:
        key_changes.append(
            f"Stock decreases by {baseline_stock - scenario_stock:.2f}."
        )

    if scenario_daily_consumption > baseline_daily_consumption:
        key_changes.append(
            f"Daily demand increases by {scenario_daily_consumption - baseline_daily_consumption:.2f}."
        )
    elif scenario_daily_consumption < baseline_daily_consumption:
        key_changes.append(
            f"Daily demand decreases by {baseline_daily_consumption - scenario_daily_consumption:.2f}."
        )

    if scenario_result.recommended_quantity > baseline_result.recommended_quantity:
        key_changes.append(
            f"Recommended resupply increases by {scenario_result.recommended_quantity - baseline_result.recommended_quantity:.2f}."
        )
    elif scenario_result.recommended_quantity < baseline_result.recommended_quantity:
        key_changes.append(
            f"Recommended resupply decreases by {baseline_result.recommended_quantity - scenario_result.recommended_quantity:.2f}."
        )

    failed_constraints = [
        constraint
        for constraint in scenario_result.constraints
        if not constraint.passed
    ]

    if not scenario_result.feasible:
        decision = "NOT_FEASIBLE"
        if failed_constraints:
            decision_reason = (
                "Scenario is not feasible because "
                + "; ".join(
                    constraint.message
                    for constraint in failed_constraints
                )
            )
        else:
            decision_reason = (
                "Scenario is not feasible because one or more "
                "optimization constraints are not satisfied."
            )
    elif scenario_result.recommended_quantity <= 0:
        decision = "NO_IMMEDIATE_ACTION"
        decision_reason = (
            "No additional resupply is required under the "
            "scenario assumptions."
        )
    elif scenario_result.recommended_quantity > baseline_result.recommended_quantity:
        decision = "INCREASE_RESUPPLY"
        decision_reason = (
            "The scenario increases the required resupply quantity."
        )
    elif scenario_result.recommended_quantity < baseline_result.recommended_quantity:
        decision = "REDUCE_RESUPPLY"
        decision_reason = (
            "The scenario reduces the required resupply quantity."
        )
    else:
        decision = "MAINTAIN_PLAN"
        decision_reason = (
            "The scenario does not change the recommended resupply quantity."
        )

    return ScenarioResult(
        feasible=scenario_result.feasible,
        baseline_quantity=(
            baseline_result.recommended_quantity
        ),
        scenario_quantity=(
            scenario_result.recommended_quantity
        ),
        baseline_stock=baseline_stock,
        scenario_stock=scenario_stock,
        baseline_days_of_cover=(
            baseline_days_of_cover
        ),
        scenario_days_of_cover=(
            scenario_days_of_cover
        ),
        baseline_risk_level=baseline_risk_level,
        scenario_risk_level=scenario_risk_level,
        comparisons=comparisons,
        constraints=(
            scenario_result.constraints
        ),
        explanation=" ".join(explanation_parts),
        decision=decision,
        decision_reason=decision_reason,
        key_changes=key_changes,
    )
