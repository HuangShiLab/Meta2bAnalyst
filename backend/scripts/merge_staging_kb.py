#!/usr/bin/env python3
"""
Merge mined literature staging into the knowledge base.

Reads structured extraction results from
``backend/knowledge_staging/papers/<PMID>.json`` (produced by
``scripts/literature_mine.py``) and merges them into
``app/knowledge/taxon_db.json`` / ``app/knowledge/disease_db.json``.

Safety rules
------------
- Dry-run by default: prints a diff summary, writes nothing. ``--apply``
  is required to modify the KB files.
- By default only ``quote_verified`` associations are merged
  (``--include-unverified`` to relax).
- Existing ``disease_associations`` entries are NEVER overwritten.
  Conflicts between KB and literature are printed for human review.
- Direction conflicts *within* the literature resolve to ``"mixed"`` and
  keep provenance from both sides.
- New taxa/diseases get skeleton entries marked ``auto_generated: true``
  with ``[CURATE]`` placeholders in notes -- an explicit signal that a
  human must fill in biology before trusting the entry.

Schema extension
----------------
Merged taxon entries gain::

    "disease_evidence": {
        "<condition>": [
            {"pmid": "...", "year": "2012", "direction": "enriched",
             "study_type": "case_control", "cohort_size": 120,
             "quote_verified": true, "journal": "..."},
            ...
        ]
    }

``disease_associations`` keeps the aggregated direction word
(enriched / depleted / mixed) so existing consumers stay compatible.
Disease entries gain a parallel ``literature_evidence`` map.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
STAGING_DIR = BACKEND_DIR / "knowledge_staging" / "papers"
TAXON_DB = BACKEND_DIR / "app" / "knowledge" / "taxon_db.json"
DISEASE_DB = BACKEND_DIR / "app" / "knowledge" / "disease_db.json"

# Higher weight = stronger evidence when directions disagree.
STUDY_TYPE_WEIGHT = {
    "rct": 6,
    "meta_analysis": 6,
    "systematic_review": 5,
    "cohort": 4,
    "case_control": 3,
    "cross_sectional": 3,
    "review": 2,
    "in_vitro": 1,
    "animal": 1,
    "other": 1,
}

# Common condition spellings seen in mining -> disease_db keys.
CONDITION_ALIASES = {
    "periodontitis": "periodontal_disease",
    "periodontal_disease": "periodontal_disease",
    "gum_disease": "periodontal_disease",
    "gingivitis": "periodontal_disease",
    "peri_implantitis": "periodontal_disease",
    "chronic_periodontitis": "periodontal_disease",
    "dental_periodontitis": "periodontal_disease",
    "stage_iii_periodontitis": "periodontal_disease",
    "aggressive_periodontitis": "periodontal_disease",
    "caries": "dental_caries",
    "dental_caries": "dental_caries",
    "tooth_decay": "dental_caries",
    "early_childhood_caries": "dental_caries",
    "untreated_dental_caries": "dental_caries",
    "root_caries": "dental_caries",
    "high_blood_pressure": "hypertension",
    "oral_cancer": "oral_cancer",
    "oral_squamous_cell_carcinoma": "oral_cancer",
    "oscc": "oral_cancer",
    "halitosis": "halitosis",
    "oral_lichen_planus": "oral_lichen_planus",
}

# LLM sometimes extracts demographics, diets, symptoms, or clinical
# measures as "conditions". These are not KB diseases -- drop them.
CONDITION_BLOCKLIST = {
    "healthy", "control", "female", "male", "elderly", "children",
    "chimpanzee", "mouse", "rat",
    "dry_food_diet", "wet_food_diet", "high_sugar_diet",
    "high_sugar_beverage_consumption", "high_sugar_high_fat_diet",
    "western_diet", "diet",
    "gingival_bleeding", "high_bleeding_on_probing", "tooth_pain",
    "dental_calculus", "plaque_index", "pocket_depth",
    "high_s_cristatus_p_gingivalis_ratio", "low_s_cristatus_p_gingivalis_ratio",
}

RANKS = {"species", "genus", "family", "order", "class", "phylum"}


def normalize_condition(cond: str) -> str:
    key = str(cond or "").strip().lower().replace(" ", "_").replace("-", "_")
    return CONDITION_ALIASES.get(key, key)


def normalize_taxon(name: str) -> str:
    text = str(name or "").strip()
    if "|" in text:
        text = text.split("|")[-1]
    if ";" in text:
        text = text.split(";")[-1]
    text = text.strip()
    if len(text) > 3 and text[1:3] == "__":
        text = text[3:]
    return text.replace(" ", "_").replace("-", "_").strip("_").lower()


def kb_key_for(normalized: str, existing_keys) -> str | None:
    """Find the KB key a normalized taxon name maps to (exact or unique prefix)."""
    norm_map = {normalize_taxon(k): k for k in existing_keys}
    if normalized in norm_map:
        return norm_map[normalized]
    prefix = [k for n, k in norm_map.items() if n.startswith(normalized + "_")]
    if len(prefix) == 1:
        return prefix[0]
    return None


def evidence_weight(ev: dict) -> float:
    w = STUDY_TYPE_WEIGHT.get(str(ev.get("study_type") or "other").lower(), 1)
    if not ev.get("quote_verified"):
        w *= 0.5
    return float(w)


def aggregate_direction(evidences: list[dict]) -> str:
    """Weighted vote; comparable support for both sides -> 'mixed'."""
    score = defaultdict(float)
    for ev in evidences:
        d = str(ev.get("direction") or "").lower()
        if d in ("enriched", "depleted"):
            score[d] += evidence_weight(ev)
    if not score:
        return "associated"
    if len(score) == 2:
        lo, hi = sorted(score.values())
        if lo / hi >= 0.5:  # within a factor of two -> genuinely mixed
            return "mixed"
    return max(score, key=score.get)


def load_staging(staging_dir: Path, verified_only: bool):
    """Yield (paper_meta, association) pairs from staging JSON files."""
    files = sorted(staging_dir.glob("*.json"))
    if not files:
        sys.exit(f"No staging papers found in {staging_dir}")
    for path in files:
        paper = json.loads(path.read_text(encoding="utf-8"))
        meta = {
            "pmid": paper.get("pmid") or path.stem.split("_")[0].replace("PMID", ""),
            "year": paper.get("year"),
            "journal": paper.get("journal"),
            "study_type": paper.get("study_type"),
            "cohort_size": paper.get("cohort_size"),
        }
        for assoc in paper.get("associations", []):
            if verified_only and not assoc.get("quote_verified"):
                continue
            if not assoc.get("taxon") or not assoc.get("condition"):
                continue
            yield meta, assoc


def build_skeleton_taxon(display_name: str, rank: str) -> dict:
    return {
        "gram_stain": None,
        "oxygen": None,
        "main_products": [],
        "known_functions": [],
        "rank": rank,
        "disease_associations": {},
        "health_markers": [],
        "notes": "[CURATE] auto-generated from literature mining; "
                 "gram_stain/oxygen/functions need manual curation.",
        "auto_generated": True,
    }


def merge(staging_dir: Path, apply: bool, verified_only: bool,
          taxon_db_path: Path = TAXON_DB, disease_db_path: Path = DISEASE_DB) -> int:
    taxon_db = json.loads(taxon_db_path.read_text(encoding="utf-8"))
    disease_db = json.loads(disease_db_path.read_text(encoding="utf-8"))

    # Aggregate evidence per (kb taxon key or new name, condition)
    buckets = defaultdict(list)          # (taxon_key, condition) -> [evidence]
    taxon_display = {}                   # taxon_key -> display name / rank
    skipped_conflict = []                # KB already has a direction
    unmatched_conditions = set()
    n_blocked = 0                        # non-disease "conditions" dropped

    for meta, assoc in load_staging(staging_dir, verified_only):
        norm = normalize_taxon(assoc["taxon"])
        if not norm:
            continue
        rank = str(assoc.get("taxon_rank") or "species").lower()
        if rank not in RANKS:
            rank = "species"
        condition = normalize_condition(assoc["condition"])
        if condition in CONDITION_BLOCKLIST:
            n_blocked += 1
            continue

        kb_key = kb_key_for(norm, taxon_db.keys())
        if kb_key is None:
            # New entry: use normalized name; species keep Genus_species form.
            kb_key = norm
            taxon_display.setdefault(kb_key, (assoc["taxon"].strip(), rank))
        else:
            taxon_display.setdefault(kb_key, (kb_key, rank))

        ev = {
            "pmid": meta["pmid"],
            "year": meta.get("year"),
            "journal": meta.get("journal"),
            "study_type": meta.get("study_type"),
            "cohort_size": meta.get("cohort_size"),
            "direction": assoc.get("direction"),
            "quote_verified": bool(assoc.get("quote_verified")),
            "evidence_quote": assoc.get("evidence_quote"),
        }
        buckets[(kb_key, condition)].append(ev)

    n_new_taxa = n_new_assoc = n_evidence = 0
    for (taxon_key, condition), evidences in sorted(buckets.items()):
        direction = aggregate_direction(evidences)

        if taxon_key not in taxon_db:
            display, rank = taxon_display[taxon_key]
            taxon_db[taxon_key] = build_skeleton_taxon(display, rank)
            n_new_taxa += 1

        entry = taxon_db[taxon_key]
        entry.setdefault("disease_associations", {})
        entry.setdefault("disease_evidence", {})

        existing = entry["disease_associations"].get(condition)
        if existing:
            if existing != direction:
                skipped_conflict.append((taxon_key, condition, existing, direction))
            # Still record evidence provenance, but don't touch the direction.
        else:
            entry["disease_associations"][condition] = direction
            n_new_assoc += 1

        seen = {(e.get("pmid"), e.get("direction")) for e in entry["disease_evidence"].get(condition, [])}
        fresh = [e for e in evidences if (e["pmid"], e["direction"]) not in seen]
        entry["disease_evidence"].setdefault(condition, []).extend(fresh)
        n_evidence += len(fresh)

        # Mirror into disease_db
        if condition in disease_db:
            d = disease_db[condition]
            d.setdefault("literature_evidence", {})
            d["literature_evidence"].setdefault(taxon_key, []).extend(
                [{k: e[k] for k in ("pmid", "year", "direction", "study_type")}
                 for e in fresh]
            )
            genus = taxon_key.split("_")[0]
            if genus and genus.capitalize() not in [g for g in d.get("key_genera", [])]:
                if taxon_display[taxon_key][1] in ("genus", "species"):
                    d.setdefault("key_genera", []).append(genus.capitalize())
        else:
            unmatched_conditions.add(condition)

    # ── Report ────────────────────────────────────────────────────
    print(f"staging dir        : {staging_dir}")
    print(f"verified-only      : {verified_only}")
    print(f"(taxon,condition)  : {len(buckets)}")
    print(f"new taxa           : {n_new_taxa}")
    print(f"new associations   : {n_new_assoc}")
    print(f"evidence records   : {n_evidence}")
    print(f"blocked non-disease: {n_blocked}")
    if skipped_conflict:
        print(f"\nCONFLICTS with existing KB (kept KB direction, review manually): "
              f"{len(skipped_conflict)}")
        for taxon_key, condition, old, new in skipped_conflict[:20]:
            print(f"  {taxon_key} / {condition}: KB={old} literature={new}")
    if unmatched_conditions:
        print(f"\nConditions NOT in disease_db (not mirrored): "
              f"{sorted(unmatched_conditions)}")

    if not apply:
        print("\nDRY-RUN: no files written. Re-run with --apply to merge.")
        return 0

    taxon_db_path.write_text(json.dumps(taxon_db, indent=1, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    disease_db_path.write_text(json.dumps(disease_db, indent=1, ensure_ascii=False) + "\n",
                               encoding="utf-8")
    print(f"\nWROTE {taxon_db_path}")
    print(f"WROTE {disease_db_path}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--staging-dir", type=Path, default=STAGING_DIR)
    ap.add_argument("--taxon-db", type=Path, default=TAXON_DB)
    ap.add_argument("--disease-db", type=Path, default=DISEASE_DB)
    ap.add_argument("--apply", action="store_true",
                    help="actually write the KB files (default: dry-run)")
    ap.add_argument("--include-unverified", action="store_true",
                    help="also merge associations whose evidence quote failed verification")
    args = ap.parse_args()
    return merge(args.staging_dir, args.apply, not args.include_unverified,
                 taxon_db_path=args.taxon_db, disease_db_path=args.disease_db)


if __name__ == "__main__":
    sys.exit(main())
