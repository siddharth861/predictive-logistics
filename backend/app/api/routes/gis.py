from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.item import Item
from app.models.inventory import Inventory
from app.models.location import Location
from app.models.logistics_event import LogisticsEvent
from app.models.shipment import Shipment
from app.models.vehicle import Vehicle

from app.api.routes.ai import (
    get_consumption_forecast,
    get_stockout_risk,
    get_supply_risk,
)


router = APIRouter(
    prefix="/api/gis",
    tags=["GIS"],
)


def get_coordinates(
    db: Session,
    location_id,
):
    result = db.execute(
        text(
            """
            SELECT
                ST_X(geometry) AS longitude,
                ST_Y(geometry) AS latitude
            FROM locations
            WHERE id = :location_id
            """
        ),
        {
            "location_id": str(location_id),
        },
    ).mappings().first()

    if not result:
        return None

    if (
        result["longitude"] is None
        or result["latitude"] is None
    ):
        return None

    return {
        "longitude": float(result["longitude"]),
        "latitude": float(result["latitude"]),
    }


def get_distance_km(
    db: Session,
    source_location_id,
    destination_location_id,
):
    result = db.execute(
        text(
            """
            SELECT
                ST_Distance(
                    source.geometry::geography,
                    destination.geometry::geography
                ) / 1000.0 AS distance_km
            FROM locations AS source
            CROSS JOIN locations AS destination
            WHERE source.id = :source_id
              AND destination.id = :destination_id
              AND source.geometry IS NOT NULL
              AND destination.geometry IS NOT NULL
            """
        ),
        {
            "source_id": str(source_location_id),
            "destination_id": str(destination_location_id),
        },
    ).mappings().first()

    if result is None:
        return None

    return float(result["distance_km"])


def get_route_risk(
    distance_km: float,
    vehicle: Vehicle | None,
    shipment: Shipment | None,
):
    risks = []
    warnings = []
    constraints = []

    # Distance constraint
    if distance_km > 500:
        risks.append("LONG_DISTANCE")
        warnings.append(
            "Route distance exceeds 500 km."
        )

    elif distance_km > 200:
        risks.append("EXTENDED_DISTANCE")
        warnings.append(
            "Route distance exceeds 200 km."
        )

    # Vehicle checks
    if vehicle is not None:

        if not vehicle.is_active:
            risks.append("INACTIVE_VEHICLE")
            warnings.append(
                "Selected vehicle is inactive."
            )

        if vehicle.status != "AVAILABLE":
            risks.append("VEHICLE_NOT_AVAILABLE")
            warnings.append(
                f"Vehicle status is {vehicle.status}."
            )

        if (
            shipment is not None
            and vehicle.capacity is not None
            and shipment.quantity > vehicle.capacity
        ):
            risks.append("CAPACITY_EXCEEDED")
            warnings.append(
                "Shipment quantity exceeds vehicle capacity."
            )
            constraints.append(
                "Vehicle capacity is insufficient."
            )

    # Shipment checks
    if shipment is not None:

        if shipment.quantity <= 0:
            risks.append("INVALID_QUANTITY")
            warnings.append(
                "Shipment quantity must be greater than zero."
            )

        if shipment.source_location_id == shipment.destination_location_id:
            risks.append("SAME_SOURCE_DESTINATION")
            warnings.append(
                "Source and destination are identical."
            )

    # Determine overall risk
    if any(
        risk in risks
        for risk in [
            "CAPACITY_EXCEEDED",
            "INACTIVE_VEHICLE",
            "INVALID_QUANTITY",
            "SAME_SOURCE_DESTINATION",
        ]
    ):
        level = "HIGH"

    elif any(
        risk in risks
        for risk in [
            "VEHICLE_NOT_AVAILABLE",
            "LONG_DISTANCE",
        ]
    ):
        level = "MEDIUM"

    elif risks:
        level = "LOW"

    else:
        level = "LOW"

    return {
        "level": level,
        "flags": risks,
        "warnings": warnings,
        "constraints": constraints,
    }


