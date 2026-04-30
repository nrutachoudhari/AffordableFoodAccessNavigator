"""Transparent rule-based recommendation engine for MVP ranking."""

from __future__ import annotations

from typing import Any

import pandas as pd

from utils.data_loader import load_retailers
from utils.location import haversine_miles


BUDGET_WEIGHTS = {
    "all": {"low": 1.0, "medium": 1.0, "high": 1.0},
    "low": {"low": 1.0, "medium": 0.55, "high": 0.2},
    "medium": {"low": 0.75, "medium": 1.0, "high": 0.65},
    "high": {"low": 0.55, "medium": 0.85, "high": 1.0},
}

GOAL_CATEGORY_PREFERENCES = {
    "high protein": {"grocery": 0.9, "discount_grocery": 1.0, "food_pantry": 0.65},
    "low fat": {"grocery": 0.95, "discount_grocery": 0.9, "food_pantry": 0.7},
    "balanced": {"grocery": 1.0, "discount_grocery": 0.95, "food_pantry": 0.8},
    "high fiber": {"grocery": 0.9, "discount_grocery": 1.0, "food_pantry": 0.75},
}


def _proximity_score(distance_miles: float) -> float:
    """Map distance to a 0-1 proximity score."""
    if distance_miles <= 1:
        return 1.0
    if distance_miles <= 3:
        return 0.85
    if distance_miles <= 5:
        return 0.65
    if distance_miles <= 8:
        return 0.45
    return 0.25


def _transportation_score(distance_miles: float, transportation_access: str) -> float:
    if transportation_access == "car":
        if distance_miles <= 8:
            return 1.0
        if distance_miles <= 15:
            return 0.75
        return 0.45

    if distance_miles <= 1:
        return 1.0
    if distance_miles <= 2:
        return 0.8
    if distance_miles <= 4:
        return 0.55
    return 0.25


def _snap_score(snap_pref: str, snap_authorized: int, resource_type: str) -> float:
    if snap_pref == "show SNAP-authorized locations only":
        return 1.0 if snap_authorized == 1 else 0.0
    if snap_authorized == 1:
        return 1.0
    return 0.7 if resource_type == "assistance" else 0.4


def _access_fit_score(resource_type: str, low_access_flag: int) -> float:
    if low_access_flag and resource_type == "assistance":
        return 1.0
    if low_access_flag and resource_type == "store":
        return 0.85
    if resource_type == "assistance":
        return 0.75
    return 0.9


def _nutrition_fit_score(goal: str, category: str, vegetarian_pref: str, vegetarian_friendly: int) -> float:
    category_fit = GOAL_CATEGORY_PREFERENCES.get(goal, {}).get(category, 0.75)
    if vegetarian_pref == "vegetarian" and vegetarian_friendly != 1:
        return max(0.2, category_fit - 0.5)
    return category_fit


def _dietary_ok(row: pd.Series, dietary_preference: str) -> bool:
    if dietary_preference == "no preference":
        return True
    if dietary_preference == "vegetarian":
        return int(row.get("vegetarian_friendly", 0)) == 1
    if dietary_preference == "vegan":
        return int(row.get("vegan_friendly", 0)) == 1
    if dietary_preference == "gluten free":
        return int(row.get("gluten_free_friendly", 0)) == 1
    return True


def _reason_text(row: pd.Series) -> str:
    parts: list[str] = []
    if row["affordability_score"] >= 0.9:
        parts.append("strong budget fit")
    if row["transportation_score"] >= 0.9:
        parts.append("easy to reach for your transportation access")
    if row["snap_score"] >= 0.9:
        parts.append("SNAP alignment is high")
    if row["nutrition_score"] >= 0.9:
        parts.append("good match to your nutrition goal")
    if row["resource_type"] == "assistance":
        parts.append("includes assistance-style support")
    if not parts:
        parts.append("balanced fit across your selected preferences")
    return "; ".join(parts).capitalize() + "."


