"""Nutrition helper utilities with FoodData Central API + local fallback."""

from __future__ import annotations

import os
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

from utils.data_loader import load_nutrition_seed


FDC_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
TIMEOUT_SECONDS = 10


NUTRIENT_KEYS = {
    "protein": "protein_g",
    "total lipid (fat)": "fat_g",
    "carbohydrate, by difference": "carbs_g",
    "energy": "calories_kcal",
    "fiber, total dietary": "fiber_g",
}


def _extract_nutrients(food_nutrients: list[dict[str, Any]]) -> dict[str, float | None]:
    out = {"protein_g": None, "fat_g": None, "carbs_g": None, "calories_kcal": None, "fiber_g": None}
    for nutrient in food_nutrients:
        name = str(nutrient.get("nutrientName", "")).strip().lower()
        mapped = NUTRIENT_KEYS.get(name)
        if mapped:
            out[mapped] = nutrient.get("value")
    return out


def _goal_queries(goal: str, dietary_preference: str) -> list[str]:
    if goal == "high protein":
        base = ["greek yogurt", "eggs", "tuna", "tofu", "black beans"]
    elif goal == "low fat":
        base = ["apple", "spinach", "broccoli", "low-fat yogurt", "black beans"]
    elif goal == "high fiber":
        base = ["lentils", "black beans", "oats", "apple", "spinach"]
    else:
        base = ["oats", "brown rice", "black beans", "chicken breast", "spinach"]

    if dietary_preference in {"vegetarian", "vegan"}:
        base = [q for q in base if q not in {"tuna", "chicken breast", "eggs"}]
        if "tofu" not in base:
            base.append("tofu")
    if dietary_preference == "gluten free":
        base = [q for q in base if q not in {"oats", "brown rice"}]
        base.extend(["quinoa", "sweet potato"])
    return base


def fetch_foods_from_fdc(goal: str, dietary_preference: str, limit: int = 10) -> pd.DataFrame:
    """Fetch nutrition suggestions via FDC API.

    Returns an empty DataFrame if key/API is unavailable, allowing fallback.
    """
    load_dotenv()
    api_key = os.getenv("FDC_API_KEY", "").strip()
    if not api_key:
        return pd.DataFrame()

    queries = _goal_queries(goal, dietary_preference)

    rows: list[dict[str, Any]] = []
    for query in queries:
        try:
            response = requests.get(
                FDC_SEARCH_URL,
                params={
                    "api_key": api_key,
                    "query": query,
                    "pageSize": 2,
                    "dataType": ["Foundation", "SR Legacy", "Survey (FNDDS)"],
                },
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            for item in data.get("foods", []):
                nutrients = _extract_nutrients(item.get("foodNutrients", []))
                rows.append(
                    {
                        "food_name": item.get("description", query.title()),
                        "category": item.get("foodCategory", "Unknown"),
                        "vegetarian": int(dietary_preference in {"vegetarian", "vegan"}),
                        **nutrients,
                        "source": "FoodData Central API",
                    }
                )
        except (requests.RequestException, ValueError):
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).drop_duplicates(subset=["food_name"]).head(limit)
    return df


def fallback_foods(goal: str, dietary_preference: str, limit: int = 10) -> pd.DataFrame:
    """Use local sample foods if API is unavailable."""
    df = load_nutrition_seed().copy()
    if dietary_preference == "vegetarian":
        df = df[df["vegetarian"] == 1]
    if dietary_preference == "vegan":
        if "vegan" in df.columns:
            df = df[df["vegan"] == 1]
        else:
            df = df[df["vegetarian"] == 1]
    if dietary_preference == "gluten free":
        if "gluten_free" in df.columns:
            df = df[df["gluten_free"] == 1]

    if goal in df["suggested_goal"].unique():
        primary = df[df["suggested_goal"] == goal]
        secondary = df[df["suggested_goal"] != goal]
        df = pd.concat([primary, secondary], ignore_index=True)

    df["source"] = "Local sample data"
    return df.head(limit)


def get_nutrition_suggestions(goal: str, dietary_preference: str, limit: int = 10) -> pd.DataFrame:
    """Return nutrition suggestions from API when possible, otherwise fallback."""
    api_df = fetch_foods_from_fdc(goal, dietary_preference, limit=limit)
    if not api_df.empty:
        return api_df
    return fallback_foods(goal, dietary_preference, limit=limit)
