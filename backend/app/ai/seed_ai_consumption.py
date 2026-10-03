from datetime import date, timedelta
import random
import uuid

from app.db.session import SessionLocal
from app.models.consumption import ConsumptionRecord


ITEM_ID = uuid.UUID("5fdf0f89-4688-405f-9316-82d72d8a9060")
LOCATION_ID = uuid.UUID("19f23720-b5b7-4153-91d9-3f9bc492240b")


def main():
    db = SessionLocal()

    try:
        random.seed(42)

        start_date = date.today() - timedelta(days=29)

        records = []

        for day in range(30):
            consumption_date = start_date + timedelta(days=day)

            base_usage = 35 + (day * 0.25)
            variation = random.uniform(-5, 5)

            quantity = round(base_usage + variation, 2)

            records.append(
                ConsumptionRecord(
                    item_id=ITEM_ID,
                    location_id=LOCATION_ID,
                    consumption_date=consumption_date,
                    quantity=quantity,
                )
            )

        db.add_all(records)
        db.commit()

        print(f"Inserted {len(records)} synthetic consumption records.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
    