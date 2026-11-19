from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CampaignRow(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(255), index=True, default="")
    offer_url: Mapped[str] = mapped_column(Text)
    bridge_url: Mapped[str] = mapped_column(Text, default="")
    white_mode: Mapped[str] = mapped_column(String(20), default="local_html")
    white_url: Mapped[str] = mapped_column(Text, default="")
    geos: Mapped[list] = mapped_column(JSON, default=list)
    threshold: Mapped[int] = mapped_column(Integer, default=100)
    challenge_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    panic: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RequestLogRow(Base):
    __tablename__ = "request_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    campaign: Mapped[str] = mapped_column(String(120), default="", index=True)
    ip: Mapped[str] = mapped_column(String(45), index=True, default="")
    country: Mapped[str] = mapped_column(String(8), default="")
    city: Mapped[str] = mapped_column(String(120), default="")
    isp: Mapped[str] = mapped_column(String(200), default="")
    referer: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(80), default="")
    user_agent: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[int] = mapped_column(Integer, default=0)
    verdict: Mapped[str] = mapped_column(String(16), index=True, default="grey")
    reason: Mapped[str] = mapped_column(String(80), default="")
    details: Mapped[list] = mapped_column(JSON, default=list)
    query: Mapped[dict] = mapped_column(JSON, default=dict)


class DecisionRow(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    campaign: Mapped[str] = mapped_column(String(120), default="")
    ip: Mapped[str] = mapped_column(String(45), default="")
    user_agent: Mapped[str] = mapped_column(Text, default="")
    query: Mapped[dict] = mapped_column(JSON, default=dict)
    headers: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[int] = mapped_column(Integer, default=0)
    verdict: Mapped[str] = mapped_column(String(16), default="challenge")
    reason: Mapped[str] = mapped_column(String(80), default="")
    details: Mapped[list] = mapped_column(JSON, default=list)
    country: Mapped[str] = mapped_column(String(8), default="")
    city: Mapped[str] = mapped_column(String(120), default="")
    offer_url: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finalized: Mapped[bool] = mapped_column(Boolean, default=False)


class BannedIPRow(Base):
    __tablename__ = "banned_ips"

    ip: Mapped[str] = mapped_column(String(80), primary_key=True)
    reason: Mapped[str] = mapped_column(String(200), default="")
    source: Mapped[str] = mapped_column(String(40), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)


class AllowedIPRow(Base):
    __tablename__ = "allowed_ips"

    ip: Mapped[str] = mapped_column(String(45), primary_key=True)
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EngineSettingsRow(Base):
    __tablename__ = "engine_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    default_threshold: Mapped[int] = mapped_column(Integer, default=70)
    challenge_band: Mapped[int] = mapped_column(Integer, default=20)


class ScoringDetail(BaseModel):
    check: str
    points: int
    reason: str


class ScoringResult(BaseModel):
    score: int = 0
    verdict: Literal["grey", "white"] = "grey"
    reason: str = ""
    details: list[ScoringDetail] = Field(default_factory=list)
    country: str = ""
    city: str = ""
    isp: str = ""


class DecideIn(BaseModel):
    campaign: str = ""
    host: str = ""
    ip: str = ""
    user_agent: str = ""
    accept_language: str = ""
    headers: dict[str, Any] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    path: str = "/"
    js_metrics: Optional[dict[str, Any]] = None
    request_id: str = ""

    @field_validator("query", "headers", mode="before")
    @classmethod
    def _object_fields(cls, value):
        # PHP json_encodes an empty array as []. A bare visit was rejected.
        if value is None or value == [] or value == "":
            return {}
        return value


class DecideOut(BaseModel):
    request_id: str
    verdict: Literal["grey", "white", "challenge"]
    action: Literal["redirect_offer", "show_white", "redirect_white", "show_preland", "challenge"]
    url: str = ""
    score: int = 0
    reason: str = ""
    campaign: str = ""
    details: list[ScoringDetail] = Field(default_factory=list)


class CampaignIn(BaseModel):
    slug: str
    name: str
    domain: str = ""
    offer_url: str
    bridge_url: str = ""
    white_mode: Literal["local_html", "redirect"] = "local_html"
    white_url: str = ""
    geos: list[str] = Field(default_factory=list)
    threshold: int = 100
    challenge_enabled: bool = False
    panic: bool = False
    enabled: bool = True
    filters: dict[str, Any] = Field(default_factory=dict)
