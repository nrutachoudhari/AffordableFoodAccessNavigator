"""Data loading utilities for Affordable Food Access Navigator.

USDA-first behavior:
1) If nationwide processed datasets exist under data/usda/, use them.
2) Otherwise, fall back to local sample CSV files for demo reliability.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
USDA_DIR = DATA_DIR / "usda"


def _preferred_path(usda_filename: str, fallback_filename: str) -> Path:
    """Return USDA national file when available, else fallback sample file."""
    usda_path = USDA_DIR / usda_filename
    if usda_path.exists():
        return usda_path
    return DATA_DIR / fallback_filename


@st.cache_data(show_spinner=False)
def load_zip_reference() -> pd.DataFrame:
    """Load ZIP centroid data.

    Preferred USDA-ready nationwide file:
        data/usda/zip_reference_us.csv
    Fallback demo file:
        data/zip_reference.csv
    """
    path = _preferred_path("zip_reference_us.csv", "zip_reference.csv")
    df = pd.read_csv(path, dtype={"zip": str})
    df["zip"] = df["zip"].astype(str).str.zfill(5)
    return df


@st.cache_data(show_spinner=False)
def load_food_access_context() -> pd.DataFrame:
    """Load food access context by ZIP.

    Preferred USDA-ready nationwide file:
        data/usda/food_access_zip_us.csv
    Fallback demo file:
        data/food_access_context.csv
    """
    path = _preferred_path("food_access_zip_us.csv", "food_access_context.csv")
    df = pd.read_csv(path, dtype={"zip": str})
    df["zip"] = df["zip"].astype(str).str.zfill(5)
    bool_cols = ["estimated_low_income", "estimated_low_access"]
    for col in bool_cols:
        df[col] = df[col].fillna(0).astype(int)
    return df


@st.cache_data(show_spinner=False)
def load_retailers() -> pd.DataFrame:
    """Load retailer and assistance options.

    Preferred USDA-ready nationwide file:
        data/usda/snap_retailers_us.csv
    Fallback demo file:
        data/retailers.csv
    """
    path = _preferred_path("snap_retailers_us.csv", "retailers.csv")
    df = pd.read_csv(path, dtype={"zip": str})
    df["zip"] = df["zip"].astype(str).str.zfill(5)
    df["snap_authorized"] = df["snap_authorized"].fillna(0).astype(int)
    df["vegetarian_friendly"] = df["vegetarian_friendly"].fillna(0).astype(int)
    if "vegan_friendly" not in df.columns:
        df["vegan_friendly"] = df["vegetarian_friendly"]
    if "gluten_free_friendly" not in df.columns:
        df["gluten_free_friendly"] = df["vegetarian_friendly"]
    df["vegan_friendly"] = df["vegan_friendly"].fillna(0).astype(int)
    df["gluten_free_friendly"] = df["gluten_free_friendly"].fillna(0).astype(int)

    # Optional enrichment: retailer-level discount / surplus program flags.
    flags_path = USDA_DIR / "retailer_discount_flags.csv"
    if flags_path.exists():
        flags = pd.read_csv(flags_path)
        if not flags.empty and "id" in flags.columns:
            agg = (
                flags.groupby("id", as_index=False)
                .agg(
                    discount_program=("program_name", lambda s: " | ".join(sorted(set(map(str, s))))),
                    discount_program_type=("program_type", lambda s: " | ".join(sorted(set(map(str, s))))),
                    discount_confidence=("confidence", lambda s: " | ".join(sorted(set(map(str, s))))),
                )
            )
            df = df.merge(agg, on="id", how="left")
    for col in ["discount_program", "discount_program_type", "discount_confidence"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("")
    return df


@st.cache_data(show_spinner=False)
def load_nutrition_seed() -> pd.DataFrame:
    """Load fallback nutrition foods for when API data is unavailable."""
    return pd.read_csv(DATA_DIR / "nutrition_seed_foods.csv")


def get_food_access_for_zip(zip_code: str) -> dict:
    """Return a dictionary with food access context for a ZIP code.

    Note:
        In production, this should map ZIP to Census tract and then query
        USDA Food Access Research Atlas tract-level indicators directly.
    """
    context_df = load_food_access_context()
    zip_df = load_zip_reference()

    context_row = context_df[context_df["zip"] == zip_code]
    zip_row = zip_df[zip_df["zip"] == zip_code]

    if zip_row.empty:
        return {
            "zip": zip_code,
            "city": "Unknown",
            "state": "Unknown",
            "county": "Unknown",
            "estimated_low_income": 0,
            "estimated_low_access": 0,
            "access_notes": "ZIP not in local demo file. Using generic fallback context.",
            "source_quality": "fallback",
        }

    base = zip_row.iloc[0].to_dict()
    if context_row.empty:
        return {
            "zip": zip_code,
            "city": base.get("city", "Unknown"),
            "state": base.get("state", "Unknown"),
            "county": base.get("county", "Unknown"),
            "estimated_low_income": 0,
            "estimated_low_access": 0,
            "access_notes": "No local food access context found for ZIP. Using neutral baseline.",
            "source_quality": "fallback",
        }

    merged = context_row.iloc[0].to_dict()
    merged.update({
        "city": base.get("city", "Unknown"),
        "state": base.get("state", "Unknown"),
        "county": base.get("county", "Unknown"),
    })
    return merged


def get_coverage_overview() -> dict:
    """Return high-level coverage metrics for the currently loaded datasets."""
    zip_df = load_zip_reference()
    food_df = load_food_access_context()
    retailers_df = load_retailers()

    zip_count = int(zip_df["zip"].nunique())
    food_count = int(food_df["zip"].nunique())
    retailer_zip_count = int(retailers_df["zip"].nunique())
    retailer_store_count = int(len(retailers_df))
    estimated_us_zip_total = 43191

    return {
        "zip_reference_count": zip_count,
        "food_access_count": food_count,
        "retailer_zip_count": retailer_zip_count,
        "retailer_store_count": retailer_store_count,
        "estimated_us_zip_total": estimated_us_zip_total,
        "zip_reference_coverage_pct": round((zip_count / max(estimated_us_zip_total, 1)) * 100, 2),
    }


def get_state_coverage_frame() -> pd.DataFrame:
    """Return state-level ZIP and retailer coverage for visualization."""
    zip_df = load_zip_reference()
    food_df = load_food_access_context()[["zip"]].copy()
    retailers_df = load_retailers()[["zip"]].copy()

    state_zip = (
        zip_df.groupby("state", as_index=False)["zip"]
        .nunique()
        .rename(columns={"zip": "zip_reference_count"})
    )

    food_with_state = food_df.merge(zip_df[["zip", "state"]], on="zip", how="left")
    state_food = (
        food_with_state.groupby("state", as_index=False)["zip"]
        .nunique()
        .rename(columns={"zip": "food_access_count"})
    )

    retailers_with_state = retailers_df.merge(zip_df[["zip", "state"]], on="zip", how="left")
    state_retailers = (
        retailers_with_state.groupby("state", as_index=False)["zip"]
        .nunique()
        .rename(columns={"zip": "retailer_zip_count"})
    )

    out = state_zip.merge(state_food, on="state", how="left").merge(state_retailers, on="state", how="left")
    out["food_access_count"] = out["food_access_count"].fillna(0).astype(int)
    out["retailer_zip_count"] = out["retailer_zip_count"].fillna(0).astype(int)
    return out.sort_values("state").reset_index(drop=True)


def get_area_coverage_grid(cell_size_deg: float = 0.75) -> pd.DataFrame:
    """Return area-based coverage grid for pixel-style US mapping.

    Each cell aggregates ZIPs into latitude/longitude bins and computes
    retailer ZIP coverage ratio in that area.
    """
    zip_df = load_zip_reference()[["zip", "latitude", "longitude"]].copy()
    food_df = load_food_access_context()[["zip"]].copy()
    retailers_df = load_retailers()[["zip"]].copy()

    zip_df["latitude"] = pd.to_numeric(zip_df["latitude"], errors="coerce")
    zip_df["longitude"] = pd.to_numeric(zip_df["longitude"], errors="coerce")
    zip_df = zip_df.dropna(subset=["latitude", "longitude"]).drop_duplicates(subset=["zip"])

    zip_df["lat_bin"] = (zip_df["latitude"] / cell_size_deg).round() * cell_size_deg
    zip_df["lon_bin"] = (zip_df["longitude"] / cell_size_deg).round() * cell_size_deg

    retailer_zips = set(retailers_df["zip"].astype(str))
    food_zips = set(food_df["zip"].astype(str))
    zip_df["has_retailer"] = zip_df["zip"].astype(str).isin(retailer_zips).astype(int)
    zip_df["has_food_access"] = zip_df["zip"].astype(str).isin(food_zips).astype(int)

    grid = (
        zip_df.groupby(["lat_bin", "lon_bin"], as_index=False)
        .agg(
            zip_count=("zip", "nunique"),
            retailer_covered=("has_retailer", "sum"),
            food_access_covered=("has_food_access", "sum"),
        )
    )
    grid["retailer_coverage_ratio"] = grid["retailer_covered"] / grid["zip_count"].clip(lower=1)
    grid["food_access_coverage_ratio"] = grid["food_access_covered"] / grid["zip_count"].clip(lower=1)
    grid["retailer_coverage_ratio"] = pd.to_numeric(grid["retailer_coverage_ratio"], errors="coerce").fillna(0.0).clip(0, 1)
    grid["food_access_coverage_ratio"] = pd.to_numeric(grid["food_access_coverage_ratio"], errors="coerce").fillna(0.0).clip(0, 1)
    grid["retailer_coverage_pct"] = (grid["retailer_coverage_ratio"] * 100).round(1)
    grid["food_access_coverage_pct"] = (grid["food_access_coverage_ratio"] * 100).round(1)
    return grid
