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
    Select the smallest available vehicle capable of carrying
    the recommended quantity.
    """

    available_vehicles = [
        vehicle
        for vehicle in vehicles
        if vehicle.status == "AVAILABLE"
        and vehicle.capacity >= recommended_quantity
    ]

    if not available_vehicles:
        return None

    return min(
        available_vehicles,
        key=lambda vehicle: vehicle.capacity,
    )


def build_optimization_plan(
    optimization_input: OptimizationInput,
) -> OptimizationResult:
    """
    Build a demand-aware resupply plan.

    Stage 10.2 introduces:
    - planning horizon
    - expected consumption
    - safety buffer
    - maximum stock ceiling
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
                f"Safety buffer adds {safety_buffer_quantity:.2f} "
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
                code="VEHICLE_CAPACITY",
                passed=False,
                message=(
                    "No available vehicle has sufficient capacity "
                    "for the recommended resupply quantity."
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
                "but no available vehicle can carry it."
            ),
        )

    constraints.append(
        OptimizationConstraint(
            code="VEHICLE_CAPACITY",
            passed=True,
            message=(
                f"Vehicle {selected_vehicle.vehicle_code} can carry "
                f"the recommended resupply quantity."
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
        constraints=constraints,
        explanation=(
            f"Recommend resupplying "
            f"{recommended_quantity:.2f} "
            f"{optimization_input.unit} using vehicle "
            f"{selected_vehicle.vehicle_code}."
        ),
    )