@router.get("/locations")
def get_locations(
    db: Session = Depends(get_db),
):
    locations = db.scalars(
        select(Location)
        .order_by(Location.code)
    ).all()

    return [
        {
            "id": str(location.id),
            "code": location.code,
            "name": location.name,
            "description": location.description,
            "location_type": location.location_type,
            "is_active": location.is_active,
            "coordinates": get_coordinates(
                db,
                location.id,
            ),
        }
        for location in locations
    ]


@router.get("/locations/{location_id}")
def get_location(
    location_id: UUID,
    db: Session = Depends(get_db),
):
    location = db.scalar(
        select(Location).where(
            Location.id == location_id
        )
    )

    if location is None:
        raise HTTPException(
            status_code=404,
            detail="Location not found.",
        )

    return {
        "id": str(location.id),
        "code": location.code,
        "name": location.name,
        "description": location.description,
        "location_type": location.location_type,
        "is_active": location.is_active,
        "coordinates": get_coordinates(
            db,
            location.id,
        ),
    }


@router.get("/locations/nearby")
def get_nearby_locations(
    latitude: float = Query(...),
    longitude: float = Query(...),
    radius_km: float = Query(
        default=50.0,
        gt=0,
        le=1000,
    ),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text(
            """
            SELECT
                id,
                code,
                name,
                location_type,
                ST_X(geometry) AS longitude,
                ST_Y(geometry) AS latitude,
                ST_Distance(
                    geometry::geography,
                    ST_SetSRID(
                        ST_MakePoint(
                            :longitude,
                            :latitude
                        ),
                        4326
                    )::geography
                ) / 1000.0 AS distance_km
            FROM locations
            WHERE geometry IS NOT NULL
            AND ST_DWithin(
                geometry::geography,
                ST_SetSRID(
                    ST_MakePoint(
                        :longitude,
                        :latitude
                    ),
                    4326
                )::geography,
                :radius_m
            )
            ORDER BY distance_km
            """
        ),
        {
            "longitude": longitude,
            "latitude": latitude,
            "radius_m": radius_km * 1000,
        },
    ).mappings().all()

    locations = [
        {
            "id": str(row["id"]),
            "code": row["code"],
            "name": row["name"],
            "location_type": row["location_type"],
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            "distance_km": round(
                float(row["distance_km"]),
                2,
            ),
        }
        for row in rows
    ]

    return {
        "center": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "radius_km": radius_km,
        "count": len(locations),
        "locations": locations,
    }


