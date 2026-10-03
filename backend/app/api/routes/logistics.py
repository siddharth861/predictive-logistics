from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import (
    ConsumptionRecord,
    DataSource,
    DemandRecord,
    Inventory,
    Item,
    Location,
    Shipment,
    Vehicle,
    Supplier,
    MaintenanceRecord,
    LogisticsEvent,
)

router = APIRouter(prefix="/api/logistics", tags=["Logistics"])


# ============================================================
# LOCATION SCHEMAS
# ============================================================

class LocationCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=150)
    location_type: str = Field(min_length=1, max_length=50)
    latitude: float
    longitude: float
    description: Optional[str] = None


# ============================================================
# ITEM SCHEMAS
# ============================================================

class ItemCreate(BaseModel):
    item_code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    category: Optional[str] = None
    unit: str = "UNIT"
    description: Optional[str] = None


# ============================================================
# INVENTORY SCHEMAS
# ============================================================

class InventoryCreate(BaseModel):
    item_id: str
    location_id: str
    quantity: float = Field(ge=0)
    minimum_stock: float = Field(default=0, ge=0)
    maximum_stock: Optional[float] = Field(default=None, ge=0)


# ============================================================
# CONSUMPTION SCHEMAS
# ============================================================

class ConsumptionCreate(BaseModel):
    item_id: str
    location_id: str
    consumption_date: date
    quantity: float = Field(ge=0)
    source_id: Optional[str] = None


# ============================================================
# DEMAND SCHEMAS
# ============================================================

class DemandCreate(BaseModel):
    item_id: str
    location_id: str
    demand_date: date
    quantity: float = Field(ge=0)
    source_id: Optional[str] = None


# ============================================================
# VEHICLE SCHEMAS
# ============================================================

class VehicleCreate(BaseModel):
    vehicle_code: str = Field(min_length=1, max_length=100)
    vehicle_type: str = Field(min_length=1, max_length=100)
    capacity: float = Field(gt=0)
    capacity_unit: str = Field(
        default="UNIT",
        min_length=1,
        max_length=50,
    )
    current_location_id: Optional[str] = None
    status: str = "AVAILABLE"


# ============================================================
# SHIPMENT SCHEMAS
# ============================================================

class ShipmentCreate(BaseModel):
    shipment_code: str = Field(min_length=1, max_length=100)
    item_id: str
    quantity: float = Field(gt=0)
    source_location_id: str
    destination_location_id: str
    vehicle_id: Optional[str] = None
    status: str = "PLANNED"
    planned_departure: Optional[datetime] = None
    estimated_arrival: Optional[datetime] = None
    notes: Optional[str] = None


class ShipmentStatusUpdate(BaseModel):
    status: str


# ============================================================
# SUPPLIER SCHEMAS
# ============================================================

class SupplierCreate(BaseModel):
    supplier_code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    supplier_type: Optional[str] = None
    contact_details: Optional[str] = None
    location_id: Optional[str] = None
    status: str = "ACTIVE"


# ============================================================
# MAINTENANCE SCHEMAS
# ============================================================

class MaintenanceCreate(BaseModel):
    vehicle_id: str
    maintenance_type: str = Field(min_length=1, max_length=100)
    status: str = "SCHEDULED"
    scheduled_date: Optional[date] = None
    completed_date: Optional[date] = None
    description: Optional[str] = None
    cost: Optional[float] = Field(default=None, ge=0)


class MaintenanceStatusUpdate(BaseModel):
    status: str


# ============================================================
# EVENT SCHEMAS
# ============================================================

class LogisticsEventCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=50)
    severity: str = "INFO"
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    location_id: Optional[str] = None
    vehicle_id: Optional[str] = None
    shipment_id: Optional[str] = None


# ============================================================
# LOCATIONS
# ============================================================

@router.post("/locations")
def create_location(
    payload: LocationCreate,
    db: Session = Depends(get_db),
):
    if not (-90 <= payload.latitude <= 90):
        raise HTTPException(
            status_code=400,
            detail="Invalid latitude",
        )

    if not (-180 <= payload.longitude <= 180):
        raise HTTPException(
            status_code=400,
            detail="Invalid longitude",
        )

    existing = db.scalar(
        select(Location).where(
            Location.code == payload.code
        )
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Location code already exists",
        )

    from geoalchemy2.elements import WKTElement

    location = Location(
        code=payload.code,
        name=payload.name,
        location_type=payload.location_type,
        description=payload.description,
        geometry=WKTElement(
            f"POINT({payload.longitude} {payload.latitude})",
            srid=4326,
        ),
    )

    db.add(location)
    db.commit()
    db.refresh(location)

    return {
        "id": str(location.id),
        "code": location.code,
        "name": location.name,
        "location_type": location.location_type,
        "description": location.description,
        "is_active": location.is_active,
        "created_at": location.created_at,
    }


