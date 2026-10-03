from .models import (
    OptimizationConstraint,
    OptimizationInput,
    OptimizationResult,
    VehicleOption,
)


def calculate_recommended_quantity(
    current_stock: float,
    minimum_stock: float,
    predicted_daily_consumption: float,
    maximum_stock: float | None = None,
    planning_horizon_days: int = 7,
    safety_buffer_days: float = 2.0,
) -> tuple[float, float, float, float]:
    """
    Calculate a demand-aware resupply quantity.

    Returns:
        recommended_quantity,
        expected_consumption,
        safety_buffer_quantity,
        target_stock
    """

    if predicted_daily_consumption < 0:
        raise ValueError("Predicted consumption cannot be negative.")

    if planning_horizon_days <= 0:
        raise ValueError("Planning horizon must be greater than zero.")

    if safety_buffer_days < 0:
        raise ValueError("Safety buffer days cannot be negative.")

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


def select_vehicle(
    recommended_quantity: float,
    vehicles: list[VehicleOption],
) -> VehicleOption | None:
    """
    Select the most suitable available vehicle.

    Selection priority:
    1. Vehicle must be active.
    2. Vehicle must be AVAILABLE.
    3. Vehicle must have sufficient capacity.
    4. Prefer a vehicle already at the destination/source
       logistics location.
    5. Prefer shorter route distance.
    6. Prefer shorter estimated travel time.
    7. Prefer smaller sufficient capacity to avoid unnecessary
       transport capacity usage.
    """

    eligible_vehicles = [
        vehicle
        for vehicle in vehicles
        if vehicle.is_active
        and vehicle.status == "AVAILABLE"
        and vehicle.capacity >= recommended_quantity
    ]

    if not eligible_vehicles:
        return None

    def vehicle_sort_key(vehicle: VehicleOption):
        return (
            0 if vehicle.distance_km == 0 else 1,
            (
                vehicle.distance_km
                if vehicle.distance_km is not None
                else float("inf")
            ),
            (
                vehicle.estimated_travel_hours
                if vehicle.estimated_travel_hours is not None
                else float("inf")
            ),
            vehicle.capacity,
        )

    return min(
        eligible_vehicles,
        key=vehicle_sort_key,
    )


