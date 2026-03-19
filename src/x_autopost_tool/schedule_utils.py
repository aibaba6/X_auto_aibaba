from __future__ import annotations

from datetime import datetime
import os
from zoneinfo import ZoneInfo


DEFAULT_TIMEZONE = "Asia/Tokyo"


def app_timezone_name(config=None) -> str:
    raw = ""
    if config is not None:
        raw = str(config.raw.get("schedule", {}).get("timezone", "")).strip()
    return raw or os.getenv("TZ", "").strip() or DEFAULT_TIMEZONE


def app_timezone(config=None) -> ZoneInfo:
    return ZoneInfo(app_timezone_name(config))


def now_local(config=None) -> datetime:
    return datetime.now(app_timezone(config))


def parse_scheduled_datetime(value: str, config=None) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except Exception:
        return None
    tz = app_timezone(config)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def serialize_scheduled_datetime(value: str, config=None) -> str:
    parsed = parse_scheduled_datetime(value, config)
    if not parsed:
        return ""
    return parsed.replace(microsecond=0).isoformat()


def format_datetime_local_input(value: str, config=None) -> str:
    parsed = parse_scheduled_datetime(value, config)
    if not parsed:
        return (value or "").strip()
    return parsed.strftime("%Y-%m-%dT%H:%M")