@router.get("/locations")
def list_locations(
    db: Session = Depends(get_db),
):
    locations = db.scalars(
        select(Location).order_by(Location.code)
    ).all()

    return {
        "count": len(locations),
        "locations": [
            {
                "id": str(location.id),
                "code": location.code,
                "name": location.name,
                "description": location.description,
                "location_type": location.location_type,
                "is_active": location.is_active,
                "created_at": location.created_at,
            }
            for location in locations
        ],
    }


# ============================================================
# ITEMS
# ============================================================

@router.post("/items")
def create_item(
    payload: ItemCreate,
    db: Session = Depends(get_db),
):
    existing = db.scalar(
        select(Item).where(
            Item.item_code == payload.item_code
        )
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Item code already exists",
        )

    item = Item(
        item_code=payload.item_code,
        name=payload.name,
        category=payload.category,
        unit=payload.unit,
        description=payload.description,
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    return {
        "id": str(item.id),
        "item_code": item.item_code,
        "name": item.name,
        "category": item.category,
        "unit": item.unit,
        "description": item.description,
        "is_active": item.is_active,
        "created_at": item.created_at,
    }


@router.get("/items")
def list_items(
    db: Session = Depends(get_db),
):
    items = db.scalars(
        select(Item).order_by(Item.item_code)
    ).all()

    return {
        "count": len(items),
        "items": [
            {
                "id": str(item.id),
                "item_code": item.item_code,
                "name": item.name,
                "category": item.category,
                "unit": item.unit,
                "description": item.description,
                "is_active": item.is_active,
                "created_at": item.created_at,
            }
            for item in items
        ],
    }


# ============================================================
# INVENTORY
# ============================================================

@router.post("/inventory")
def create_inventory(
    payload: InventoryCreate,
    db: Session = Depends(get_db),
):
    item = db.get(Item, payload.item_id)

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Item not found",
        )

    location = db.get(Location, payload.location_id)

    if not location:
        raise HTTPException(
            status_code=404,
            detail="Location not found",
        )

    if not location.is_active:
        raise HTTPException(
            status_code=400,
            detail="Location is inactive",
        )

    if (
        payload.maximum_stock is not None
        and payload.maximum_stock < payload.minimum_stock
    ):
        raise HTTPException(
            status_code=400,
            detail="maximum_stock cannot be less than minimum_stock",
        )

    existing = db.scalar(
        select(Inventory).where(
            Inventory.item_id == payload.item_id,
            Inventory.location_id == payload.location_id,
        )
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Inventory record already exists for this item and location",
        )

    inventory = Inventory(
        item_id=payload.item_id,
        location_id=payload.location_id,
        quantity=payload.quantity,
        minimum_stock=payload.minimum_stock,
        maximum_stock=payload.maximum_stock,
    )

    db.add(inventory)
    db.commit()
    db.refresh(inventory)

    return {
        "id": str(inventory.id),
        "item_id": str(inventory.item_id),
        "location_id": str(inventory.location_id),
        "quantity": inventory.quantity,
        "minimum_stock": inventory.minimum_stock,
        "maximum_stock": inventory.maximum_stock,
        "created_at": inventory.created_at,
    }


@router.get("/inventory")
def list_inventory(
    db: Session = Depends(get_db),
):
    records = db.scalars(
        select(Inventory).order_by(
            Inventory.created_at.desc()
        )
    ).all()

    return {
        "count": len(records),
        "inventory": [
            {
                "id": str(record.id),
                "item_id": str(record.item_id),
                "item_code": record.item.item_code,
                "item_name": record.item.name,
                "location_id": str(record.location_id),
                "location_code": record.location.code,
                "location_name": record.location.name,
                "quantity": record.quantity,
                "minimum_stock": record.minimum_stock,
                "maximum_stock": record.maximum_stock,
                "created_at": record.created_at,
            }
            for record in records
        ],
    }


