"""Build nationwide app-ready datasets from USDA/raw source files.

Usage:
    python scripts/build_usda_datasets.py

Expected raw files in data/raw/:
- zip_reference_us.csv
  Required columns (aliases supported):
    zip, city, state, county, latitude, longitude

- food_access_atlas.csv (USDA Food Access Research Atlas tract-level extract)
  Expected to include tract id and low-income/low-access style indicators.

- zip_tract_crosswalk.csv
  Required columns (aliases supported):
    zip, tract, ratio

- snap_retailers_raw.csv (USDA SNAP retailer export)
  Required columns (aliases supported):
    name, address, zip, latitude, longitude

Outputs (written to data/usda/):
- zip_reference_us.csv
- food_access_zip_us.csv
- snap_retailers_us.csv
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "usda"


def _pick_column(df: pd.DataFrame, aliases: list[str], required: bool = True) -> str | None:
    low_map = {c.lower().strip(): c for c in df.columns}
    for alias in aliases:
        key = alias.lower().strip()
        if key in low_map:
            return low_map[key]
    if required:
        raise ValueError(f"Missing required column. Tried aliases: {aliases}")
    return None


def _clean_zip(series: pd.Series) -> pd.Series:
    return series.astype(str).str.extract(r"(\d{5})", expand=False).fillna("").str.zfill(5)


def build_zip_reference() -> pd.DataFrame:
    src = RAW_DIR / "zip_reference_us.csv"
    if not src.exists():
        raise FileNotFoundError(f"Missing {src}")

    df = pd.read_csv(src, dtype=str)
    zip_col = _pick_column(df, ["zip", "zipcode", "zcta", "zcta5", "postal_code"])
    city_col = _pick_column(df, ["city", "place_name", "primary_city"])
    state_col = _pick_column(df, ["state", "state_abbr", "stusps"])
    county_col = _pick_column(df, ["county", "county_name"], required=False)
    lat_col = _pick_column(df, ["latitude", "lat", "intptlat"])
    lon_col = _pick_column(df, ["longitude", "lon", "lng", "intptlon"])

    out = pd.DataFrame(
        {
            "zip": _clean_zip(df[zip_col]),
            "city": df[city_col].fillna("Unknown"),
            "state": df[state_col].fillna("Unknown"),
            "county": df[county_col].fillna("Unknown") if county_col else "Unknown",
            "latitude": pd.to_numeric(df[lat_col], errors="coerce"),
            "longitude": pd.to_numeric(df[lon_col], errors="coerce"),
        }
    )

    out = out.dropna(subset=["latitude", "longitude"])
    out = out[out["zip"].str.len() == 5]
    out = out.drop_duplicates(subset=["zip"]).sort_values("zip")
    return out


def build_food_access_zip(zip_ref: pd.DataFrame) -> pd.DataFrame:
    atlas_path = RAW_DIR / "food_access_atlas.csv"
    crosswalk_path = RAW_DIR / "zip_tract_crosswalk.csv"
    if not atlas_path.exists() or not crosswalk_path.exists():
        raise FileNotFoundError("Missing food_access_atlas.csv or zip_tract_crosswalk.csv")

    atlas = pd.read_csv(atlas_path, dtype=str)
    cross = pd.read_csv(crosswalk_path, dtype=str)

    tract_col_atlas = _pick_column(atlas, ["tract", "censustract", "tractfips", "census_tract"])
    li_col = _pick_column(
        atlas,
        ["li", "litracts_1and10", "lilatracts_1and10", "low_income", "low_income_flag"],
        required=False,
    )
    la_col = _pick_column(
        atlas,
        ["la", "la1and10", "latracts_1and10", "low_access", "low_access_flag"],
        required=False,
    )

    tract_col_cross = _pick_column(cross, ["tract", "tractfips", "census_tract"])
    zip_col_cross = _pick_column(cross, ["zip", "zipcode", "zcta", "postal_code"])
    ratio_col = _pick_column(cross, ["ratio", "res_ratio", "tot_ratio", "weight"], required=False)

    selected_cols = [tract_col_atlas]
    if li_col:
        selected_cols.append(li_col)
    if la_col and la_col not in selected_cols:
        selected_cols.append(la_col)
    atlas_work = atlas[selected_cols].copy()
    atlas_work = atlas_work.rename(columns={tract_col_atlas: "tract"})
    atlas_work["tract"] = atlas_work["tract"].astype(str).str.extract(r"(\d{11})", expand=False)

    if li_col:
        atlas_work["li_flag"] = pd.to_numeric(atlas_work[li_col], errors="coerce").fillna(0)
    else:
        atlas_work["li_flag"] = 0
    if la_col and la_col in atlas_work.columns:
        atlas_work["la_flag"] = pd.to_numeric(atlas_work[la_col], errors="coerce").fillna(0)
    else:
        atlas_work["la_flag"] = 0

    cross_work = cross[[zip_col_cross, tract_col_cross] + ([ratio_col] if ratio_col else [])].copy()
    cross_work = cross_work.rename(columns={zip_col_cross: "zip", tract_col_cross: "tract"})
    cross_work["zip"] = _clean_zip(cross_work["zip"])
    cross_work["tract"] = cross_work["tract"].astype(str).str.extract(r"(\d{11})", expand=False)
    cross_work["ratio"] = pd.to_numeric(cross_work[ratio_col], errors="coerce").fillna(1.0) if ratio_col else 1.0

    merged = cross_work.merge(atlas_work[["tract", "li_flag", "la_flag"]], on="tract", how="left")
    merged[["li_flag", "la_flag"]] = merged[["li_flag", "la_flag"]].fillna(0)

    grouped = (
        merged.groupby("zip", as_index=False)
        .apply(
            lambda g: pd.Series(
                {
                    "li_weighted": (g["li_flag"] * g["ratio"]).sum() / max(g["ratio"].sum(), 1e-9),
                    "la_weighted": (g["la_flag"] * g["ratio"]).sum() / max(g["ratio"].sum(), 1e-9),
                }
            )
        )
        .reset_index(drop=True)
    )

    out = zip_ref[["zip", "county", "state"]].merge(grouped, on="zip", how="left")
    out["li_weighted"] = out["li_weighted"].fillna(0)
    out["la_weighted"] = out["la_weighted"].fillna(0)

    out["estimated_low_income"] = (out["li_weighted"] >= 0.5).astype(int)
    out["estimated_low_access"] = (out["la_weighted"] >= 0.5).astype(int)
    out["access_notes"] = (
        "Derived from USDA Food Access Atlas tract indicators via ZIP-to-tract weighted crosswalk."
    )
    out["source_quality"] = "usda_national_zip_derived"

    return out[
        [
            "zip",
            "county",
            "state",
            "estimated_low_income",
            "estimated_low_access",
            "access_notes",
            "source_quality",
        ]
    ]


def build_snap_retailers(zip_ref: pd.DataFrame) -> pd.DataFrame:
    src = RAW_DIR / "snap_retailers_raw.csv"
    if not src.exists():
        raise FileNotFoundError(f"Missing {src}")

    df = pd.read_csv(src, dtype=str)

    name_col = _pick_column(df, ["name", "store_name", "retailer_name", "doing_business_as"])
    addr_col = _pick_column(df, ["address", "address1", "street", "street_address"])
    zip_col = _pick_column(df, ["zip", "zipcode", "postal_code"])
    lat_col = _pick_column(df, ["latitude", "lat", "y"])
    lon_col = _pick_column(df, ["longitude", "lon", "lng", "x"])

    out = pd.DataFrame(
        {
            "name": df[name_col].fillna("Unknown retailer"),
            "address": df[addr_col].fillna("Address unavailable"),
            "zip": _clean_zip(df[zip_col]),
            "latitude": pd.to_numeric(df[lat_col], errors="coerce"),
            "longitude": pd.to_numeric(df[lon_col], errors="coerce"),
        }
    )

    out = out.dropna(subset=["latitude", "longitude"])
    out = out[out["zip"].str.len() == 5]

    # USDA SNAP export contains authorized locations, so set as true.
    out["snap_authorized"] = 1
    out["category"] = "grocery"
    out["price_level"] = "medium"
    out["vegetarian_friendly"] = 1
    out["resource_type"] = "store"

    out = out.merge(zip_ref[["zip"]], on="zip", how="inner")
    out = out.drop_duplicates(subset=["name", "address", "zip"]).reset_index(drop=True)
    out.insert(0, "id", range(1, len(out) + 1))
    return out[
        [
            "id",
            "name",
            "address",
            "zip",
            "latitude",
            "longitude",
            "snap_authorized",
            "category",
            "price_level",
            "vegetarian_friendly",
            "resource_type",
        ]
    ]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    zip_ref = build_zip_reference()
    food_access = build_food_access_zip(zip_ref)
    retailers = build_snap_retailers(zip_ref)

    zip_ref.to_csv(OUT_DIR / "zip_reference_us.csv", index=False)
    food_access.to_csv(OUT_DIR / "food_access_zip_us.csv", index=False)
    retailers.to_csv(OUT_DIR / "snap_retailers_us.csv", index=False)

    print("Built USDA-ready files:")
    print(f"- {OUT_DIR / 'zip_reference_us.csv'} ({len(zip_ref):,} rows)")
    print(f"- {OUT_DIR / 'food_access_zip_us.csv'} ({len(food_access):,} rows)")
    print(f"- {OUT_DIR / 'snap_retailers_us.csv'} ({len(retailers):,} rows)")


if __name__ == "__main__":
    main()
