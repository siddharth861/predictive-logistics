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
    distance_from_source_km: Optional[float] = None
    estimated_travel_hours: Optional[float] = None
    route_risk_level: str = "LOW"
    route_available: bool = True


@dataclass
class RouteConstraint:
    code: str
    passed: bool
    message: str
    severity: str = "INFO"


@dataclass
class AllocationResult:
    destination_id: str
    destination_code: str
    requested_quantity: float
    allocated_quantity: float
    remaining_need: float
    feasible: bool
    explanation: str = ""
    route_distance_km: Optional[float] = None
    estimated_travel_hours: Optional[float] = None
    route_risk_level: str = "LOW"


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
    destinations: list[SupplyDestination] = field(default_factory=list)
    max_route_distance_km: Optional[float] = None
    max_travel_hours: Optional[float] = None
    blocked_route_risk_levels: list[str] = field(default_factory=list)


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
    selected_vehicle_capacity: Optional[float] = None
    selected_vehicle_capacity_unit: Optional[str] = None
    selected_vehicle_distance_km: Optional[float] = None
    selected_vehicle_travel_hours: Optional[float] = None
    allocations: list[AllocationResult] = field(default_factory=list)
    route_constraints: list[RouteConstraint] = field(default_factory=list)
    constraints: list[OptimizationConstraint] = field(default_factory=list)
    explanation: str = ""


@dataclass
class ScenarioInput:
    additional_supply: float = 0.0
    demand_change_percent: float = 0.0
    planning_horizon_days: Optional[int] = None
    safety_buffer_days: Optional[float] = None
    vehicle_id: Optional[str] = None
    route_available: Optional[bool] = None
    route_risk_level: Optional[str] = None
    additional_supply_unit: Optional[str] = None


@dataclass
class ScenarioComparison:
    metric: str
    baseline_value: float
    scenario_value: float
    change: float
    change_percent: Optional[float] = None


@dataclass
class ScenarioResult:
    feasible: bool
    baseline_quantity: float
    scenario_quantity: float
    baseline_stock: float
    scenario_stock: float
    baseline_days_of_cover: Optional[float]
    scenario_days_of_cover: Optional[float]
    baseline_risk_level: str
    scenario_risk_level: str
    comparisons: list[ScenarioComparison] = field(default_factory=list)
    constraints: list[OptimizationConstraint] = field(default_factory=list)
    explanation: str = ""
    decision: str = "REVIEW"
    decision_reason: str = ""
    key_changes: list[str] = field(default_factory=list)
