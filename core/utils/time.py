from __future__ import annotations

import datetime as _dt
import re


def utc_iso_z(dt: _dt.datetime) -> str:
    """Format a datetime as UTC ISO-8601 with milliseconds and trailing 'Z'."""
    if not isinstance(dt, _dt.datetime):
        raise TypeError("utc_iso_z() expects a datetime")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt.astimezone(_dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_now_iso_z() -> str:
    """Return UTC timestamp matching JS Date#toISOString() (milliseconds + trailing 'Z')."""
    # Example: 2026-01-20T05:36:28.123+00:00 -> 2026-01-20T05:36:28.123Z
    return utc_iso_z(_dt.datetime.now(tz=_dt.timezone.utc))


def utc_now_iso_z_seconds() -> str:
    """Return UTC timestamp with seconds precision and trailing 'Z'."""
    return _dt.datetime.now(tz=_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def utc_stamp_compact() -> str:
    # Match legacy timestamp format: new Date().toISOString().replace(/[:.]/g, "").replace("T","-").replace("Z","Z")
    iso = utc_now_iso_z()
    return iso.replace(":", "").replace(".", "").replace("T", "-")


def iso_date_part(iso: str) -> str:
    s = str(iso or "").strip()
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else ""
