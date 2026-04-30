"""About page for methodology, limitations, and extension roadmap."""

import plotly.express as px
import streamlit as st

from utils.data_loader import get_coverage_overview, get_state_coverage_frame
from utils.recommender import get_scoring_weights

st.set_page_config(page_title="About | Affordable Food Access Navigator", page_icon="ℹ️", layout="wide")

st.title("About & Methodology")

st.markdown(
    """
Affordable Food Access Navigator is an MVP recommendation app designed for quick, practical food decision support.
It combines local context, nearby resource options, and nutrition guidance into one workflow.
"""
)

st.header("Methodology")
st.markdown(
    """
1. User inputs ZIP code and constraints (budget, transportation, SNAP preference, nutrition goal, dietary preference).
2. ZIP-level context is loaded from local sample CSV (proxy for tract-level USDA Food Access indicators).
3. Candidate retailers/resources are filtered and scored using transparent weighted logic:
   - affordability: 30%
   - transportation fit: 20%
   - nutrition fit: 25%
   - SNAP alignment: 15%
   - proximity: 10%
4. Top recommendations are shown with score explanations and reason text.
5. Nutrition Explorer returns example foods via USDA FoodData Central API (if API key exists) or local fallback data.
"""
)

st.header("Scoring Logic")
weights = get_scoring_weights()
st.markdown(
    """
Recommendations use a transparent weighted score (not a black-box model):

`score = affordability*0.30 + transportation*0.20 + nutrition*0.25 + snap*0.15 + proximity*0.10`
"""
)
pretty_factors = {
    "affordability_score": "Affordability Score",
    "transportation_score": "Transportation Score",
    "nutrition_score": "Nutrition Score",
    "snap_score": "SNAP Score",
    "proximity_score": "Proximity Score",
}
weights_df = {
    "Factor": [pretty_factors.get(k, k.replace("_", " ").title()) for k in weights.keys()],
    "Weight": list(weights.values()),
}
st.dataframe(weights_df, use_container_width=True, hide_index=True)
st.caption("Each recommendation card also shows its own score breakdown for transparency.")

st.header("Current Data Strategy")
st.markdown(
    """
- MVP uses local sample CSVs for reliable demos.
- Architecture is built to swap in production datasets without changing UI behavior.
- Recommended production upgrade path:
  - USDA Food Access Research Atlas tract-level joins (ZIP -> tract mapping)
  - USDA SNAP retailer data refresh pipeline
  - Optional local food bank and farmers market integrations
"""
)

st.header("Coverage Status")
coverage = get_coverage_overview()
metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
metric_col1.metric("ZIPs in reference", f"{coverage['zip_reference_count']:,}")
metric_col2.metric("Food-access ZIPs", f"{coverage['food_access_count']:,}")
metric_col3.metric("Retailer ZIPs", f"{coverage['retailer_zip_count']:,}")
metric_col4.metric("Retailer stores", f"{coverage['retailer_store_count']:,}")
st.caption(
    f"Estimated US ZIP coverage from loaded ZIP reference: {coverage['zip_reference_coverage_pct']}% "
    f"({coverage['zip_reference_count']:,} of ~{coverage['estimated_us_zip_total']:,})."
)

state_cov = get_state_coverage_frame()
map_fig = px.choropleth(
    state_cov,
    locations="state",
    locationmode="USA-states",
    color="zip_reference_count",
    scope="usa",
    hover_data={
        "zip_reference_count": True,
        "food_access_count": True,
        "retailer_zip_count": True,
    },
    color_continuous_scale="Blues",
    title="US Coverage Map (ZIP Reference Count by State)",
)
map_fig.update_layout(
    margin={"r": 0, "t": 40, "l": 0, "b": 0},
    coloraxis_colorbar_title_text="Count of ZIPs",
)
st.plotly_chart(map_fig, use_container_width=True)

with st.expander("View state coverage table"):
    state_cov_display = state_cov.rename(
        columns={
            "state": "State",
            "zip_reference_count": "ZIP Reference Count",
            "food_access_count": "Food Access Count",
            "retailer_zip_count": "Retailer ZIP Count",
        }
    )
    st.dataframe(state_cov_display, use_container_width=True, hide_index=True)

st.header("Limitations")
st.markdown(
    """
- ZIP-level food access context is approximate and not exact tract-level attribution.
- Distances are centroid-to-point approximations, not routing/travel-time estimates.
- Retailer list is sample data in MVP mode.
- Nutrition suggestions may use fallback sample foods if API key is missing or API is unavailable.
- Price level uses coarse categories (low/medium/high), not item-level pricing.
"""
)

st.header("Future Improvements")
st.markdown(
    """
- Add precise tract lookup and USDA atlas field mapping.
- Integrate transit-aware travel time and walkability scores.
- Add food banks, farmers markets, and co-op directories as modular data sources.
- Add personalized meal suggestions and weekly budget planning.
- Introduce multilingual support and accessibility-first UX refinements.
- Add periodic ETL jobs for automatic dataset updates.
"""
)
