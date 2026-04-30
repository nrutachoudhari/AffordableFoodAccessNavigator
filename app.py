"""Affordable Food Access Navigator - Streamlit MVP."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.data_loader import get_food_access_for_zip, load_retailers
from utils.location import get_zip_centroid, is_valid_zip
from utils.nutrition import get_nutrition_suggestions
from utils.recommender import (
    rank_recommendations,
    recommendations_to_map_frame,
    score_breakdown_text,
)


st.set_page_config(
    page_title="Affordable Food Access Navigator",
    page_icon="🥗",
    layout="wide",
)

st.markdown(
    """
    <style>
    .main-title {font-size: 2rem; font-weight: 700; margin-bottom: 0.2rem;}
    .subtitle {color: #4b5563; margin-bottom: 1rem;}
    .card {border: 1px solid #1f2937; border-radius: 12px; padding: 14px; margin-bottom: 10px; background: #000000; color: #f8fafc;}
    .muted {color: #cbd5e1; font-size: 0.9rem;}
    .pill {display: inline-block; padding: 0.2rem 0.55rem; border-radius: 999px; background: #0f172a; color: #93c5fd; border: 1px solid #1e293b; font-size: 0.75rem; margin-right: 0.35rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="main-title">Affordable Food Access Navigator</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="subtitle">Find affordable, SNAP-friendly, and nutrition-aligned food options by ZIP code.</div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Your Preferences")
    zip_code = st.text_input("ZIP code", value="19104", max_chars=5).strip()
    budget_level = st.selectbox("Budget level", ["all", "low", "medium", "high"], index=0)
    transportation_access = st.selectbox("Transportation access", ["car", "no car"], index=1)
    nutrition_goal = st.selectbox(
        "Nutrition goal",
        ["high protein", "low fat", "balanced", "high fiber"],
        index=2,
    )
    snap_preference = st.radio(
        "SNAP preference",
        ["show SNAP-authorized locations only", "show all options"],
        index=1,
    )
    dietary_preference = st.radio(
        "Dietary preference",
        ["no preference", "vegetarian", "vegan", "gluten free"],
        index=0,
    )
    top_n = st.slider("Number of recommendations", min_value=5, max_value=10, value=7)

    run = st.button("Find My Food Options", type="primary", use_container_width=True)
    if run:
        st.session_state["search_submitted"] = True

if "search_submitted" not in st.session_state:
    st.session_state["search_submitted"] = False

if not st.session_state["search_submitted"]:
    st.info("Choose your preferences in the sidebar, then click **Find My Food Options**.")
    st.stop()

if not is_valid_zip(zip_code):
    st.error("Please enter a valid 5-digit ZIP code.")
    st.stop()
zip_code = zip_code.zfill(5)

zip_centroid = get_zip_centroid(zip_code)
if not zip_centroid:
    retailers_df = load_retailers()
    local_zip_rows = retailers_df[retailers_df["zip"] == zip_code]
    if not local_zip_rows.empty:
        zip_centroid = {
            "zip": zip_code,
            "city": "Unknown",
            "state": "Unknown",
            "county": "Unknown",
            "latitude": float(local_zip_rows["latitude"].astype(float).mean()),
            "longitude": float(local_zip_rows["longitude"].astype(float).mean()),
        }
    else:
        # Pan-US fallback to allow any valid ZIP input when full reference data is not loaded yet.
        zip_centroid = {
            "zip": zip_code,
            "city": "Unknown",
            "state": "Unknown",
            "county": "Unknown",
            "latitude": 39.8283,
            "longitude": -98.5795,
        }
        st.info(
            "ZIP could not be resolved in local data or offline US ZIP database. Using national center fallback."
        )
elif zip_centroid.get("source") == "pgeocode_offline_us":
    st.info("ZIP resolved from offline US ZIP database. Add USDA nationwide ZIP reference data for full local context fields.")

access_context = get_food_access_for_zip(zip_code)
recommendations, total_matches = rank_recommendations(
    zip_centroid=zip_centroid,
    budget_level=budget_level,
    transportation_access=transportation_access,
    nutrition_goal=nutrition_goal,
    snap_preference=snap_preference,
    dietary_preference=dietary_preference,
    access_context=access_context,
    top_n=top_n,
)

nutrition_df = get_nutrition_suggestions(nutrition_goal, dietary_preference, limit=10)

st.subheader("1. Area Food Access Summary")
low_income_text = "Yes" if int(access_context.get("estimated_low_income", 0)) == 1 else "No"
low_access_text = "Yes" if int(access_context.get("estimated_low_access", 0)) == 1 else "No"

st.markdown(
    f"""
    <div class="card">
        <strong>ZIP entered:</strong> {zip_code} ({zip_centroid['city']}, {zip_centroid['state']})<br/>
        <strong>County:</strong> {zip_centroid['county']}<br/>
        <strong>Estimated low-income indicator:</strong> {low_income_text}<br/>
        <strong>Estimated low-access indicator:</strong> {low_access_text}<br/>
        <strong>Context note:</strong> {access_context.get('access_notes', 'N/A')}
    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("2. Ranked Recommendations")
if recommendations.empty:
    st.warning("No recommendations matched your current filters. Try selecting 'show all options' for SNAP preference.")
else:
    if budget_level == "low" and total_matches < top_n:
        st.info(f"Only {total_matches} low-budget stores found for your selected filters.")

    for idx, row in recommendations.iterrows():
        snap_tag = "SNAP" if int(row["snap_authorized"]) == 1 else "Non-SNAP"
        if dietary_preference == "vegetarian":
            diet_ok = int(row.get("vegetarian_friendly", 0)) == 1
            diet_tag = "Vegetarian-friendly" if diet_ok else "Not vegetarian-focused"
        elif dietary_preference == "vegan":
            diet_ok = int(row.get("vegan_friendly", 0)) == 1
            diet_tag = "Vegan-friendly" if diet_ok else "Not vegan-focused"
        elif dietary_preference == "gluten free":
            diet_ok = int(row.get("gluten_free_friendly", 0)) == 1
            diet_tag = "Gluten-free friendly" if diet_ok else "Not gluten-free focused"
        else:
            diet_tag = "General diet options"

        pill_items = []
        if idx == 0:
            pill_items.append("⭐ Top Pick")
        pill_items.extend(
            [
                snap_tag,
                f"{row['price_level'].title()} budget fit",
                diet_tag,
                row["resource_type"].replace("_", " ").title(),
            ]
        )
        if str(row.get("discount_program", "")).strip():
            pill_items.append(f"Discount partner: {row['discount_program']}")
        pills_html = "".join([f'<span class="pill">{item}</span>' for item in pill_items])

        reason_points = [
            item.strip().capitalize()
            for item in str(row["recommendation_reason"]).replace(".", "").split(";")
            if item.strip()
        ]
        why_list_html = "".join([f"<li>{point}</li>" for point in reason_points])

        st.markdown(
            f"""
            <div class="card">
                <div>
                    <strong>{row['name']}</strong>
                </div>
                <div class="muted">{row['address']} ({row['zip']})</div>
                <div style="margin-top: 6px; margin-bottom: 6px;">{pills_html}</div>
                <div><strong>Approx. distance:</strong> {row['distance_miles']:.1f} miles</div>
                <div><strong>Discount/Waste program confidence:</strong> {row.get('discount_confidence', '') or 'Unknown'}</div>
                <div><strong>Why recommended:</strong></div>
                <ul style="margin-top: 4px; margin-bottom: 6px;">{why_list_html}</ul>
                <div class="muted">{score_breakdown_text(row)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.expander("Show recommendations on map"):
        map_df = recommendations_to_map_frame(recommendations)
        map_df["marker_size"] = 14
        fig = px.scatter_mapbox(
            map_df,
            lat="latitude",
            lon="longitude",
            hover_name="name",
            custom_data=["address", "distance_miles", "resource_type"],
            color="final_score",
            size="marker_size",
            size_max=18,
            zoom=10,
            height=540,
            color_continuous_scale="Blues",
        )
        fig.update_traces(marker={"opacity": 0.95})
        fig.update_traces(
            hovertemplate=(
                "<b>%{hovertext}</b><br>"
                "Address: %{customdata[0]}<br>"
                "Distance (miles): %{customdata[1]:.1f}<br>"
                "Resource Type: %{customdata[2]}<extra></extra>"
            )
        )
        fig.update_layout(
            mapbox_style="open-street-map",
            margin={"r": 0, "t": 0, "l": 0, "b": 0},
            coloraxis_showscale=False,
        )
        st.plotly_chart(fig, use_container_width=True)

st.subheader("3. Nutrition Explorer")
st.caption(
    "Foods are chosen to align with your goal. The app uses FoodData Central API when API key is available, otherwise local seed data."
)

if nutrition_df.empty:
    st.warning("No nutrition suggestions available right now.")
else:
    for col in ["calories_kcal", "protein_g", "fat_g", "carbs_g", "fiber_g"]:
        if col in nutrition_df.columns:
            nutrition_df[col] = pd.to_numeric(nutrition_df[col], errors="coerce").round(1)

    nutrition_display = nutrition_df.rename(
        columns={
            "food_name": "Food",
            "calories_kcal": "Calories",
            "protein_g": "Protein (grams)",
            "fat_g": "Fat (grams)",
            "carbs_g": "Carbohydrates (grams)",
            "fiber_g": "Fiber (grams)",
        }
    )
    for col in ["Calories", "Protein (grams)", "Fat (grams)", "Carbohydrates (grams)", "Fiber (grams)"]:
        if col in nutrition_display.columns:
            nutrition_display[col] = nutrition_display[col].where(nutrition_display[col].notna(), "N/A")

    st.dataframe(
        nutrition_display[
            [
                "Food",
                "Calories",
                "Protein (grams)",
                "Fat (grams)",
                "Carbohydrates (grams)",
                "Fiber (grams)",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

st.subheader("4. Why This Is Transparent")
st.write(
    "Recommendations use a visible weighted formula rather than a black-box model. Each card shows the score rationale so users can audit why an option ranked higher or lower."
)
