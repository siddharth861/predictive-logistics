from __future__ import annotations

from typing import Optional

from app.optimization.models import (
    AllocationResult,
    OptimizationConstraint,
    OptimizationInput,
    OptimizationResult,
    RouteConstraint,
    SupplyDestination,
    VehicleOption,
)


def calculate_recommended_quantity(
    current_stock: float,
    minimum_stock: float,
    maximum_stock: Optional[float],
    predicted_daily_consumption: float,
    planning_horizon_days: int = 7,
    safety_buffer_days: float = 2.0,
) -> tuple[float, float, float, float]:
    if current_stock < 0:
        raise ValueError("Current stock cannot be negative.")

    if minimum_stock < 0:
        raise ValueError("Minimum stock cannot be negative.")

    if maximum_stock is not None and maximum_stock < minimum_stock:
        raise ValueError(
            "Maximum stock cannot be lower than minimum stock."
        )

    if predicted_daily_consumption < 0:
        raise ValueError(
            "Predicted daily consumption cannot be negative."
        )

    if planning_horizon_days <= 0:
        raise ValueError(
            "Planning horizon must be greater than zero."
        )

    if safety_buffer_days < 0:
        raise ValueError(
            "Safety buffer days cannot be negative."
        )

    expected_consumption = (
        predicted_daily_consumption * planning_horizon_days
    )

    safety_buffer_quantity = (
        predicted_daily_consumption * safety_buffer_days
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
        round(recommended_quantity, 2),
        round(expected_consumption, 2),
        round(safety_buffer_quantity, 2),
        round(target_stock, 2),
    )


def calculate_destination_need(
    destination: SupplyDestination,
) -> tuple[float, float, float, float]:
    return calculate_recommended_quantity(
        current_stock=destination.current_stock,
        minimum_stock=destination.minimum_stock,
        maximum_stock=destination.maximum_stock,
        predicted_daily_consumption=(
            destination.predicted_daily_consumption
        ),
        planning_horizon_days=destination.planning_horizon_days,
        safety_buffer_days=destination.safety_buffer_days,
    )


