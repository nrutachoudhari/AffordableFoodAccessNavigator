# USDA Processed Data (Nationwide)

If these files exist, the app uses them automatically instead of demo CSV files.

Required files:
- `zip_reference_us.csv`
- `food_access_zip_us.csv`
- `snap_retailers_us.csv`

These files should cover all US ZIP codes/states for nationwide behavior.

Build them from raw datasets with:

```bash
python scripts/build_usda_datasets.py
```
