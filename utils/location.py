"""Location and distance utilities for ZIP-based recommendation logic."""

from __future__ import annotations

import math
from functools import lru_cache

import pandas as pd
from utils.data_loader import load_zip_reference

try:
    import pgeocode
except ImportError:  # pragma: no cover - optional dependency until installed
    pgeocode = None


EARTH_RADIUS_MILES = 3958.8


def is_valid_zip(zip_code: str) -> bool:
    """Basic US ZIP validation for 5-digit ZIPs."""
    return bool(zip_code) and zip_code.isdigit() and len(zip_code) == 5


@lru_cache(maxsize=1)
def _us_postal_db():
    if pgeocode is None:
        return None
    try:
        return pgeocode.Nominatim("us")
    except Exception:
        return None


def _lookup_with_pgeocode(zip_code: str) -> dict | None:
    db = _us_postal_db()
    if db is None:
        return None
    rec = db.query_postal_code(zip_code)
    if rec is None or (isinstance(rec, pd.Series) and rec.empty):
        return None

    lat = rec.get("latitude")
    lon = rec.get("longitude")
    if pd.isna(lat) or pd.isna(lon):
        return None

    return {
        "zip": zip_code,
        "city": str(rec.get("place_name") or "Unknown"),
        "state": str(rec.get("state_code") or "Unknown"),
        "county": "Unknown",
        "latitude": float(lat),
        "longitude": float(lon),
        "source": "pgeocode_offline_us",
    }


def get_zip_centroid(zip_code: str) -> dict | None:
    """Return centroid lat/lon for a ZIP.

    Lookup order:
    1) Local loaded ZIP reference (USDA/demo CSV)
    2) Offline all-US ZIP fallback via pgeocode (if installed)
    """
    zip_df = load_zip_reference()
    row = zip_df[zip_df["zip"] == zip_code]
    if not row.empty:
        item = row.iloc[0]
        return {
            "zip": item["zip"],
            "city": item["city"],
            "state": item["state"],
            "county": item["county"],
            "latitude": float(item["latitude"]),
            "longitude": float(item["longitude"]),
            "source": "local_reference",
        }

    return _lookup_with_pgeocode(zip_code)


def get_zip_coverage_status(zip_code: str) -> dict:
    """Return coverage diagnostics for current ZIP and dataset mode."""
    zip_df = load_zip_reference()
    local_zip_count = int(zip_df["zip"].nunique())
    in_local = bool((zip_df["zip"] == zip_code).any())

    db = _us_postal_db()
    if db is not None and hasattr(db, "_data"):
        us_total = int(db._data["postal_code"].dropna().nunique())
    else:
        us_total = 43191  # approximate US 5-digit ZIP count

    coverage_pct = round((local_zip_count / max(us_total, 1)) * 100, 2)
    return {
        "zip_in_local_reference": in_local,
        "local_zip_count": local_zip_count,
        "estimated_total_us_zips": us_total,
        "local_coverage_pct": coverage_pct,
        "has_pgeocode": db is not None,
    }


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance in miles."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_MILES * c