def rank_recommendations(
    zip_centroid: dict,
    budget_level: str,
    transportation_access: str,
    nutrition_goal: str,
    snap_preference: str,
    dietary_preference: str,
    access_context: dict,
    top_n: int = 10,
) -> tuple[pd.DataFrame, int]:
    """Generate ranked recommendations and return (top_results, total_matches)."""
    retailers = load_retailers().copy()

    retailers["distance_miles"] = retailers.apply(
        lambda x: haversine_miles(
            zip_centroid["latitude"],
            zip_centroid["longitude"],
            float(x["latitude"]),
            float(x["longitude"]),
        ),
        axis=1,
    )

    # Keep candidates reasonably local for MVP while still allowing fallback options.
    candidates = retailers[retailers["distance_miles"] <= 25].copy()
    if candidates.empty:
        candidates = retailers.copy()

    candidates["affordability_score"] = candidates["price_level"].map(BUDGET_WEIGHTS.get(budget_level, {})).fillna(0.5)
    candidates["transportation_score"] = candidates["distance_miles"].apply(
        lambda d: _transportation_score(d, transportation_access)
    )
    candidates["nutrition_score"] = candidates.apply(
        lambda x: _nutrition_fit_score(
            nutrition_goal,
            x["category"],
            dietary_preference,
            int(x["vegetarian_friendly"]),
        ),
        axis=1,
    )
    candidates["snap_score"] = candidates.apply(
        lambda x: _snap_score(snap_preference, int(x["snap_authorized"]), x["resource_type"]),
        axis=1,
    )
    candidates["proximity_score"] = candidates["distance_miles"].apply(_proximity_score)
    candidates["access_fit_score"] = candidates["resource_type"].apply(
        lambda t: _access_fit_score(t, int(access_context.get("estimated_low_access", 0)))
    )

    if snap_preference == "show SNAP-authorized locations only":
        candidates = candidates[candidates["snap_authorized"] == 1].copy()

    # User requested strict low-budget filtering for low budget selection.
    if budget_level == "low":
        candidates = candidates[candidates["price_level"] == "low"].copy()

    candidates = candidates[candidates.apply(lambda row: _dietary_ok(row, dietary_preference), axis=1)].copy()

    if candidates.empty:
        return candidates, 0

    # Transparent weighted score requested by specification.
    candidates["final_score"] = (
        candidates["affordability_score"] * 0.30
        + candidates["transportation_score"] * 0.20
        + candidates["nutrition_score"] * 0.25
        + candidates["snap_score"] * 0.15
        + candidates["proximity_score"] * 0.10
    )

    # Access context acts as a tie-breaker boost in higher-need areas.
    candidates["final_score"] = candidates["final_score"] * (0.92 + 0.08 * candidates["access_fit_score"])

    candidates["recommendation_reason"] = candidates.apply(_reason_text, axis=1)

    out_cols = [
        "id",
        "name",
        "address",
        "zip",
        "distance_miles",
        "snap_authorized",
        "category",
        "resource_type",
        "price_level",
        "vegetarian_friendly",
        "affordability_score",
        "transportation_score",
        "nutrition_score",
        "snap_score",
        "proximity_score",
        "final_score",
        "recommendation_reason",
        "discount_program",
        "discount_program_type",
        "discount_confidence",
    ]

    ranked_all = candidates[out_cols].sort_values(by="final_score", ascending=False).reset_index(drop=True)
    total_matches = len(ranked_all)
    ranked = ranked_all.head(top_n)
    return ranked, total_matches


def score_breakdown_text(row: pd.Series) -> str:
    """Generate a plain-English explanation for one recommendation score."""
    return (
        f"Score {row['final_score']:.2f} from affordability ({row['affordability_score']:.2f}), "
        f"transportation fit ({row['transportation_score']:.2f}), nutrition fit ({row['nutrition_score']:.2f}), "
        f"SNAP alignment ({row['snap_score']:.2f}), and proximity ({row['proximity_score']:.2f})."
    )


def recommendations_to_map_frame(recs: pd.DataFrame) -> pd.DataFrame:
    """Return map-friendly coordinates with minimal columns."""
    # Retailer coordinates are loaded from source DataFrame in rank_recommendations.
    all_retailers = load_retailers()[["name", "address", "zip", "latitude", "longitude"]]
    merged = recs.merge(all_retailers, on=["name", "address", "zip"], how="left")
    return merged[["name", "address", "latitude", "longitude", "final_score", "distance_miles", "resource_type"]]


def get_scoring_weights() -> dict[str, Any]:
    """Expose weighting config for UI transparency."""
    return {
        "affordability_score": 0.30,
        "transportation_score": 0.20,
        "nutrition_score": 0.25,
        "snap_score": 0.15,
        "proximity_score": 0.10,
    }
