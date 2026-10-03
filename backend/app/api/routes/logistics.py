from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.elements import WKTElement
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.models.inventory import Inventory
from app.models.item import Item
from app.models.location import Location


router = APIRouter(
    prefix="/api/logistics",
    tags=["Logistics"],
)


# -------------------------------------------------------------------
# LOCATIONS
# -------------------------------------------------------------------

@router.post("/locations")
def create_location(
    code: str,
    name: str,
    location_type: str,
    latitude: float,
    longitude: float,
    description: str | None = None,
    db: Session = Depends(get_db),
):
    if not -90 <= latitude <= 90:
        raise HTTPException(
            status_code=400,
            detail="Latitude must be between -90 and 90.",
        )

    if not -180 <= longitude <= 180:
        raise HTTPException(
            status_code=400,
            detail="Longitude must be between -180 and 180.",
        )

    existing_location = (
        db.query(Location)
        .filter(Location.code == code)
        .first()
    )

    if existing_location:
        raise HTTPException(
            status_code=409,
            detail="Location code already exists.",
        )

    location = Location(
        code=code,
        name=name,
        description=description,
        location_type=location_type,
        geometry=WKTElement(
            f"POINT({longitude} {latitude})",
            srid=4326,
        ),
        is_active=True,
    )

    db.add(location)

    try:
        db.commit()
        db.refresh(location)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Location code already exists.",
        )

    return {
        "id": str(location.id),
        "code": location.code,
        "name": location.name,
        "description": location.description,
        "location_type": location.location_type,
        "latitude": latitude,
        "longitude": longitude,
        "is_active": location.is_active,
        "created_at": location.created_at.isoformat(),
    }


@router.get("/locations")
def list_locations(
    db: Session = Depends(get_db),
):
    locations = (
        db.query(Location)
        .order_by(Location.created_at.desc())
        .all()
    )

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
                "created_at": location.created_at.isoformat(),
            }
            for location in locations
        ],
    }


# -------------------------------------------------------------------
# ITEMS
# -------------------------------------------------------------------

@router.post("/items")
def create_item(
    item_code: str,
    name: str,
    category: str | None = None,
    unit: str = "UNIT",
    description: str | None = None,
    db: Session = Depends(get_db),
):
    existing_item = (
        db.query(Item)
        .filter(Item.item_code == item_code)
        .first()
    )

    if existing_item:
        raise HTTPException(
            status_code=409,
            detail="Item code already exists.",
        )

    item = Item(
        item_code=item_code,
        name=name,
        category=category,
        unit=unit,
        description=description,
        is_active=True,
    )

    db.add(item)

    try:
        db.commit()
        db.refresh(item)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Item code already exists.",
        )

    return {
        "id": str(item.id),
        "item_code": item.item_code,
        "name": item.name,
        "category": item.category,
        "unit": item.unit,
        "description": item.description,
        "is_active": item.is_active,
        "created_at": item.created_at.isoformat(),
    }


@router.get("/items")
def list_items(
    db: Session = Depends(get_db),
):
    items = (
        db.query(Item)
        .order_by(Item.created_at.desc())
        .all()
    )

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
                "created_at": item.created_at.isoformat(),
            }
            for item in items
        ],
    }


# -------------------------------------------------------------------
# INVENTORY
# -------------------------------------------------------------------

@router.post("/inventory")
def create_inventory(
    item_id: UUID,
    location_id: UUID,
    quantity: float,
    minimum_stock: float = 0,
    maximum_stock: float | None = None,
    db: Session = Depends(get_db),
):
    item = (
        db.query(Item)
        .filter(Item.id == item_id)
        .first()
    )

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Item not found.",
        )

    location = (
        db.query(Location)
        .filter(Location.id == location_id)
        .first()
    )

    if not location:
        raise HTTPException(
            status_code=404,
            detail="Location not found.",
        )

    if not location.is_active:
        raise HTTPException(
            status_code=400,
            detail="Location is inactive.",
        )

    if quantity < 0:
        raise HTTPException(
            status_code=400,
            detail="Quantity cannot be negative.",
        )

    if minimum_stock < 0:
        raise HTTPException(
            status_code=400,
            detail="Minimum stock cannot be negative.",
        )

    if maximum_stock is not None:
        if maximum_stock < 0:
            raise HTTPException(
                status_code=400,
                detail="Maximum stock cannot be negative.",
            )

        if maximum_stock < minimum_stock:
            raise HTTPException(
                status_code=400,
                detail="Maximum stock cannot be less than minimum stock.",
            )

    existing_inventory = (
        db.query(Inventory)
        .filter(
            Inventory.item_id == item_id,
            Inventory.location_id == location_id,
        )
        .first()
    )

    if existing_inventory:
        raise HTTPException(
            status_code=409,
            detail="Inventory record already exists for this item and location.",
        )

    inventory = Inventory(
        item_id=item_id,
        location_id=location_id,
        quantity=quantity,
        minimum_stock=minimum_stock,
        maximum_stock=maximum_stock,
    )

    db.add(inventory)

    try:
        db.commit()
        db.refresh(inventory)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Inventory record already exists for this item and location.",
        )

    return {
        "id": str(inventory.id),
        "item_id": str(inventory.item_id),
        "location_id": str(inventory.location_id),
        "quantity": inventory.quantity,
        "minimum_stock": inventory.minimum_stock,
        "maximum_stock": inventory.maximum_stock,
        "created_at": inventory.created_at.isoformat(),
    }


@router.get("/inventory")
def list_inventory(
    db: Session = Depends(get_db),
):
    inventory_records = (
        db.query(Inventory)
        .order_by(Inventory.created_at.desc())
        .all()
    )

    return {
        "count": len(inventory_records),
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
                "created_at": record.created_at.isoformat(),
                "updated_at": record.updated_at.isoformat(),
            }
            for record in inventory_records
        ],
    }