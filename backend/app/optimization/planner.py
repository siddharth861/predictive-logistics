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
) -> float:
    """
    Calculate a basic resupply quantity.

    The target is to restore inventory to the configured maximum
    stock level when one exists. Otherwise, restore it to a
    two-day safety buffer above minimum stock.
    """

    if predicted_daily_consumption < 0:
        raise ValueError("Predicted consumption cannot be negative.")

    if maximum_stock is not None and maximum_stock > minimum_stock:
        target_stock = maximum_stock
    else:
        target_stock = minimum_stock + (
            predicted_daily_consumption * 2
        )

    recommended_quantity = max(
        0.0,
        target_stock - current_stock,
    )

    return round(recommended_quantity, 2)


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
    Build a basic feasible resupply plan.

    This is the foundation for the Stage 10 optimization engine.
    More advanced allocation and constraint optimization will be
    added in later substages.
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
        and optimization_input.maximum_stock < optimization_input.minimum_stock
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

    if any(not constraint.passed for constraint in constraints):
        return OptimizationResult(
            feasible=False,
            recommended_quantity=0.0,
            selected_vehicle_id=None,
            selected_vehicle_code=None,
            constraints=constraints,
            explanation="Optimization input contains invalid constraints.",
        )

    recommended_quantity = calculate_recommended_quantity(
        current_stock=optimization_input.current_stock,
        minimum_stock=optimization_input.minimum_stock,
        predicted_daily_consumption=(
            optimization_input.predicted_daily_consumption
        ),
        maximum_stock=optimization_input.maximum_stock,
    )

    constraints.append(
        OptimizationConstraint(
            code="STOCK_TARGET",
            passed=True,
            message="Recommended quantity is calculated from the inventory target.",
        )
    )

    selected_vehicle = select_vehicle(
        recommended_quantity=recommended_quantity,
        vehicles=optimization_input.vehicles,
    )

    if recommended_quantity == 0:
        constraints.append(
            OptimizationConstraint(
                code="NO_RESUPPLY_REQUIRED",
                passed=True,
                message="Current stock already satisfies the configured target.",
            )
        )

        return OptimizationResult(
            feasible=True,
            recommended_quantity=0.0,
            selected_vehicle_id=None,
            selected_vehicle_code=None,
            constraints=constraints,
            explanation=(
                "No immediate resupply is required because current "
                "inventory satisfies the configured target."
            ),
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
            constraints=constraints,
            explanation=(
                "A resupply quantity was calculated, but no available "
                "vehicle can carry the required quantity."
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
        constraints=constraints,
        explanation=(
            f"Recommend resupplying {recommended_quantity:.2f} "
            f"{optimization_input.unit} using vehicle "
            f"{selected_vehicle.vehicle_code}."
        ),
    )