# ============================================================
# CONSUMPTION
# ============================================================

@router.post("/consumption")
def create_consumption(
    payload: ConsumptionCreate,
    db: Session = Depends(get_db),
):
    item = db.get(Item, payload.item_id)

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Item not found",
        )

    location = db.get(Location, payload.location_id)

    if not location:
        raise HTTPException(
            status_code=404,
            detail="Location not found",
        )

    if payload.source_id:
        source = db.get(
            DataSource,
            payload.source_id,
        )

        if not source:
            raise HTTPException(
                status_code=404,
                detail="Data source not found",
            )

    record = ConsumptionRecord(
        item_id=payload.item_id,
        location_id=payload.location_id,
        consumption_date=payload.consumption_date,
        quantity=payload.quantity,
        source_id=payload.source_id,
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "id": str(record.id),
        "item_code": item.item_code,
        "item_name": item.name,
        "location_code": location.code,
        "location_name": location.name,
        "consumption_date": record.consumption_date,
        "quantity": record.quantity,
        "source_id": (
            str(record.source_id)
            if record.source_id
            else None
        ),
        "created_at": record.created_at,
    }


@router.get("/consumption")
def list_consumption(
    item_id: Optional[str] = None,
    location_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
):
    query = select(ConsumptionRecord)

    if item_id:
        query = query.where(
            ConsumptionRecord.item_id == item_id
        )

    if location_id:
        query = query.where(
            ConsumptionRecord.location_id == location_id
        )

    if start_date:
        query = query.where(
            ConsumptionRecord.consumption_date >= start_date
        )

    if end_date:
        query = query.where(
            ConsumptionRecord.consumption_date <= end_date
        )

    records = db.scalars(
        query.order_by(
            ConsumptionRecord.consumption_date.desc()
        )
    ).all()

    return {
        "count": len(records),
        "consumption": [
            {
                "id": str(record.id),
                "item_code": record.item.item_code,
                "item_name": record.item.name,
                "location_code": record.location.code,
                "location_name": record.location.name,
                "consumption_date": record.consumption_date,
                "quantity": record.quantity,
                "source_id": (
                    str(record.source_id)
                    if record.source_id
                    else None
                ),
                "created_at": record.created_at,
            }
            for record in records
        ],
    }


# ============================================================
# DEMAND
# ============================================================

@router.post("/demand")
def create_demand(
    payload: DemandCreate,
    db: Session = Depends(get_db),
):
    item = db.get(Item, payload.item_id)

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Item not found",
        )

    location = db.get(Location, payload.location_id)

    if not location:
        raise HTTPException(
            status_code=404,
            detail="Location not found",
        )

    if payload.source_id:
        source = db.get(
            DataSource,
            payload.source_id,
        )

        if not source:
            raise HTTPException(
                status_code=404,
                detail="Data source not found",
            )

    record = DemandRecord(
        item_id=payload.item_id,
        location_id=payload.location_id,
        demand_date=payload.demand_date,
        quantity=payload.quantity,
        source_id=payload.source_id,
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "id": str(record.id),
        "item_code": item.item_code,
        "item_name": item.name,
        "location_code": location.code,
        "location_name": location.name,
        "demand_date": record.demand_date,
        "quantity": record.quantity,
        "source_id": (
            str(record.source_id)
            if record.source_id
            else None
        ),
        "created_at": record.created_at,
    }


@router.get("/demand")
def list_demand(
    item_id: Optional[str] = None,
    location_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
):
    query = select(DemandRecord)

    if item_id:
        query = query.where(
            DemandRecord.item_id == item_id
        )

    if location_id:
        query = query.where(
            DemandRecord.location_id == location_id
        )

    if start_date:
        query = query.where(
            DemandRecord.demand_date >= start_date
        )

    if end_date:
        query = query.where(
            DemandRecord.demand_date <= end_date
        )

    records = db.scalars(
        query.order_by(
            DemandRecord.demand_date.desc()
        )
    ).all()

    return {
        "count": len(records),
        "demand": [
            {
                "id": str(record.id),
                "item_code": record.item.item_code,
                "item_name": record.item.name,
                "location_code": record.location.code,
                "location_name": record.location.name,
                "demand_date": record.demand_date,
                "quantity": record.quantity,
                "source_id": (
                    str(record.source_id)
                    if record.source_id
                    else None
                ),
                "created_at": record.created_at,
            }
            for record in records
        ],
    }


