"""Build retailer-level discount/waste-program flags.

Inputs:
- data/usda/snap_retailers_us.csv
- data/enrichment/discount_programs_public.csv

Output:
- data/usda/retailer_discount_flags.csv
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
USDA = ROOT / "data" / "usda"
ENRICH = ROOT / "data" / "enrichment"


def _norm(s: str) -> str:
    return "".join(ch for ch in str(s).lower().strip() if ch.isalnum() or ch.isspace())


def build() -> pd.DataFrame:
    retailers = pd.read_csv(USDA / "snap_retailers_us.csv", dtype={"zip": str})
    refs = pd.read_csv(ENRICH / "discount_programs_public.csv", dtype={"zip": str})

    retailers["_name_norm"] = retailers["name"].fillna("").map(_norm)
    retailers["_zip"] = retailers["zip"].astype(str).str.zfill(5)

    rows = []
    for _, ref in refs.iterrows():
        scope = str(ref.get("coverage_scope", "")).strip().lower()
        chain = _norm(ref.get("chain_name", ""))
        store = _norm(ref.get("store_name", ""))
        zip_code = str(ref.get("zip", "")).strip().zfill(5) if str(ref.get("zip", "")).strip() else ""

        cand = retailers
        match_level = "none"
        if scope == "chain" and chain:
            cand = cand[cand["_name_norm"].str.contains(chain, na=False)]
            match_level = "chain"
        elif scope == "city" and zip_code:
            cand = cand[cand["_zip"] == zip_code]
            match_level = "zip"
        elif scope == "store" and store:
            cand = cand[cand["_name_norm"] == store]
            match_level = "store_exact"
        elif zip_code:
            cand = cand[cand["_zip"] == zip_code]
            match_level = "zip"

        for _, r in cand.iterrows():
            rows.append(
                {
                    "id": int(r["id"]),
                    "program_name": ref.get("program_name", "Unknown"),
                    "program_type": ref.get("program_type", "discount"),
                    "match_level": match_level,
                    "confidence": ref.get("confidence", "medium"),
                    "evidence_url": ref.get("evidence_url", ""),
                    "last_verified": ref.get("last_verified", ""),
                    "notes": ref.get("notes", ""),
                }
            )

    if not rows:
        out = pd.DataFrame(
            columns=[
                "id",
                "program_name",
                "program_type",
                "match_level",
                "confidence",
                "evidence_url",
                "last_verified",
                "notes",
            ]
        )
    else:
        out = pd.DataFrame(rows)
        out = out.sort_values(by=["id", "program_name", "match_level"]).drop_duplicates(subset=["id", "program_name"])

    return out


def main() -> None:
    USDA.mkdir(parents=True, exist_ok=True)
    out = build()
    target = USDA / "retailer_discount_flags.csv"
    out.to_csv(target, index=False)
    print(f"Wrote {target} ({len(out):,} rows)")


if __name__ == "__main__":
    main()