def build_optimization_plan(
    optimization_input: OptimizationInput,
) -> OptimizationResult:
    """
    Build a demand-aware resupply and vehicle allocation plan.

    Stage 10.3 adds transport allocation using:
    - vehicle availability
    - vehicle active state
    - vehicle capacity
    - route distance
    - estimated travel time
    """

    constraints: list[OptimizationConstraint] = []

    if optimization_input.current_stock < 0:
        constraints.append(
            OptimizationConstraint(
                code="INVALID_CURRENT_STOCK",
                passed=False,
                message="Current stock cannot be negative.",
            )
        )

    if optimization_input.minimum_stock < 0:
        constraints.append(
            OptimizationConstraint(
                code="INVALID_MINIMUM_STOCK",
                passed=False,
                message="Minimum stock cannot be negative.",
            )
        )

    if (
        optimization_input.maximum_stock is not None
        and optimization_input.maximum_stock
        < optimization_input.minimum_stock
    ):
        constraints.append(
            OptimizationConstraint(
                code="INVALID_STOCK_RANGE",
                passed=False,
                message="Maximum stock cannot be below minimum stock.",
            )
        )

    if optimization_input.predicted_daily_consumption < 0:
        constraints.append(
            OptimizationConstraint(
                code="INVALID_FORECAST",
                passed=False,
                message="Predicted consumption cannot be negative.",
            )
        )

    if optimization_input.planning_horizon_days <= 0:
        constraints.append(
            OptimizationConstraint(
                code="INVALID_PLANNING_HORIZON",
                passed=False,
                message="Planning horizon must be greater than zero.",
            )
        )

    if optimization_input.safety_buffer_days < 0:
        constraints.append(
            OptimizationConstraint(
                code="INVALID_SAFETY_BUFFER",
                passed=False,
                message="Safety buffer days cannot be negative.",
            )
        )

    if any(not constraint.passed for constraint in constraints):
        return OptimizationResult(
            feasible=False,
            recommended_quantity=0.0,
            selected_vehicle_id=None,
            selected_vehicle_code=None,
            planning_horizon_days=(
                optimization_input.planning_horizon_days
            ),
            constraints=constraints,
            explanation="Optimization input contains invalid constraints.",
        )

    (
        recommended_quantity,
        expected_consumption,
        safety_buffer_quantity,
        target_stock,
    ) = calculate_recommended_quantity(
        current_stock=optimization_input.current_stock,
        minimum_stock=optimization_input.minimum_stock,
        predicted_daily_consumption=(
            optimization_input.predicted_daily_consumption
        ),
        maximum_stock=optimization_input.maximum_stock,
        planning_horizon_days=(
            optimization_input.planning_horizon_days
        ),
        safety_buffer_days=(
            optimization_input.safety_buffer_days
        ),
    )

    constraints.append(
        OptimizationConstraint(
            code="DEMAND_FORECAST",
            passed=True,
            message=(
                f"Expected consumption over "
                f"{optimization_input.planning_horizon_days} days "
                f"is {expected_consumption:.2f} "
                f"{optimization_input.unit}."
            ),
        )
    )

    constraints.append(
        OptimizationConstraint(
            code="SAFETY_BUFFER",
            passed=True,
            message=(
                f"Safety buffer adds "
                f"{safety_buffer_quantity:.2f} "
                f"{optimization_input.unit}."
            ),
        )
    )

    constraints.append(
        OptimizationConstraint(
            code="STOCK_TARGET",
            passed=True,
            message=(
                f"Target stock is "
                f"{target_stock:.2f} "
                f"{optimization_input.unit}."
            ),
        )
    )

    if recommended_quantity == 0:
        constraints.append(
            OptimizationConstraint(
                code="NO_RESUPPLY_REQUIRED",
                passed=True,
                message=(
                    "Current stock already satisfies the "
                    "calculated planning target."
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
            constraints=constraints,
            explanation=(
                "No immediate resupply is required because "
                "current inventory satisfies the planning target."
            ),
        )

    selected_vehicle = select_vehicle(
        recommended_quantity=recommended_quantity,
        vehicles=optimization_input.vehicles,
    )

    if selected_vehicle is None:
        constraints.append(
            OptimizationConstraint(
                code="VEHICLE_ALLOCATION",
                passed=False,
                message=(
                    "No active available vehicle has sufficient "
                    "capacity for the recommended resupply quantity."
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
            constraints=constraints,
            explanation=(
                "A demand-based resupply quantity was calculated, "
                "but no suitable available vehicle could be allocated."
            ),
        )

    constraints.append(
        OptimizationConstraint(
            code="VEHICLE_ALLOCATION",
            passed=True,
            message=(
                f"Vehicle {selected_vehicle.vehicle_code} selected "
                f"for the resupply movement."
            ),
        )
    )

    constraints.append(
        OptimizationConstraint(
            code="VEHICLE_CAPACITY",
            passed=True,
            message=(
                f"Vehicle {selected_vehicle.vehicle_code} has "
                f"{selected_vehicle.capacity:.2f} "
                f"{selected_vehicle.capacity_unit} capacity."
            ),
        )
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
                    f"{selected_vehicle.estimated_travel_hours:.2f} hours."
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
        selected_vehicle_capacity=selected_vehicle.capacity,
        selected_vehicle_capacity_unit=selected_vehicle.capacity_unit,
        selected_vehicle_distance_km=selected_vehicle.distance_km,
        selected_vehicle_travel_hours=(
            selected_vehicle.estimated_travel_hours
        ),
        constraints=constraints,
        explanation=(
            f"Recommend resupplying "
            f"{recommended_quantity:.2f} "
            f"{optimization_input.unit} using vehicle "
            f"{selected_vehicle.vehicle_code}."
        ),
    )