# ============================================================
# VEHICLES
# ============================================================

@router.post("/vehicles")
def create_vehicle(
    payload: VehicleCreate,
    db: Session = Depends(get_db),
):
    existing = db.scalar(
        select(Vehicle).where(
            Vehicle.vehicle_code == payload.vehicle_code
        )
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Vehicle code already exists",
        )

    allowed_statuses = {
        "AVAILABLE",
        "IN_TRANSIT",
        "MAINTENANCE",
        "UNAVAILABLE",
    }

    if payload.status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid status. "
                f"Allowed values: {sorted(allowed_statuses)}"
            ),
        )

    location = None

    if payload.current_location_id:
        location = db.get(
            Location,
            payload.current_location_id,
        )

        if not location:
            raise HTTPException(
                status_code=404,
                detail="Current location not found",
            )

    vehicle = Vehicle(
        vehicle_code=payload.vehicle_code,
        vehicle_type=payload.vehicle_type,
        capacity=payload.capacity,
        capacity_unit=payload.capacity_unit,
        current_location_id=payload.current_location_id,
        status=payload.status,
    )

    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)

    return {
        "id": str(vehicle.id),
        "vehicle_code": vehicle.vehicle_code,
        "vehicle_type": vehicle.vehicle_type,
        "capacity": vehicle.capacity,
        "capacity_unit": vehicle.capacity_unit,
        "current_location_id": (
            str(vehicle.current_location_id)
            if vehicle.current_location_id
            else None
        ),
        "current_location": (
            location.code
            if location
            else None
        ),
        "status": vehicle.status,
        "is_active": vehicle.is_active,
        "created_at": vehicle.created_at,
    }


@router.get("/vehicles")
def list_vehicles(
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    query = select(Vehicle)

    if status:
        query = query.where(
            Vehicle.status == status
        )

    vehicles = db.scalars(
        query.order_by(Vehicle.vehicle_code)
    ).all()

    return {
        "count": len(vehicles),
        "vehicles": [
            {
                "id": str(vehicle.id),
                "vehicle_code": vehicle.vehicle_code,
                "vehicle_type": vehicle.vehicle_type,
                "capacity": vehicle.capacity,
                "capacity_unit": vehicle.capacity_unit,
                "current_location_id": (
                    str(vehicle.current_location_id)
                    if vehicle.current_location_id
                    else None
                ),
                "current_location": (
                    vehicle.current_location.code
                    if vehicle.current_location
                    else None
                ),
                "status": vehicle.status,
                "is_active": vehicle.is_active,
                "created_at": vehicle.created_at,
            }
            for vehicle in vehicles
        ],
    }


# ============================================================
# SHIPMENTS
# ============================================================

@router.post("/shipments")
def create_shipment(
    payload: ShipmentCreate,
    db: Session = Depends(get_db),
):
    existing = db.scalar(
        select(Shipment).where(
            Shipment.shipment_code == payload.shipment_code
        )
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Shipment code already exists",
        )

    allowed_statuses = {
        "PLANNED",
        "DISPATCHED",
        "IN_TRANSIT",
        "DELIVERED",
        "DELAYED",
        "CANCELLED",
    }

    if payload.status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid shipment status. "
                f"Allowed values: {sorted(allowed_statuses)}"
            ),
        )

    item = db.get(Item, payload.item_id)

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Item not found",
        )

    source = db.get(
        Location,
        payload.source_location_id,
    )

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source location not found",
        )

    destination = db.get(
        Location,
        payload.destination_location_id,
    )

    if not destination:
        raise HTTPException(
            status_code=404,
            detail="Destination location not found",
        )

    if (
        payload.source_location_id
        == payload.destination_location_id
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Source and destination locations "
                "must be different"
            ),
        )

    vehicle = None

    if payload.vehicle_id:
        vehicle = db.get(
            Vehicle,
            payload.vehicle_id,
        )

        if not vehicle:
            raise HTTPException(
                status_code=404,
                detail="Vehicle not found",
            )

        if not vehicle.is_active:
            raise HTTPException(
                status_code=400,
                detail="Vehicle is inactive",
            )

        if payload.quantity > vehicle.capacity:
            raise HTTPException(
                status_code=400,
                detail="Shipment quantity exceeds vehicle capacity",
            )

    shipment = Shipment(
        shipment_code=payload.shipment_code,
        item_id=payload.item_id,
        quantity=payload.quantity,
        source_location_id=payload.source_location_id,
        destination_location_id=payload.destination_location_id,
        vehicle_id=payload.vehicle_id,
        status=payload.status,
        planned_departure=payload.planned_departure,
        estimated_arrival=payload.estimated_arrival,
        notes=payload.notes,
    )

    db.add(shipment)
    db.commit()
    db.refresh(shipment)

    return {
        "id": str(shipment.id),
        "shipment_code": shipment.shipment_code,
        "item_code": item.item_code,
        "item_name": item.name,
        "quantity": shipment.quantity,
        "source_location": source.code,
        "destination_location": destination.code,
        "vehicle_code": (
            vehicle.vehicle_code
            if vehicle
            else None
        ),
        "status": shipment.status,
        "planned_departure": shipment.planned_departure,
        "estimated_arrival": shipment.estimated_arrival,
        "actual_departure": shipment.actual_departure,
        "actual_arrival": shipment.actual_arrival,
        "notes": shipment.notes,
        "created_at": shipment.created_at,
    }


