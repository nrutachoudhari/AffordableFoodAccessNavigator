# Affordable Food Access Navigator

A Streamlit MVP that helps people find affordable and healthy food options based on ZIP code, transportation access, budget, SNAP preference, and nutrition goals.

Created for the Codex Creator Challenge: https://duke.joinhandshake.com/codex-creator-challenge

## What This MVP Does

- Collects user inputs:
  - ZIP code
  - budget level (`all`, `low`, `medium`, `high`)
  - transportation access (`car`, `no car`)
  - nutrition goal (`high protein`, `low fat`, `balanced`, `high fiber`)
  - SNAP preference (`show SNAP-authorized locations only`, `show all options`)
  - dietary preference (`vegetarian`, `no preference`)
- Shows a food access context summary for the selected ZIP.
- Includes an About-page coverage dashboard with state-level US map visualization.
- Ranks nearby stores/resources with a transparent weighted score.
- Displays recommendation cards with plain-English explanations.
- Provides a nutrition explorer with nutrient values (calories, protein, fat, carbs, fiber).
- Uses USDA FoodData Central API when key is available, with local fallback if not.

## Project Structure

```text
Affordable Food Access Navigator/
├── app.py
├── requirements.txt
├── .env.example
├── README.md
├── data/
│   ├── zip_reference.csv
│   ├── food_access_context.csv
│   ├── retailers.csv
│   ├── nutrition_seed_foods.csv
│   └── enrichment/
│       └── discount_programs_public.csv
├── utils/
│   ├── data_loader.py
│   ├── location.py
│   ├── recommender.py
│   └── nutrition.py
├── scripts/
│   ├── build_usda_datasets.py
│   └── build_discount_matches.py
└── pages/
    └── about.py
```

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Add environment variables:

```bash
cp .env.example .env
```

4. (Optional) Add your USDA FoodData Central API key in `.env`:

```env
FDC_API_KEY=your_api_key_here
```

5. Run app:

```bash
streamlit run app.py
```

## Nationwide USDA Data Mode (All US ZIPs/States)

The app now uses a USDA-first loading strategy:
- If nationwide processed files exist in `data/usda/`, they are used automatically.
- If not, the app falls back to local demo CSVs so the MVP still runs.

### Build nationwide files

1. Put raw files in `data/raw/`:
   - `zip_reference_us.csv`
   - `food_access_atlas.csv`
   - `zip_tract_crosswalk.csv`
   - `snap_retailers_raw.csv`
2. Run:

```bash
python scripts/build_usda_datasets.py
```

3. The script writes:
   - `data/usda/zip_reference_us.csv`
   - `data/usda/food_access_zip_us.csv`
   - `data/usda/snap_retailers_us.csv`

## Methodology Note (MVP)

The recommendation score is transparent and rule-based:

```text
score =
  affordability_score * 0.30 +
  transportation_score * 0.20 +
  nutrition_score * 0.25 +
  snap_score * 0.15 +
  proximity_score * 0.10
```

Why this helps:
- It avoids black-box ranking.
- Each recommendation displays factor-level explanations.
- Users can understand and challenge recommendation logic.

## Data Notes and How To Replace Sample Data

This MVP can run in either:
- Demo mode (local sample CSVs), or
- USDA nationwide mode (processed files in `data/usda/`).

### 1) USDA Food Access Research Atlas
- Current state:
  - Demo: `data/food_access_context.csv` (approximate ZIP-level sample)
  - USDA mode: `data/usda/food_access_zip_us.csv` (derived from tract indicators and ZIP-tract crosswalk)
- Upgrade path:
  - Load tract-level atlas data.
  - Map ZIP to Census tract using a ZIP-tract crosswalk.
  - Rebuild processed files with `scripts/build_usda_datasets.py`.

### 2) USDA SNAP Retailer Data
- Current state:
  - Demo: `data/retailers.csv`
  - USDA mode: `data/usda/snap_retailers_us.csv`
- Upgrade path:
  - Put SNAP export into `data/raw/snap_retailers_raw.csv`.
  - Run `scripts/build_usda_datasets.py`.
  - Optionally enrich pricing/category fields via a separate enrichment pass.

### 2b) Discount / Food-Waste Program Enrichment (publicly curation-based)
- Input file: `data/enrichment/discount_programs_public.csv`
- Build flags:

```bash
python scripts/build_discount_matches.py
```

- Output file: `data/usda/retailer_discount_flags.csv`
- The app automatically merges these flags and displays:
  - discount partner badges on recommendation cards
  - discount confidence labels

Notes:
- This is a practical MVP approach when no universal open API exists for markdown/food-waste programs.
- Keep `evidence_url`, `last_verified`, and `confidence` updated for transparency.

### 3) USDA FoodData Central Nutrition
- Current state: `utils/nutrition.py` calls API if `FDC_API_KEY` exists.
- Fallback: local `data/nutrition_seed_foods.csv` if API unavailable.
- Upgrade path:
  - Expand search queries and handle branded/common foods by user context.
  - Add caching layer to reduce repeated API calls.
  - Keep user-facing labels in US nutrition style (e.g., `Protein (grams)`).

## Limitations

- ZIP-level context is approximate and can differ from tract-level truth.
- Distance is straight-line approximation, not routing/travel-time.
- Sample retailer data is not complete market coverage.
- Price-level indicators are coarse categories, not item-level prices.
- Nutrition results can vary depending on API coverage and matching.

## Future Improvements

- Add precise tract-level geospatial joins for access indicators.
- Add transit-aware travel-time calculations.
- Integrate additional sources:
  - food banks
  - farmers markets
  - discount surplus-food options
- Add user accounts and saved preferences.
- Add stronger accessibility and multilingual UX.
- Add evaluation dashboard for fairness and recommendation quality.
- Add scheduled refresh jobs for both USDA SNAP and discount-program curation data.

## ZIP Coverage

- With USDA nationwide files in `data/usda/`, the app supports pan-US ZIP coverage.
- Without those files, the app still accepts any valid ZIP and resolves most ZIPs via offline `pgeocode` US data.
- If both local lookup and offline lookup fail, it uses a national-center fallback for continuity.