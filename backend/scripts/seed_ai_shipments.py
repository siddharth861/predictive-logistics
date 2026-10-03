from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.item import Item
from app.models.location import Location
from app.models.shipment import Shipment
from app.models.vehicle import Vehicle


RANDOM_SEED = 42
random.seed(RANDOM_SEED)


def main() -> None:
    db = SessionLocal()

    try:
        item = db.scalar(
            select(Item).where(
                Item.item_code == "F001"
            )
        )

        source = db.scalar(
            select(Location).where(
                Location.code == "DEPOT-A"
            )
        )

        destination = db.scalar(
            select(Location).where(
                Location.code == "FORWARD-B"
            )
        )

        vehicle = db.scalar(
            select(Vehicle).where(
                Vehicle.vehicle_code == "TRK-001"
            )
        )

        if not item:
            raise ValueError("Item F001 not found.")

        if not source:
            raise ValueError("Location DEPOT-A not found.")

        if not destination:
            raise ValueError("Location FORWARD-B not found.")

        if not vehicle:
            raise ValueError("Vehicle TRK-001 not found.")

        existing_codes = set(
            db.scalars(
                select(Shipment.shipment_code)
            ).all()
        )

        created = 0

        for index in range(1, 31):
            shipment_code = f"AI-SHP-{index:03d}"

            if shipment_code in existing_codes:
                continue

            days_ago = 30 - index

            planned_departure = (
                datetime.now(timezone.utc)
                - timedelta(days=days_ago)
            )

            base_hours = 6.0

            variation = random.uniform(
                -0.75,
                1.25,
            )

            delay = (
                random.uniform(2.0, 6.0)
                if random.random() < 0.20
                else 0.0
            )

            actual_duration = (
                base_hours
                + variation
                + delay
            )

            actual_departure = (
                planned_departure
                + timedelta(
                    minutes=random.randint(0, 60)
                )
            )

            estimated_arrival = (
                planned_departure
                + timedelta(
                    hours=base_hours
                )
            )

            actual_arrival = (
                actual_departure
                + timedelta(
                    hours=actual_duration
                )
            )

            shipment = Shipment(
                shipment_code=shipment_code,
                item_id=item.id,
                quantity=random.uniform(
                    50,
                    500,
                ),
                source_location_id=source.id,
                destination_location_id=destination.id,
                vehicle_id=vehicle.id,
                status="DELIVERED",
                planned_departure=planned_departure,
                actual_departure=actual_departure,
                estimated_arrival=estimated_arrival,
                actual_arrival=actual_arrival,
                notes=(
                    "Synthetic AI training shipment. "
                    "Not operational data."
                ),
            )

            db.add(shipment)
            created += 1

        db.commit()

        print(
            f"Created {created} synthetic shipment records."
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()