@router.get("/shipments")
def list_shipments(
    status: Optional[str] = Query(default=None),
    vehicle_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    query = select(Shipment)

    if status:
        query = query.where(
            Shipment.status == status
        )

    if vehicle_id:
        query = query.where(
            Shipment.vehicle_id == vehicle_id
        )

    shipments = db.scalars(
        query.order_by(
            Shipment.created_at.desc()
        )
    ).all()

    return {
        "count": len(shipments),
        "shipments": [
            {
                "id": str(shipment.id),
                "shipment_code": shipment.shipment_code,
                "item_code": shipment.item.item_code,
                "item_name": shipment.item.name,
                "quantity": shipment.quantity,
                "source_location": (
                    shipment.source_location.code
                ),
                "destination_location": (
                    shipment.destination_location.code
                ),
                "vehicle_code": (
                    shipment.vehicle.vehicle_code
                    if shipment.vehicle
                    else None
                ),
                "status": shipment.status,
                "planned_departure": (
                    shipment.planned_departure
                ),
                "actual_departure": (
                    shipment.actual_departure
                ),
                "estimated_arrival": (
                    shipment.estimated_arrival
                ),
                "actual_arrival": (
                    shipment.actual_arrival
                ),
                "notes": shipment.notes,
                "created_at": shipment.created_at,
            }
            for shipment in shipments
        ],
    }


@router.patch("/shipments/{shipment_id}/status")
def update_shipment_status(
    shipment_id: str,
    payload: ShipmentStatusUpdate,
    db: Session = Depends(get_db),
):
    allowed_statuses = {
        "PLANNED",
        "DISPATCHED",
        "IN_TRANSIT",
        "DELIVERED",
        "DELAYED",
        "CANCELLED",
    }

    if payload.status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid shipment status. "
                f"Allowed values: {sorted(allowed_statuses)}"
            ),
        )

    shipment = db.get(
        Shipment,
        shipment_id,
    )

    if not shipment:
        raise HTTPException(
            status_code=404,
            detail="Shipment not found",
        )

    now = datetime.now().astimezone()

    if (
        payload.status == "DISPATCHED"
        and shipment.actual_departure is None
    ):
        shipment.actual_departure = now

    if (
        payload.status == "DELIVERED"
        and shipment.actual_arrival is None
    ):
        shipment.actual_arrival = now

    shipment.status = payload.status

    db.commit()
    db.refresh(shipment)

    return {
        "id": str(shipment.id),
        "shipment_code": shipment.shipment_code,
        "status": shipment.status,
        "actual_departure": shipment.actual_departure,
        "actual_arrival": shipment.actual_arrival,
        "updated_at": shipment.updated_at,
    }

# ============================================================
# SUPPLIERS
# ============================================================