@router.get("/distance")
def get_distance(
    source_location_id: UUID = Query(...),
    destination_location_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    source = db.scalar(
        select(Location).where(
            Location.id == source_location_id
        )
    )

    destination = db.scalar(
        select(Location).where(
            Location.id == destination_location_id
        )
    )

    if source is None:
        raise HTTPException(
            status_code=404,
            detail="Source location not found.",
        )

    if destination is None:
        raise HTTPException(
            status_code=404,
            detail="Destination location not found.",
        )

    distance_km = get_distance_km(
        db,
        source_location_id,
        destination_location_id,
    )

    if distance_km is None:
        raise HTTPException(
            status_code=400,
            detail="One or both locations do not have spatial coordinates.",
        )

    return {
        "source": {
            "id": str(source.id),
            "code": source.code,
            "name": source.name,
            "coordinates": get_coordinates(
                db,
                source.id,
            ),
        },
        "destination": {
            "id": str(destination.id),
            "code": destination.code,
            "name": destination.name,
            "coordinates": get_coordinates(
                db,
                destination.id,
            ),
        },
        "distance_km": round(
            distance_km,
            3,
        ),
    }


@router.get("/route")
def get_route(
    source_location_id: UUID = Query(...),
    destination_location_id: UUID = Query(...),
    vehicle_id: UUID | None = Query(default=None),
    average_speed_kmh: float = Query(
        default=40.0,
        gt=1,
        le=150,
    ),
    db: Session = Depends(get_db),
):
    source = db.scalar(
        select(Location).where(
            Location.id == source_location_id
        )
    )

    destination = db.scalar(
        select(Location).where(
            Location.id == destination_location_id
        )
    )

    if source is None:
        raise HTTPException(
            status_code=404,
            detail="Source location not found.",
        )

    if destination is None:
        raise HTTPException(
            status_code=404,
            detail="Destination location not found.",
        )

    distance_km = get_distance_km(
        db,
        source_location_id,
        destination_location_id,
    )

    if distance_km is None:
        raise HTTPException(
            status_code=400,
            detail="One or both locations do not have spatial coordinates.",
        )

    vehicle_data = None

    if vehicle_id is not None:
        vehicle = db.scalar(
            select(Vehicle).where(
                Vehicle.id == vehicle_id
            )
        )

        if vehicle is None:
            raise HTTPException(
                status_code=404,
                detail="Vehicle not found.",
            )

        vehicle_data = {
            "id": str(vehicle.id),
            "vehicle_code": vehicle.vehicle_code,
            "vehicle_type": vehicle.vehicle_type,
            "capacity": (
                float(vehicle.capacity)
                if vehicle.capacity is not None
                else None
            ),
            "capacity_unit": vehicle.capacity_unit,
            "status": vehicle.status,
            "current_location_id": (
                str(vehicle.current_location_id)
                if vehicle.current_location_id
                else None
            ),
        }

    estimated_hours = (
        distance_km / average_speed_kmh
    )

    return {
        "source": {
            "id": str(source.id),
            "code": source.code,
            "name": source.name,
            "coordinates": get_coordinates(
                db,
                source.id,
            ),
        },
        "destination": {
            "id": str(destination.id),
            "code": destination.code,
            "name": destination.name,
            "coordinates": get_coordinates(
                db,
                destination.id,
            ),
        },
        "route": {
            "distance_km": round(
                distance_km,
                3,
            ),
            "average_speed_kmh": average_speed_kmh,
            "estimated_travel_hours": round(
                estimated_hours,
                2,
            ),
            "routing_method": "POSTGIS_STRAIGHT_LINE",
            "status": "ESTIMATED",
        },
        "vehicle": vehicle_data,
    }


@router.get("/route-risk")
def get_route_risk_endpoint(
    source_location_id: UUID = Query(...),
    destination_location_id: UUID = Query(...),
    vehicle_id: UUID | None = Query(default=None),
    shipment_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
):
    source = db.scalar(
        select(Location).where(
            Location.id == source_location_id
        )
    )

    destination = db.scalar(
        select(Location).where(
            Location.id == destination_location_id
        )
    )

    if source is None:
        raise HTTPException(
            status_code=404,
            detail="Source location not found.",
        )

    if destination is None:
        raise HTTPException(
            status_code=404,
            detail="Destination location not found.",
        )

    distance_km = get_distance_km(
        db,
        source_location_id,
        destination_location_id,
    )

    if distance_km is None:
        raise HTTPException(
            status_code=400,
            detail="One or both locations do not have spatial coordinates.",
        )

    vehicle = None

    if vehicle_id is not None:
        vehicle = db.scalar(
            select(Vehicle).where(
                Vehicle.id == vehicle_id
            )
        )

        if vehicle is None:
            raise HTTPException(
                status_code=404,
                detail="Vehicle not found.",
            )

    shipment = None

    if shipment_id is not None:
        shipment = db.scalar(
            select(Shipment).where(
                Shipment.id == shipment_id
            )
        )

        if shipment is None:
            raise HTTPException(
                status_code=404,
                detail="Shipment not found.",
            )

        if (
            shipment.source_location_id
            != source_location_id
        ):
            raise HTTPException(
                status_code=400,
                detail="Shipment source does not match route source.",
            )

        if (
            shipment.destination_location_id
            != destination_location_id
        ):
            raise HTTPException(
                status_code=400,
                detail="Shipment destination does not match route destination.",
            )

    risk = get_route_risk(
        distance_km,
        vehicle,
        shipment,
    )

    return {
        "source": {
            "id": str(source.id),
            "code": source.code,
            "name": source.name,
            "coordinates": get_coordinates(
                db,
                source.id,
            ),
        },
        "destination": {
            "id": str(destination.id),
            "code": destination.code,
            "name": destination.name,
            "coordinates": get_coordinates(
                db,
                destination.id,
            ),
        },
        "distance_km": round(
            distance_km,
            3,
        ),
        "vehicle": (
            {
                "id": str(vehicle.id),
                "vehicle_code": vehicle.vehicle_code,
                "vehicle_type": vehicle.vehicle_type,
                "capacity": (
                    float(vehicle.capacity)
                    if vehicle.capacity is not None
                    else None
                ),
                "capacity_unit": vehicle.capacity_unit,
                "status": vehicle.status,
                "is_active": vehicle.is_active,
            }
            if vehicle
            else None
        ),
        "shipment": (
            {
                "id": str(shipment.id),
                "shipment_code": shipment.shipment_code,
                "quantity": float(
                    shipment.quantity
                ),
                "status": shipment.status,
            }
            if shipment
            else None
        ),
        "risk": risk,
    }


@router.get("/operational-layer")
def get_operational_layer(
    db: Session = Depends(get_db),
):
    locations = db.scalars(
        select(Location)
        .where(Location.is_active.is_(True))
        .order_by(Location.code)
    ).all()

    vehicles = db.scalars(
        select(Vehicle)
        .order_by(Vehicle.vehicle_code)
    ).all()

    shipments = db.scalars(
        select(Shipment)
        .order_by(Shipment.created_at.desc())
    ).all()

    events = db.scalars(
        select(LogisticsEvent)
        .where(
            LogisticsEvent.is_resolved.is_(False)
        )
        .order_by(
            LogisticsEvent.created_at.desc()
        )
    ).all()

    location_layers = []

    for location in locations:
        location_layers.append(
            {
                "id": str(location.id),
                "code": location.code,
                "name": location.name,
                "location_type": location.location_type,
                "coordinates": get_coordinates(
                    db,
                    location.id,
                ),
            }
        )

    vehicle_layers = []

    for vehicle in vehicles:
        coordinates = None

        if vehicle.current_location_id:
            coordinates = get_coordinates(
                db,
                vehicle.current_location_id,
            )

        vehicle_layers.append(
            {
                "id": str(vehicle.id),
                "vehicle_code": vehicle.vehicle_code,
                "vehicle_type": vehicle.vehicle_type,
                "status": vehicle.status,
                "capacity": (
                    float(vehicle.capacity)
                    if vehicle.capacity is not None
                    else None
                ),
                "current_location_id": (
                    str(vehicle.current_location_id)
                    if vehicle.current_location_id
                    else None
                ),
                "coordinates": coordinates,
            }
        )

    shipment_layers = []

    for shipment in shipments:
        source_coordinates = get_coordinates(
            db,
            shipment.source_location_id,
        )

        destination_coordinates = get_coordinates(
            db,
            shipment.destination_location_id,
        )

        shipment_layers.append(
            {
                "id": str(shipment.id),
                "shipment_code": shipment.shipment_code,
                "status": shipment.status,
                "quantity": float(
                    shipment.quantity
                ),
                "source": {
                    "location_id": str(
                        shipment.source_location_id
                    ),
                    "coordinates": source_coordinates,
                },
                "destination": {
                    "location_id": str(
                        shipment.destination_location_id
                    ),
                    "coordinates": destination_coordinates,
                },
                "vehicle_id": (
                    str(shipment.vehicle_id)
                    if shipment.vehicle_id
                    else None
                ),
                "planned_departure": (
                    shipment.planned_departure.isoformat()
                    if shipment.planned_departure
                    else None
                ),
                "estimated_arrival": (
                    shipment.estimated_arrival.isoformat()
                    if shipment.estimated_arrival
                    else None
                ),
            }
        )

    event_layers = []

    for event in events:
        coordinates = None

        if event.location_id:
            coordinates = get_coordinates(
                db,
                event.location_id,
            )

        event_layers.append(
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
                "coordinates": coordinates,
                "created_at": (
                    event.created_at.isoformat()
                    if event.created_at
                    else None
                ),
            }
        )

    return {
        "locations": location_layers,
        "vehicles": vehicle_layers,
        "shipments": shipment_layers,
        "events": event_layers,
        "summary": {
            "locations": len(location_layers),
            "vehicles": len(vehicle_layers),
            "shipments": len(shipment_layers),
            "unresolved_events": len(event_layers),
        },
    }


