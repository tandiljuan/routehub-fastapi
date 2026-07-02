import re
from datetime import datetime, timezone
from typing import Any

from dateutil.parser import parse as parse_datetime
from fastapi import HTTPException

from models.types.geopoint import format_geo_point
from models.types.event import validate_ical_event

_DTSTART_RE = re.compile(r'^DTSTART(?:;|:)', re.MULTILINE | re.IGNORECASE)


def parse_bulk_deliveries_body(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and isinstance(raw.get("deliveries"), list):
        return raw["deliveries"]
    raise HTTPException(
        status_code=422,
        detail="Expected a JSON array or an object with a 'deliveries' array",
    )


def _format_ical_utc(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime('%Y%m%dT%H%M%SZ')


def _parse_tw_timestamp(value: str) -> datetime:
    raw = value.strip().replace(' ', 'T')
    try:
        return datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except ValueError:
        return parse_datetime(value)


def _time_window_dict_to_ical(tw: dict) -> str | None:
    start = tw.get('start')
    end = tw.get('end')
    if not start or not end:
        return None
    dtstart = _format_ical_utc(_parse_tw_timestamp(str(start)))
    dtend = _format_ical_utc(_parse_tw_timestamp(str(end)))
    return f"DTSTART:{dtstart}\r\nDTEND:{dtend}"


def _normalize_schedule_entry(entry: Any) -> str | None:
    if isinstance(entry, dict):
        return _time_window_dict_to_ical(entry)
    if not isinstance(entry, str):
        return None
    text = entry.strip()
    if not text:
        return None
    if not _DTSTART_RE.search(text):
        return None
    try:
        return validate_ical_event(text)
    except ValueError:
        return None


def _sanitize_bulk_schedules(item: dict) -> dict:
    schedules = item.get('schedules')
    if not schedules:
        return item
    if not isinstance(schedules, list):
        normalized = dict(item)
        normalized.pop('schedules', None)
        return normalized

    valid: list[str] = []
    for entry in schedules:
        normalized = _normalize_schedule_entry(entry)
        if normalized:
            valid.append(normalized)

    normalized = dict(item)
    if valid:
        normalized['schedules'] = valid
    else:
        normalized.pop('schedules', None)
    return normalized


def normalize_bulk_delivery_item(item: Any) -> Any:
    if not isinstance(item, dict):
        return item

    normalized = _sanitize_bulk_schedules(item)
    if normalized.get("destination"):
        return normalized

    lat = normalized.get("lat")
    lng = normalized.get("lng")
    extra = normalized.get("extra")
    if (lat is None or lng is None) and isinstance(extra, dict):
        if lat is None:
            lat = extra.get("lat")
        if lng is None:
            lng = extra.get("lng")

    if lat is None or lng is None:
        return normalized

    out = dict(normalized)
    out["destination"] = format_geo_point(float(lat), float(lng))
    return out