@router.post("/suppliers")
def create_supplier(payload: SupplierCreate, db: Session = Depends(get_db)):
    existing = db.scalar(select(Supplier).where(Supplier.supplier_code == payload.supplier_code))
    if existing:
        raise HTTPException(status_code=409, detail="Supplier code already exists")
    allowed_statuses = {"ACTIVE", "INACTIVE", "SUSPENDED"}
    if payload.status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid supplier status. Allowed values: {sorted(allowed_statuses)}")
    supplier = Supplier(supplier_code=payload.supplier_code, name=payload.name, supplier_type=payload.supplier_type, contact_details=payload.contact_details, location_id=payload.location_id, status=payload.status)
    db.add(supplier); db.commit(); db.refresh(supplier)
    return {"id": str(supplier.id), "supplier_code": supplier.supplier_code, "name": supplier.name, "supplier_type": supplier.supplier_type, "contact_details": supplier.contact_details, "location_id": str(supplier.location_id) if supplier.location_id else None, "status": supplier.status, "is_active": supplier.is_active, "created_at": supplier.created_at}

@router.get("/suppliers")
def list_suppliers(status: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    query = select(Supplier)
    if status: query = query.where(Supplier.status == status)
    suppliers = db.scalars(query.order_by(Supplier.supplier_code)).all()
    return {"count": len(suppliers), "suppliers": [{"id": str(s.id), "supplier_code": s.supplier_code, "name": s.name, "supplier_type": s.supplier_type, "contact_details": s.contact_details, "location_id": str(s.location_id) if s.location_id else None, "status": s.status, "is_active": s.is_active, "created_at": s.created_at} for s in suppliers]}

# ============================================================
# MAINTENANCE
# ============================================================

@router.post("/maintenance")
def create_maintenance(payload: MaintenanceCreate, db: Session = Depends(get_db)):
    vehicle = db.get(Vehicle, payload.vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    allowed_statuses = {"SCHEDULED", "IN_PROGRESS", "COMPLETED", "CANCELLED"}
    if payload.status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid maintenance status. Allowed values: {sorted(allowed_statuses)}")
    if payload.completed_date and payload.scheduled_date and payload.completed_date < payload.scheduled_date:
        raise HTTPException(status_code=400, detail="completed_date cannot be before scheduled_date")
    record = MaintenanceRecord(vehicle_id=payload.vehicle_id, maintenance_type=payload.maintenance_type, status=payload.status, scheduled_date=payload.scheduled_date, completed_date=payload.completed_date, description=payload.description, cost=payload.cost)
    db.add(record); db.commit(); db.refresh(record)
    return {"id": str(record.id), "vehicle_id": str(record.vehicle_id), "vehicle_code": vehicle.vehicle_code, "maintenance_type": record.maintenance_type, "status": record.status, "scheduled_date": record.scheduled_date, "completed_date": record.completed_date, "description": record.description, "cost": record.cost, "created_at": record.created_at}

@router.get("/maintenance")
def list_maintenance(vehicle_id: Optional[str] = Query(default=None), status: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    query = select(MaintenanceRecord)
    if vehicle_id: query = query.where(MaintenanceRecord.vehicle_id == vehicle_id)
    if status: query = query.where(MaintenanceRecord.status == status)
    records = db.scalars(query.order_by(MaintenanceRecord.created_at.desc())).all()
    return {"count": len(records), "maintenance": [{"id": str(r.id), "vehicle_id": str(r.vehicle_id), "vehicle_code": r.vehicle.vehicle_code, "maintenance_type": r.maintenance_type, "status": r.status, "scheduled_date": r.scheduled_date, "completed_date": r.completed_date, "description": r.description, "cost": r.cost, "created_at": r.created_at} for r in records]}

@router.patch("/maintenance/{maintenance_id}/status")
def update_maintenance_status(maintenance_id: str, payload: MaintenanceStatusUpdate, db: Session = Depends(get_db)):
    allowed_statuses = {"SCHEDULED", "IN_PROGRESS", "COMPLETED", "CANCELLED"}
    if payload.status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid maintenance status. Allowed values: {sorted(allowed_statuses)}")
    record = db.get(MaintenanceRecord, maintenance_id)
    if not record:
        raise HTTPException(status_code=404, detail="Maintenance record not found")
    record.status = payload.status
    if payload.status == "COMPLETED" and record.completed_date is None:
        record.completed_date = date.today()
    db.commit(); db.refresh(record)
    return {"id": str(record.id), "vehicle_id": str(record.vehicle_id), "vehicle_code": record.vehicle.vehicle_code, "maintenance_type": record.maintenance_type, "status": record.status, "scheduled_date": record.scheduled_date, "completed_date": record.completed_date, "updated_at": record.updated_at}


# ============================================================
# LOGISTICS EVENTS
# ============================================================

@router.post("/events")
def create_logistics_event(
    payload: LogisticsEventCreate,
    db: Session = Depends(get_db),
):
    allowed_event_types = {
        "LOW_STOCK",
        "DEMAND_SPIKE",
        "VEHICLE_FAILURE",
        "SHIPMENT_DELAY",
        "WEATHER_ALERT",
        "MAINTENANCE_DUE",
        "DATA_QUALITY",
    }

    allowed_severities = {
        "INFO",
        "WARNING",
        "CRITICAL",
    }

    if payload.event_type not in allowed_event_types:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid event type. "
                f"Allowed values: {sorted(allowed_event_types)}"
            ),
        )

    if payload.severity not in allowed_severities:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid severity. "
                f"Allowed values: {sorted(allowed_severities)}"
            ),
        )

    if payload.location_id:
        location = db.get(Location, payload.location_id)
        if not location:
            raise HTTPException(
                status_code=404,
                detail="Location not found",
            )

    if payload.vehicle_id:
        vehicle = db.get(Vehicle, payload.vehicle_id)
        if not vehicle:
            raise HTTPException(
                status_code=404,
                detail="Vehicle not found",
            )

    if payload.shipment_id:
        shipment = db.get(Shipment, payload.shipment_id)
        if not shipment:
            raise HTTPException(
                status_code=404,
                detail="Shipment not found",
            )

    event = LogisticsEvent(
        event_type=payload.event_type,
        severity=payload.severity,
        title=payload.title,
        description=payload.description,
        location_id=payload.location_id,
        vehicle_id=payload.vehicle_id,
        shipment_id=payload.shipment_id,
    )

    db.add(event)
    db.commit()
    db.refresh(event)

    return {
        "id": str(event.id),
        "event_type": event.event_type,
        "severity": event.severity,
        "title": event.title,
        "description": event.description,
        "location_id": (
            str(event.location_id)
            if event.location_id
            else None
        ),
        "vehicle_id": (
            str(event.vehicle_id)
            if event.vehicle_id
            else None
        ),
        "shipment_id": (
            str(event.shipment_id)
            if event.shipment_id
            else None
        ),
        "is_resolved": event.is_resolved,
        "resolved_at": event.resolved_at,
        "created_at": event.created_at,
    }


