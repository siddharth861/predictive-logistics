from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VehicleOption:
    vehicle_id: str
    vehicle_code: str
    capacity: float
    capacity_unit: str
    status: str
    distance_km: Optional[float] = None
    estimated_travel_hours: Optional[float] = None


@dataclass
class OptimizationInput:
    item_id: str
    item_code: str
    item_name: str
    unit: str

    location_id: str
    location_code: str

    current_stock: float
    minimum_stock: float
    maximum_stock: Optional[float]

    predicted_daily_consumption: float
    days_of_cover: Optional[float]

    # Stage 10.2 planning parameters
    planning_horizon_days: int = 7
    safety_buffer_days: float = 2.0

    vehicles: list[VehicleOption] = field(default_factory=list)


@dataclass
class OptimizationConstraint:
    code: str
    passed: bool
    message: str


@dataclass
class OptimizationResult:
    feasible: bool
    recommended_quantity: float
    selected_vehicle_id: Optional[str]
    selected_vehicle_code: Optional[str]

    # Stage 10.2 calculation details
    planning_horizon_days: int = 0
    expected_consumption: float = 0.0
    safety_buffer_quantity: float = 0.0
    target_stock: float = 0.0

    constraints: list[OptimizationConstraint] = field(
        default_factory=list
    )

    explanation: str = ""