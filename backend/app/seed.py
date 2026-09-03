"""Seed the demo dataset: 3 farms near Juja / JKUAT + 2 partner API clients.

    python -m app.seed            # seed if empty
    python -m app.seed --reset    # drop everything and reseed
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, SessionLocal, engine, init_db
from app.models import ApiClient, Farm, Farmer

log = logging.getLogger("farmshield.seed")

# Planting dates are relative to today so the demo always lands in the intended stages.
DEMO_FARMERS = [
    {"name": "Wanjiku Kamau", "phone": "+254711000001", "language": "sw"},
    {"name": "Otieno Odhiambo", "phone": "+254711000002", "language": "en"},
    {"name": "Amina Hassan", "phone": "+254711000003", "language": "sw"},
]
DEMO_FARMS = [
    # maize at flowering (day 62 of 125): the HIGH-risk hero farm under a dry spell
    {"farmer_phone": "+254711000001", "name": "Kamau Maize Plot", "crop": "maize", "days_ago": 62, "lat": -1.0980, "lon": 37.0120, "area_ha": 0.8},
    # beans at vegetative (day 25 of 90): MEDIUM
    {"farmer_phone": "+254711000002", "name": "Odhiambo Beans Field", "crop": "beans", "days_ago": 25, "lat": -1.1020, "lon": 37.0185, "area_ha": 0.5},
    # kale planted 5 days ago after rain: LOW
    {"farmer_phone": "+254711000003", "name": "Amina Sukuma Garden", "crop": "kale", "days_ago": 5, "lat": -1.0935, "lon": 37.0090, "area_ha": 0.2},
]
DEMO_CLIENTS = [
    {"name": "acme-insurance", "api_key": "fs_demo_acme_insurance_2026", "organisation_type": "insurer"},
    {"name": "harvest-sacco", "api_key": "fs_demo_harvest_sacco_2026", "organisation_type": "sacco"},
]


def seed(db: Session, today: date | None = None) -> dict[str, int]:
    """Insert demo rows that are missing (idempotent). Returns counts inserted."""
    today = today or date.today()
    inserted = {"farmers": 0, "farms": 0, "api_clients": 0}

    farmers_by_phone: dict[str, Farmer] = {}
    for f in DEMO_FARMERS:
        existing = db.scalar(select(Farmer).where(Farmer.phone == f["phone"]))
        if existing is None:
            existing = Farmer(**f)
            db.add(existing)
            inserted["farmers"] += 1
        farmers_by_phone[f["phone"]] = existing
    db.flush()

    for fm in DEMO_FARMS:
        if db.scalar(select(Farm).where(Farm.name == fm["name"])) is None:
            db.add(
                Farm(
                    farmer_id=farmers_by_phone[fm["farmer_phone"]].id,
                    name=fm["name"],
                    crop=fm["crop"],
                    planting_date=today - timedelta(days=fm["days_ago"]),
                    lat=fm["lat"],
                    lon=fm["lon"],
                    area_ha=fm["area_ha"],
                    county="Kiambu",
                )
            )
            inserted["farms"] += 1

    for c in DEMO_CLIENTS:
        if db.scalar(select(ApiClient).where(ApiClient.name == c["name"])) is None:
            db.add(ApiClient(**c))
            inserted["api_clients"] += 1

    db.commit()
    return inserted


def seed_if_empty() -> None:
    init_db()
    with SessionLocal() as db:
        if db.scalar(select(Farm.id).limit(1)) is None:
            counts = seed(db)
            log.info("Seeded demo data: %s", counts)
        else:
            counts = seed(db)  # still ensure API clients exist
            if any(counts.values()):
                log.info("Topped up demo data: %s", counts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="drop all tables first")
    args = ap.parse_args()
    if args.reset:
        Base.metadata.drop_all(bind=engine)
        print("dropped all tables")
    init_db()
    with SessionLocal() as db:
        print("seeded:", seed(db))
        for c in db.scalars(select(ApiClient)):
            print(f"  API client {c.name:16s} X-API-Key: {c.api_key}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