def evaluate_route_constraints(
    destination: SupplyDestination,
    optimization_input: OptimizationInput,
) -> list[RouteConstraint]:
    constraints: list[RouteConstraint] = []

    if not destination.route_available:
        constraints.append(
            RouteConstraint(
                code="ROUTE_UNAVAILABLE",
                passed=False,
                message=(
                    f"Route to {destination.destination_code} "
                    "is currently unavailable."
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
        optimization_input.max_route_distance_km is not None
        and destination.distance_from_source_km is not None
    ):
        passed = (
            destination.distance_from_source_km
            <= optimization_input.max_route_distance_km
        )

        constraints.append(
            RouteConstraint(
                code="MAX_ROUTE_DISTANCE",
                passed=passed,
                message=(
                    f"Route distance is "
                    f"{destination.distance_from_source_km:.3f} km; "
                    f"maximum allowed is "
                    f"{optimization_input.max_route_distance_km:.3f} km."
                ),
                severity="HIGH" if not passed else "INFO",
            )
        )

    if (
        optimization_input.max_travel_hours is not None
        and destination.estimated_travel_hours is not None
    ):
        passed = (
            destination.estimated_travel_hours
            <= optimization_input.max_travel_hours
        )

        constraints.append(
            RouteConstraint(
                code="MAX_TRAVEL_TIME",
                passed=passed,
                message=(
                    f"Estimated travel time is "
                    f"{destination.estimated_travel_hours:.2f} hours; "
                    f"maximum allowed is "
                    f"{optimization_input.max_travel_hours:.2f} hours."
                ),
                severity="HIGH" if not passed else "INFO",
            )
        )

    blocked_risk_levels = {
        level.upper()
        for level in optimization_input.blocked_route_risk_levels
    }

    risk_level = destination.route_risk_level.upper()

    if blocked_risk_levels:
        passed = risk_level not in blocked_risk_levels

        constraints.append(
            RouteConstraint(
                code="ROUTE_RISK",
                passed=passed,
                message=(
                    f"Route risk level is {risk_level}; "
                    f"blocked levels are "
                    f"{', '.join(sorted(blocked_risk_levels))}."
                ),
                severity="HIGH" if not passed else "INFO",
            )
        )

    return constraints


def is_route_feasible(
    destination: SupplyDestination,
    optimization_input: OptimizationInput,
) -> tuple[bool, list[RouteConstraint]]:
    route_constraints = evaluate_route_constraints(
        destination,
        optimization_input,
    )

    feasible = all(
        constraint.passed
        for constraint in route_constraints
    )

    return feasible, route_constraints


def allocate_supply(
    available_supply: float,
    destinations: list[SupplyDestination],
    optimization_input: Optional[OptimizationInput] = None,
) -> tuple[list[AllocationResult], list[RouteConstraint]]:
    if available_supply < 0:
        raise ValueError("Available supply cannot be negative.")

    requests = []
    route_constraints: list[RouteConstraint] = []

    for index, destination in enumerate(destinations):
        (
            requested_quantity,
            _expected_consumption,
            _safety_buffer_quantity,
            _target_stock,
        ) = calculate_destination_need(destination)

        if optimization_input is not None:
            route_feasible, destination_constraints = (
                is_route_feasible(
                    destination,
                    optimization_input,
                )
            )

            route_constraints.extend(
                destination_constraints
            )
        else:
            route_feasible = True

        requests.append(
            (
                index,
                destination,
                requested_quantity,
                route_feasible,
            )
        )

    requests.sort(
        key=lambda entry: (
            not entry[3],
            -entry[2],
            entry[0],
        )
    )

    remaining_supply = available_supply
    results: list[AllocationResult] = []

    for (
        _index,
        destination,
        requested_quantity,
        route_feasible,
    ) in requests:

        if not route_feasible:
            results.append(
                AllocationResult(
                    destination_id=destination.destination_id,
                    destination_code=destination.destination_code,
                    requested_quantity=round(
                        requested_quantity,
                        2,
                    ),
                    allocated_quantity=0.0,
                    remaining_need=round(
                        requested_quantity,
                        2,
                    ),
                    feasible=False,
                    explanation=(
                        f"No supply allocated to "
                        f"{destination.destination_code} "
                        "because its route is not feasible."
                    ),
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
            continue

        allocated_quantity = min(
            requested_quantity,
            remaining_supply,
        )

        allocated_quantity = round(
            max(0.0, allocated_quantity),
            2,
        )

        remaining_need = round(
            max(
                0.0,
                requested_quantity - allocated_quantity,
            ),
            2,
        )

        fully_satisfied = remaining_need == 0.0

        if fully_satisfied:
            explanation = (
                f"Allocated {allocated_quantity:.2f} "
                f"to {destination.destination_code}."
            )
        else:
            explanation = (
                f"Allocated {allocated_quantity:.2f} "
                f"to {destination.destination_code}; "
                f"{remaining_need:.2f} remains unmet."
            )

        results.append(
            AllocationResult(
                destination_id=destination.destination_id,
                destination_code=destination.destination_code,
                requested_quantity=round(
                    requested_quantity,
                    2,
                ),
                allocated_quantity=allocated_quantity,
                remaining_need=remaining_need,
                feasible=fully_satisfied,
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

        remaining_supply = round(
            max(
                0.0,
                remaining_supply - allocated_quantity,
            ),
            2,
        )

    result_by_id = {
        result.destination_id: result
        for result in results
    }

    ordered_results = [
        result_by_id[destination.destination_id]
        for destination in destinations
    ]

    return ordered_results, route_constraints


def select_vehicle(
    vehicles: list[VehicleOption],
    recommended_quantity: float,
) -> Optional[VehicleOption]:
    eligible_vehicles = []

    for vehicle in vehicles:
        if not vehicle.is_active:
            continue

        if vehicle.status.upper() != "AVAILABLE":
            continue

        if vehicle.capacity < recommended_quantity:
            continue

        distance = (
            vehicle.distance_km
            if vehicle.distance_km is not None
            else float("inf")
        )

        travel_time = (
            vehicle.estimated_travel_hours
            if vehicle.estimated_travel_hours is not None
            else float("inf")
        )

        eligible_vehicles.append(
            (
                distance,
                travel_time,
                vehicle.capacity,
                vehicle,
            )
        )

    if not eligible_vehicles:
        return None

    eligible_vehicles.sort(
        key=lambda entry: (
            entry[0],
            entry[1],
            entry[2],
        )
    )

    return eligible_vehicles[0][3]


def select_route_compatible_vehicle(
    vehicles: list[VehicleOption],
    recommended_quantity: float,
    destination: SupplyDestination,
) -> Optional[VehicleOption]:
    """
    Select a vehicle that can carry the required quantity and is
    compatible with the selected destination route.
    """

    eligible_vehicles = []

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

        distance = (
            vehicle.distance_km
            if vehicle.distance_km is not None
            else float("inf")
        )

        travel_time = (
            vehicle.estimated_travel_hours
            if vehicle.estimated_travel_hours is not None
            else float("inf")
        )

        eligible_vehicles.append(
            (
                distance,
                travel_time,
                vehicle.capacity,
                vehicle,
            )
        )

    if not eligible_vehicles:
        return None

    eligible_vehicles.sort(
        key=lambda entry: (
            entry[0],
            entry[1],
            entry[2],
        )
    )

    return eligible_vehicles[0][3]


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

    constraints = [
        OptimizationConstraint(
            code="DEMAND_FORECAST",
            passed=True,
            message=(
                f"Expected consumption over "
                f"{optimization_input.planning_horizon_days} "
                f"days is "
                f"{expected_consumption:.2f} "
                f"{optimization_input.unit}."
            ),
        ),
        OptimizationConstraint(
            code="SAFETY_BUFFER",
            passed=True,
            message=(
                f"Safety buffer adds "
                f"{safety_buffer_quantity:.2f} "
                f"{optimization_input.unit}."
            ),
        ),
        OptimizationConstraint(
            code="STOCK_TARGET",
            passed=True,
            message=(
                f"Target stock is "
                f"{target_stock:.2f} "
                f"{optimization_input.unit}."
            ),
        ),
    ]

    route_constraints: list[RouteConstraint] = []
    allocations: list[AllocationResult] = []

    # ---------------------------------------------------------
    # Multi-location allocation
    # ---------------------------------------------------------

    if optimization_input.destinations:

        (
            allocations,
            route_constraints,
        ) = allocate_supply(
            available_supply=optimization_input.current_stock,
            destinations=optimization_input.destinations,
            optimization_input=optimization_input,
        )

        total_requested = round(
            sum(
                allocation.requested_quantity
                for allocation in allocations
            ),
            2,
        )

        total_allocated = round(
            sum(
                allocation.allocated_quantity
                for allocation in allocations
            ),
            2,
        )

        all_destinations_satisfied = all(
            allocation.feasible
            for allocation in allocations
        )

        route_feasible = all(
            constraint.passed
            for constraint in route_constraints
        )

        constraints.append(
            OptimizationConstraint(
                code="MULTI_LOCATION_ALLOCATION",
                passed=(
                    all_destinations_satisfied
                    and route_feasible
                ),
                message=(
                    f"Allocated {total_allocated:.2f} "
                    f"of {total_requested:.2f} "
                    f"{optimization_input.unit} "
                    f"across {len(allocations)} destinations."
                ),
            )
        )

        if not route_feasible:
            constraints.append(
                OptimizationConstraint(
                    code="ROUTE_FEASIBILITY",
                    passed=False,
                    message=(
                        "One or more destination routes "
                        "do not satisfy the configured "
                        "route constraints."
                    ),
                )
            )

        if total_allocated <= 0:
            return OptimizationResult(
                feasible=False,
                recommended_quantity=0.0,
                selected_vehicle_id=None,
                selected_vehicle_code=None,
                planning_horizon_days=(
                    optimization_input.planning_horizon_days
                ),
                expected_consumption=expected_consumption,
                safety_buffer_quantity=safety_buffer_quantity,
                target_stock=target_stock,
                allocations=allocations,
                route_constraints=route_constraints,
                constraints=constraints,
                explanation=(
                    "No feasible supply allocation "
                    "is available for the requested "
                    "destinations."
                ),
            )

        # Select vehicle against the first feasible allocated
        # destination. This preserves deterministic behavior
        # until multi-vehicle routing is introduced.
        selected_destination = next(
            (
                destination
                for destination in optimization_input.destinations
                if any(
                    allocation.destination_id
                    == destination.destination_id
                    and allocation.allocated_quantity > 0
                    for allocation in allocations
                )
            ),
            None,
        )

        if selected_destination is None:
            return OptimizationResult(
                feasible=False,
                recommended_quantity=total_allocated,
                selected_vehicle_id=None,
                selected_vehicle_code=None,
                planning_horizon_days=(
                    optimization_input.planning_horizon_days
                ),
                expected_consumption=expected_consumption,
                safety_buffer_quantity=safety_buffer_quantity,
                target_stock=target_stock,
                allocations=allocations,
                route_constraints=route_constraints,
                constraints=constraints,
                explanation=(
                    "No destination received an allocation."
                ),
            )

        selected_vehicle = select_route_compatible_vehicle(
            optimization_input.vehicles,
            total_allocated,
            selected_destination,
        )

        if selected_vehicle is None:
            constraints.append(
                OptimizationConstraint(
                    code="VEHICLE_ALLOCATION",
                    passed=False,
                    message=(
                        "No available vehicle is compatible "
                        "with the selected route and has "
                        "sufficient capacity."
                    ),
                )
            )

            return OptimizationResult(
                feasible=False,
                recommended_quantity=total_allocated,
                selected_vehicle_id=None,
                selected_vehicle_code=None,
                planning_horizon_days=(
                    optimization_input.planning_horizon_days
                ),
                expected_consumption=expected_consumption,
                safety_buffer_quantity=safety_buffer_quantity,
                target_stock=target_stock,
                allocations=allocations,
                route_constraints=route_constraints,
                constraints=constraints,
                explanation=(
                    f"{total_allocated:.2f} "
                    f"{optimization_input.unit} "
                    "can be allocated, but no "
                    "route-compatible vehicle is available."
                ),
            )

        constraints.extend(
            [
                OptimizationConstraint(
                    code="VEHICLE_ALLOCATION",
                    passed=True,
                    message=(
                        f"Vehicle "
                        f"{selected_vehicle.vehicle_code} "
                        "selected for the multi-location "
                        "movement."
                    ),
                ),
                OptimizationConstraint(
                    code="VEHICLE_CAPACITY",
                    passed=True,
                    message=(
                        f"Vehicle "
                        f"{selected_vehicle.vehicle_code} "
                        f"has "
                        f"{selected_vehicle.capacity:.2f} "
                        f"{selected_vehicle.capacity_unit} "
                        "capacity."
                    ),
                ),
                OptimizationConstraint(
                    code="VEHICLE_ROUTE_COMPATIBILITY",
                    passed=True,
                    message=(
                        f"Vehicle "
                        f"{selected_vehicle.vehicle_code} "
                        "is compatible with the selected route."
                    ),
                ),
            ]
        )

        return OptimizationResult(
            feasible=(
                all_destinations_satisfied
                and route_feasible
            ),
            recommended_quantity=total_allocated,
            selected_vehicle_id=selected_vehicle.vehicle_id,
            selected_vehicle_code=selected_vehicle.vehicle_code,
            planning_horizon_days=(
                optimization_input.planning_horizon_days
            ),
            expected_consumption=expected_consumption,
            safety_buffer_quantity=safety_buffer_quantity,
            target_stock=target_stock,
            selected_vehicle_capacity=(
                selected_vehicle.capacity
            ),
            selected_vehicle_capacity_unit=(
                selected_vehicle.capacity_unit
            ),
            selected_vehicle_distance_km=(
                selected_vehicle.distance_km
            ),
            selected_vehicle_travel_hours=(
                selected_vehicle.estimated_travel_hours
            ),
            allocations=allocations,
            route_constraints=route_constraints,
            constraints=constraints,
            explanation=(
                f"Allocate {total_allocated:.2f} "
                f"{optimization_input.unit} across "
                f"{len(allocations)} destinations using "
                f"{selected_vehicle.vehicle_code}."
            ),
        )

    # ---------------------------------------------------------
    # Existing single-destination behavior
    # ---------------------------------------------------------

    if recommended_quantity <= 0:
        constraints.append(
            OptimizationConstraint(
                code="NO_RESUPPLY_REQUIRED",
                passed=True,
                message=(
                    "Current stock already meets the "
                    "calculated target."
                ),
            )
        )

        return OptimizationResult(
            feasible=True,
            recommended_quantity=0.0,
            selected_vehicle_id=None,
            selected_vehicle_code=None,
            planning_horizon_days=(
                optimization_input.planning_horizon_days
            ),
            expected_consumption=expected_consumption,
            safety_buffer_quantity=safety_buffer_quantity,
            target_stock=target_stock,
            allocations=[],
            route_constraints=[],
            constraints=constraints,
            explanation=(
                "No immediate resupply is required."
            ),
        )

    selected_vehicle = select_vehicle(
        optimization_input.vehicles,
        recommended_quantity,
    )

    if selected_vehicle is None:
        constraints.append(
            OptimizationConstraint(
                code="VEHICLE_ALLOCATION",
                passed=False,
                message=(
                    "No active, available vehicle has "
                    "sufficient capacity for the "
                    "recommended quantity."
                ),
            )
        )

        return OptimizationResult(
            feasible=False,
            recommended_quantity=recommended_quantity,
            selected_vehicle_id=None,
            selected_vehicle_code=None,
            planning_horizon_days=(
                optimization_input.planning_horizon_days
            ),
            expected_consumption=expected_consumption,
            safety_buffer_quantity=safety_buffer_quantity,
            target_stock=target_stock,
            allocations=[],
            route_constraints=[],
            constraints=constraints,
            explanation=(
                f"Recommend resupplying "
                f"{recommended_quantity:.2f} "
                f"{optimization_input.unit}, but no "
                "suitable vehicle is available."
            ),
        )

    constraints.extend(
        [
            OptimizationConstraint(
                code="VEHICLE_ALLOCATION",
                passed=True,
                message=(
                    f"Vehicle "
                    f"{selected_vehicle.vehicle_code} "
                    "selected for the resupply movement."
                ),
            ),
            OptimizationConstraint(
                code="VEHICLE_CAPACITY",
                passed=True,
                message=(
                    f"Vehicle "
                    f"{selected_vehicle.vehicle_code} "
                    f"has "
                    f"{selected_vehicle.capacity:.2f} "
                    f"{selected_vehicle.capacity_unit} "
                    "capacity."
                ),
            ),
        ]
    )

    if selected_vehicle.distance_km is not None:
        constraints.append(
            OptimizationConstraint(
                code="ROUTE_DISTANCE",
                passed=True,
                message=(
                    f"Selected vehicle route distance is "
                    f"{selected_vehicle.distance_km:.3f} km."
                ),
            )
        )

    if selected_vehicle.estimated_travel_hours is not None:
        constraints.append(
            OptimizationConstraint(
                code="TRAVEL_TIME",
                passed=True,
                message=(
                    f"Estimated travel time is "
                    f"{selected_vehicle.estimated_travel_hours:.2f} "
                    "hours."
                ),
            )
        )

    return OptimizationResult(
        feasible=True,
        recommended_quantity=recommended_quantity,
        selected_vehicle_id=selected_vehicle.vehicle_id,
        selected_vehicle_code=selected_vehicle.vehicle_code,
        planning_horizon_days=(
            optimization_input.planning_horizon_days
        ),
        expected_consumption=expected_consumption,
        safety_buffer_quantity=safety_buffer_quantity,
        target_stock=target_stock,
        selected_vehicle_capacity=(
            selected_vehicle.capacity
        ),
        selected_vehicle_capacity_unit=(
            selected_vehicle.capacity_unit
        ),
        selected_vehicle_distance_km=(
            selected_vehicle.distance_km
        ),
        selected_vehicle_travel_hours=(
            selected_vehicle.estimated_travel_hours
        ),
        allocations=[],
        route_constraints=[],
        constraints=constraints,
        explanation=(
            f"Recommend resupplying "
            f"{recommended_quantity:.2f} "
            f"{optimization_input.unit} using vehicle "
            f"{selected_vehicle.vehicle_code}."
        ),
    )