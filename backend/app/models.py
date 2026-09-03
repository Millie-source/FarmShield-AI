"""SQLAlchemy models: Farmer, Farm, WeatherReading, RiskAssessment, Alert, ApiClient."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Farmer(Base):
    __tablename__ = "farmers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    language: Mapped[str] = mapped_column(String(2), default="en")  # en | sw
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    farms: Mapped[list[Farm]] = relationship(back_populates="farmer", cascade="all, delete-orphan")


class Farm(Base):
    __tablename__ = "farms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("farmers.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    crop: Mapped[str] = mapped_column(String(30), index=True)
    planting_date: Mapped[date] = mapped_column(Date)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    area_ha: Mapped[float | None] = mapped_column(Float, nullable=True)
    county: Mapped[str | None] = mapped_column(String(60), nullable=True, default="Kiambu")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    farmer: Mapped[Farmer] = relationship(back_populates="farms")
    assessments: Mapped[list[RiskAssessment]] = relationship(
        back_populates="farm", cascade="all, delete-orphan", order_by="RiskAssessment.assessed_at.desc()"
    )
    alerts: Mapped[list[Alert]] = relationship(back_populates="farm", cascade="all, delete-orphan", order_by="Alert.created_at.desc()")
    readings: Mapped[list[WeatherReading]] = relationship(back_populates="farm", cascade="all, delete-orphan")

    @property
    def latest_assessment(self) -> RiskAssessment | None:
        return self.assessments[0] if self.assessments else None


class WeatherReading(Base):
    """Daily reading as ingested for a farm (audit trail of what the score was based on)."""

    __tablename__ = "weather_readings"
    __table_args__ = (UniqueConstraint("farm_id", "date", "source", name="uq_reading_farm_date_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), index=True)
    source: Mapped[str] = mapped_column(String(60))  # e.g. mock:dry_spell, conduit:jkuat
    date: Mapped[date] = mapped_column(Date, index=True)
    rainfall_mm: Mapped[float] = mapped_column(Float)
    temp_max_c: Mapped[float] = mapped_column(Float)
    temp_min_c: Mapped[float] = mapped_column(Float)
    humidity_pct: Mapped[float] = mapped_column(Float)
    soil_moisture_pct: Mapped[float] = mapped_column(Float)
    solar_radiation_wm2: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    farm: Mapped[Farm] = relationship(back_populates="readings")


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), index=True)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    scenario: Mapped[str | None] = mapped_column(String(30), nullable=True)
    data_sources: Mapped[list] = mapped_column(JSON, default=list)

    stage_name: Mapped[str] = mapped_column(String(40))
    overall_score: Mapped[int] = mapped_column(Integer)
    overall_level: Mapped[str] = mapped_column(String(10))
    overall_label: Mapped[str] = mapped_column(String(40))
    drought_score: Mapped[int] = mapped_column(Integer)
    drought_level: Mapped[str] = mapped_column(String(10))
    flood_score: Mapped[int] = mapped_column(Integer)
    flood_level: Mapped[str] = mapped_column(String(10))
    heat_score: Mapped[int] = mapped_column(Integer)
    heat_level: Mapped[str] = mapped_column(String(10))
    crop_health_score: Mapped[int] = mapped_column(Integer)
    crop_health_level: Mapped[str] = mapped_column(String(10))
    crop_health_label: Mapped[str] = mapped_column(String(10))

    insurance_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[dict] = mapped_column(JSON)  # full RiskOut payload (engine output + trigger + advice)

    advice_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    advice_sw: Mapped[str | None] = mapped_column(Text, nullable=True)
    advice_source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # gemini | fallback

    farm: Mapped[Farm] = relationship(back_populates="assessments")
    alerts: Mapped[list[Alert]] = relationship(back_populates="assessment")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), index=True)
    assessment_id: Mapped[int | None] = mapped_column(ForeignKey("risk_assessments.id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(20), default="sms")
    recipient: Mapped[str] = mapped_column(String(20))
    language: Mapped[str] = mapped_column(String(2), default="en")
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued | sent | failed | previewed
    provider: Mapped[str] = mapped_column(String(30), default="console")
    provider_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    trigger_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    farm: Mapped[Farm] = relationship(back_populates="alerts")
    assessment: Mapped[RiskAssessment | None] = relationship(back_populates="alerts")


class ApiClient(Base):
    """Partner (insurer / bank / SACCO / agribusiness) allowed to call /api/v1."""

    __tablename__ = "api_clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    api_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    organisation_type: Mapped[str] = mapped_column(String(30))  # insurer | sacco | bank | agribusiness
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