@router.get("/events")
def list_logistics_events(
    event_type: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    is_resolved: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
):
    query = select(LogisticsEvent)

    if event_type:
        query = query.where(
            LogisticsEvent.event_type == event_type
        )

    if severity:
        query = query.where(
            LogisticsEvent.severity == severity
        )

    if is_resolved is not None:
        query = query.where(
            LogisticsEvent.is_resolved == is_resolved
        )

    events = db.scalars(
        query.order_by(
            LogisticsEvent.created_at.desc()
        )
    ).all()

    return {
        "count": len(events),
        "events": [
            {
                "id": str(event.id),
                "event_type": event.event_type,
                "severity": event.severity,
                "title": event.title,
                "description": event.description,
                "location_id": (
                    str(event.location_id)
                    if event.location_id
                    else None
                ),
                "vehicle_id": (
                    str(event.vehicle_id)
                    if event.vehicle_id
                    else None
                ),
                "shipment_id": (
                    str(event.shipment_id)
                    if event.shipment_id
                    else None
                ),
                "is_resolved": event.is_resolved,
                "resolved_at": event.resolved_at,
                "created_at": event.created_at,
            }
            for event in events
        ],
    }


@router.patch("/events/{event_id}/resolve")
def resolve_logistics_event(
    event_id: str,
    db: Session = Depends(get_db),
):
    event = db.get(
        LogisticsEvent,
        event_id,
    )

    if not event:
        raise HTTPException(
            status_code=404,
            detail="Logistics event not found",
        )

    if not event.is_resolved:
        event.is_resolved = True
        event.resolved_at = datetime.now().astimezone()

        db.commit()
        db.refresh(event)

    return {
        "id": str(event.id),
        "event_type": event.event_type,
        "severity": event.severity,
        "title": event.title,
        "is_resolved": event.is_resolved,
        "resolved_at": event.resolved_at,
        "updated_at": event.updated_at,
    }