@router.get("/supply-flow")
def get_supply_flow(
    status: str | None = Query(default=None),
    item_id: UUID | None = Query(default=None),
    vehicle_id: UUID | None = Query(default=None),
    source_location_id: UUID | None = Query(default=None),
    destination_location_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = select(Shipment).order_by(
        Shipment.created_at.desc()
    )

    if status is not None:
        query = query.where(
            Shipment.status == status
        )

    if item_id is not None:
        query = query.where(
            Shipment.item_id == item_id
        )

    if vehicle_id is not None:
        query = query.where(
            Shipment.vehicle_id == vehicle_id
        )

    if source_location_id is not None:
        query = query.where(
            Shipment.source_location_id
            == source_location_id
        )

    if destination_location_id is not None:
        query = query.where(
            Shipment.destination_location_id
            == destination_location_id
        )

    shipments = db.scalars(query).all()

    flows = []

    for shipment in shipments:
        source = db.scalar(
            select(Location).where(
                Location.id
                == shipment.source_location_id
            )
        )

        destination = db.scalar(
            select(Location).where(
                Location.id
                == shipment.destination_location_id
            )
        )

        if source is None or destination is None:
            continue

        vehicle = None

        if shipment.vehicle_id is not None:
            vehicle = db.scalar(
                select(Vehicle).where(
                    Vehicle.id
                    == shipment.vehicle_id
                )
            )

        item = db.scalar(
            select(Item).where(
                Item.id == shipment.item_id
            )
        )

        source_coordinates = get_coordinates(
            db,
            source.id,
        )

        destination_coordinates = get_coordinates(
            db,
            destination.id,
        )

        distance_km = get_distance_km(
            db,
            source.id,
            destination.id,
        )

        flows.append(
            {
                "shipment": {
                    "id": str(shipment.id),
                    "code": shipment.shipment_code,
                    "status": shipment.status,
                    "quantity": float(
                        shipment.quantity
                    ),
                    "planned_departure": (
                        shipment.planned_departure.isoformat()
                        if shipment.planned_departure
                        else None
                    ),
                    "actual_departure": (
                        shipment.actual_departure.isoformat()
                        if shipment.actual_departure
                        else None
                    ),
                    "estimated_arrival": (
                        shipment.estimated_arrival.isoformat()
                        if shipment.estimated_arrival
                        else None
                    ),
                    "actual_arrival": (
                        shipment.actual_arrival.isoformat()
                        if shipment.actual_arrival
                        else None
                    ),
                },
                "item": (
                    {
                        "id": str(item.id),
                        "code": item.item_code,
                        "name": item.name,
                        "category": item.category,
                        "unit": item.unit,
                    }
                    if item
                    else {
                        "id": str(
                            shipment.item_id
                        )
                    }
                ),
                "source": {
                    "id": str(source.id),
                    "code": source.code,
                    "name": source.name,
                    "location_type": source.location_type,
                    "coordinates": source_coordinates,
                },
                "destination": {
                    "id": str(destination.id),
                    "code": destination.code,
                    "name": destination.name,
                    "location_type": destination.location_type,
                    "coordinates": destination_coordinates,
                },
                "vehicle": (
                    {
                        "id": str(vehicle.id),
                        "code": vehicle.vehicle_code,
                        "type": vehicle.vehicle_type,
                        "status": vehicle.status,
                        "capacity": (
                            float(vehicle.capacity)
                            if vehicle.capacity
                            is not None
                            else None
                        ),
                        "capacity_unit": (
                            vehicle.capacity_unit
                        ),
                    }
                    if vehicle
                    else None
                ),
                "route": {
                    "distance_km": (
                        round(
                            distance_km,
                            3,
                        )
                        if distance_km is not None
                        else None
                    ),
                },
            }
        )

    return {
        "count": len(flows),
        "flows": flows,
    }


@router.get("/operational-intelligence")
def get_operational_intelligence(
    item_id: UUID | None = Query(default=None),
    location_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Combine GIS operational context with AI logistics intelligence.

    When item_id and location_id are supplied, the endpoint returns
    intelligence for that specific item/location pair.

    When they are omitted, the endpoint discovers item/location pairs
    from the current inventory table.
    """

    # ------------------------------------------------------------
    # Determine item/location pairs
    # ------------------------------------------------------------

    pairs = []

    if item_id is not None and location_id is not None:
        pairs.append(
            {
                "item_id": item_id,
                "location_id": location_id,
            }
        )

    elif item_id is not None:
        inventories = db.scalars(
            select(Inventory).where(
                Inventory.item_id == item_id
            )
        ).all()

        for inventory in inventories:
            pairs.append(
                {
                    "item_id": inventory.item_id,
                    "location_id": inventory.location_id,
                }
            )

    elif location_id is not None:
        inventories = db.scalars(
            select(Inventory).where(
                Inventory.location_id
                == location_id
            )
        ).all()

        for inventory in inventories:
            pairs.append(
                {
                    "item_id": inventory.item_id,
                    "location_id": inventory.location_id,
                }
            )

    else:
        inventories = db.scalars(
            select(Inventory)
            .order_by(
                Inventory.updated_at.desc()
            )
        ).all()

        seen = set()

        for inventory in inventories:
            pair_key = (
                str(inventory.item_id),
                str(inventory.location_id),
            )

            if pair_key in seen:
                continue

            seen.add(pair_key)

            pairs.append(
                {
                    "item_id": inventory.item_id,
                    "location_id": inventory.location_id,
                }
            )

    # ------------------------------------------------------------
    # Build intelligence records
    # ------------------------------------------------------------

    intelligence = []

    for pair in pairs:

        current_item_id = pair["item_id"]
        current_location_id = pair["location_id"]

        item = db.scalar(
            select(Item).where(
                Item.id == current_item_id
            )
        )

        location = db.scalar(
            select(Location).where(
                Location.id == current_location_id
            )
        )

        inventory = db.scalar(
            select(Inventory).where(
                Inventory.item_id
                == current_item_id,
                Inventory.location_id
                == current_location_id,
            )
        )

        if item is None or location is None:
            continue

        # --------------------------------------------------------
        # AI predictions
        # --------------------------------------------------------

        try:
            forecast = get_consumption_forecast(
                current_item_id,
                current_location_id,
                db,
            )

            stockout = get_stockout_risk(
                current_item_id,
                current_location_id,
                db,
            )

            supply_risk = get_supply_risk(
                current_item_id,
                current_location_id,
                db,
            )

        except HTTPException as exc:
            # A location/item pair may exist in inventory but
            # not have enough historical consumption data yet.
            intelligence.append(
                {
                    "item": {
                        "id": str(item.id),
                        "code": item.item_code,
                        "name": item.name,
                        "category": item.category,
                        "unit": item.unit,
                    },
                    "location": {
                        "id": str(location.id),
                        "code": location.code,
                        "name": location.name,
                        "location_type": location.location_type,
                        "coordinates": get_coordinates(
                            db,
                            location.id,
                        ),
                    },
                    "inventory": (
                        {
                            "quantity": float(
                                inventory.quantity
                            ),
                            "minimum_stock": float(
                                inventory.minimum_stock
                            ),
                            "maximum_stock": (
                                float(
                                    inventory.maximum_stock
                                )
                                if inventory.maximum_stock
                                is not None
                                else None
                            ),
                        }
                        if inventory
                        else None
                    ),
                    "ai": {
                        "available": False,
                        "error": str(exc.detail),
                    },
                }
            )

            continue

        # --------------------------------------------------------
        # GIS supply-flow context
        # --------------------------------------------------------

        related_shipments = db.scalars(
            select(Shipment)
            .where(
                (
                    Shipment.source_location_id
                    == current_location_id
                )
                |
                (
                    Shipment.destination_location_id
                    == current_location_id
                )
            )
            .order_by(
                Shipment.created_at.desc()
            )
        ).all()

        shipment_layers = []

        for shipment in related_shipments:

            source = db.scalar(
                select(Location).where(
                    Location.id
                    == shipment.source_location_id
                )
            )

            destination = db.scalar(
                select(Location).where(
                    Location.id
                    == shipment.destination_location_id
                )
            )

            if source is None or destination is None:
                continue

            distance_km = get_distance_km(
                db,
                source.id,
                destination.id,
            )

            vehicle = None

            if shipment.vehicle_id is not None:
                vehicle = db.scalar(
                    select(Vehicle).where(
                        Vehicle.id
                        == shipment.vehicle_id
                    )
                )

            shipment_layers.append(
                {
                    "id": str(shipment.id),
                    "code": shipment.shipment_code,
                    "status": shipment.status,
                    "quantity": float(
                        shipment.quantity
                    ),
                    "source": {
                        "id": str(source.id),
                        "code": source.code,
                        "name": source.name,
                        "coordinates": get_coordinates(
                            db,
                            source.id,
                        ),
                    },
                    "destination": {
                        "id": str(destination.id),
                        "code": destination.code,
                        "name": destination.name,
                        "coordinates": get_coordinates(
                            db,
                            destination.id,
                        ),
                    },
                    "vehicle": (
                        {
                            "id": str(vehicle.id),
                            "code": vehicle.vehicle_code,
                            "status": vehicle.status,
                        }
                        if vehicle
                        else None
                    ),
                    "route": {
                        "distance_km": (
                            round(
                                distance_km,
                                3,
                            )
                            if distance_km is not None
                            else None
                        ),
                    },
                }
            )

        # --------------------------------------------------------
        # Final integrated record
        # --------------------------------------------------------

        intelligence.append(
            {
                "item": {
                    "id": str(item.id),
                    "code": item.item_code,
                    "name": item.name,
                    "category": item.category,
                    "unit": item.unit,
                },
                "location": {
                    "id": str(location.id),
                    "code": location.code,
                    "name": location.name,
                    "location_type": location.location_type,
                    "coordinates": get_coordinates(
                        db,
                        location.id,
                    ),
                },
                "inventory": (
                    {
                        "quantity": float(
                            inventory.quantity
                        ),
                        "minimum_stock": float(
                            inventory.minimum_stock
                        ),
                        "maximum_stock": (
                            float(
                                inventory.maximum_stock
                            )
                            if inventory.maximum_stock
                            is not None
                            else None
                        ),
                    }
                    if inventory
                    else None
                ),
                "ai": {
                    "available": True,
                    "forecast": forecast,
                    "stockout": stockout,
                    "supply_risk": supply_risk,
                },
                "gis": {
                    "related_shipments": shipment_layers,
                    "related_shipment_count": len(
                        shipment_layers
                    ),
                },
            }
        )

    return {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "count": len(intelligence),
        "intelligence": intelligence,
    }