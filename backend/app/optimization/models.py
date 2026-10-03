from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VehicleOption:
    vehicle_id: str
    vehicle_code: str
    capacity: float
    capacity_unit: str
    status: str

    # Stage 10.3 transport allocation data
    distance_km: Optional[float] = None
    estimated_travel_hours: Optional[float] = None
    current_location_id: Optional[str] = None
    is_active: bool = True


@dataclass
class SupplyDestination:
    destination_id: str
    destination_code: str

    current_stock: float
    minimum_stock: float
    maximum_stock: Optional[float]

    predicted_daily_consumption: float
    days_of_cover: Optional[float]

    planning_horizon_days: int = 7
    safety_buffer_days: float = 2.0


@dataclass
class AllocationResult:
    destination_id: str
    destination_code: str

    requested_quantity: float
    allocated_quantity: float

    remaining_need: float

    feasible: bool
    explanation: str = ""


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

    planning_horizon_days: int = 7
    safety_buffer_days: float = 2.0

    vehicles: list[VehicleOption] = field(default_factory=list)

    # Stage 10.4 multi-location allocation
    destinations: list[SupplyDestination] = field(
        default_factory=list
    )


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

    planning_horizon_days: int = 0
    expected_consumption: float = 0.0
    safety_buffer_quantity: float = 0.0
    target_stock: float = 0.0

    # Stage 10.3 allocation details
    selected_vehicle_capacity: Optional[float] = None
    selected_vehicle_capacity_unit: Optional[str] = None
    selected_vehicle_distance_km: Optional[float] = None
    selected_vehicle_travel_hours: Optional[float] = None

    # Stage 10.4 multi-location allocation
    allocations: list[AllocationResult] = field(
        default_factory=list
    )

    constraints: list[OptimizationConstraint] = field(
        default_factory=list
    )

    explanation: str = ""