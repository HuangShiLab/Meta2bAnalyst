#!/usr/bin/env python3
"""
Mine taxon-condition associations from PubMed abstracts for papers
without open-access full text.

For each PMID, fetches title/abstract/year/journal via NCBI E-utilities,
then calls the LLM to extract structured associations.

Output format is compatible with literature_mine.py:
  knowledge_staging/papers/PMID<pmid>.json
  knowledge_staging/associations.jsonl  (appended)

Usage:
    venv/bin/python3 scripts/mine_no_oa_abstracts.py [--pmid-file PATH]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("mine_no_oa")

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.config import settings

STAGING_DIR = BACKEND / "knowledge_staging"
PAPERS_DIR = STAGING_DIR / "papers"
ASSOC_PATH = STAGING_DIR / "associations.jsonl"

VALID_DIRECTIONS = {"enriched", "depleted", "mixed"}
VALID_RANKS = {"species", "genus", "family", "order", "class", "phylum", "other"}

SYSTEM_PROMPT = """You are a microbiome literature mining assistant. Extract taxon-condition
associations from the PAPER ABSTRACT provided by the user.

IMPORTANT: You are working from an ABSTRACT, not a full text. Extract ONLY associations
that are explicitly stated in the abstract. Do NOT infer associations from the full paper.

Return ONLY a JSON object (no markdown fences, no commentary) with this schema:
{
  "title": string,           // paper title as printed
  "year": string|null,       // publication year if visible
  "journal": string|null,
  "niche": string,           // e.g. "oral_saliva", "oral_plaque", "gut", "skin", "vaginal", "other"
  "study_type": string,      // "cohort" | "case_control" | "RCT" | "in_vitro" | "animal" | "review" | "other"
  "cohort_size": int|null,   // total human subjects if stated in abstract, else null
  "associations": [
    {
      "taxon": string,       // scientific name, e.g. "Porphyromonas gingivalis" or "Prevotella"
      "taxon_rank": string,  // one of species|genus|family|order|class|phylum|other
      "condition": string,   // disease/condition in snake_case English, e.g. "periodontal_disease", "dental_caries", "healthy"
      "direction": string,   // "enriched" | "depleted" | "mixed"  (in condition vs control)
      "evidence_quote": string  // VERBATIM sentence or phrase copied from the ABSTRACT that supports this association
    }
  ]
}

Rules:
- Only extract associations the ABSTRACT explicitly reports.
- direction describes the taxon IN the condition relative to the comparison baseline.
- evidence_quote MUST be copied character-for-character from the abstract text (a single sentence or clause).
- If the abstract reports no usable taxon-level associations, return an empty "associations" list.
- Do not invent PMIDs, cohort sizes, or taxa.
"""


def fetch_pubmed_records(pmids: list[str]) -> dict[str, dict]:
    """Fetch PubMed records via E-utilities efetch, return dict keyed by PMID."""
    url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        f"?db=pubmed&id={','.join(pmids)}&retmode=xml"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "meta2banalyst/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        xml_data = resp.read()

    root = ET.fromstring(xml_data)
    records = {}

    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        pmid = pmid_el.text if pmid_el is not None else ""
        if not pmid:
            continue

        # Title
        title_el = article.find(".//ArticleTitle")
        title = "".join(title_el.itertext()) if title_el is not None else ""

        # Abstract
        abstract_els = article.findall(".//AbstractText")
        abstract = " ".join("".join(el.itertext()) for el in abstract_els)

        # Journal
        journal_el = article.find(".//Journal/Title")
        journal = journal_el.text if journal_el is not None else None

        # Year
        year_el = article.find(".//PubDate/Year") or article.find(".//DateCompleted/Year")
        year = year_el.text if year_el is not None else None

        records[pmid] = {
            "title": title,
            "abstract": abstract,
            "journal": journal,
            "year": year,
        }

    return records


def normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def verify_quote(quote: str, text: str) -> bool:
    """Evidence honesty guard: the quote must exist in the text."""
    if not quote or len(quote) < 15:
        return False
    hay = normalize_ws(text)
    needle = normalize_ws(quote)
    if needle in hay:
        return True
    return len(needle) >= 40 and needle[:40] in hay


def chat_json(client_cfg: dict, user_prompt: str, max_tokens: int = 4000) -> dict:
    payload = {
        "model": client_cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        f"{client_cfg['base_url']}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {client_cfg['api_key']}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        response = json.loads(r.read().decode())
    content = response["choices"][0]["message"]["content"]
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    return json.loads(content)


def validate_association(a: dict, text: str) -> dict:
    out = {
        "taxon": str(a.get("taxon", "")).strip(),
        "taxon_rank": str(a.get("taxon_rank", "other")).strip().lower(),
        "condition": str(a.get("condition", "")).strip().lower().replace(" ", "_"),
        "direction": str(a.get("direction", "")).strip().lower(),
        "evidence_quote": str(a.get("evidence_quote", "")).strip(),
    }
    problems = []
    if not out["taxon"]:
        problems.append("missing taxon")
    if out["taxon_rank"] not in VALID_RANKS:
        out["taxon_rank"] = "other"
    if out["direction"] not in VALID_DIRECTIONS:
        problems.append(f"bad direction: {out['direction']!r}")
    out["quote_verified"] = verify_quote(out["evidence_quote"], text)
    if not out["quote_verified"]:
        problems.append("quote not found verbatim in text")
    out["problems"] = problems
    return out


def mine_abstract(pmid: str, record: dict, client_cfg: dict) -> dict:
    text = record["abstract"]
    if len(text) < 200:
        raise ValueError(f"abstract too short ({len(text)} chars)")

    user_prompt = (
        f"Paper PMID: {pmid}\n"
        f"Title: {record['title']}\n"
        f"Journal: {record.get('journal') or 'unknown'}\n"
        f"Year: {record.get('year') or 'unknown'}\n\n"
        "=== ABSTRACT ===\n" + text
    )

    raw = chat_json(client_cfg, user_prompt)

    associations = []
    for a in raw.get("associations") or []:
        if isinstance(a, dict):
            associations.append(validate_association(a, text))

    return {
        "pmid": pmid,
        "source_file": f"PMID{pmid}_ABSTRACT.json",
        "title": raw.get("title") or record["title"],
        "year": raw.get("year") or record.get("year"),
        "journal": raw.get("journal") or record.get("journal"),
        "niche": raw.get("niche"),
        "study_type": raw.get("study_type"),
        "cohort_size": raw.get("cohort_size"),
        "n_associations": len(associations),
        "n_quote_verified": sum(1 for a in associations if a["quote_verified"]),
        "associations": associations,
        "abstract_mined": True,  # flag to distinguish from full-text mining
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pmid-file", type=Path, default=STAGING_DIR / "redownload_pmids_remaining.txt")
    ap.add_argument("--sleep", type=float, default=2.0)
    args = ap.parse_args()

    api_key = settings.KIMI_API_KEY
    if not api_key:
        print("KIMI_API_KEY not configured - aborting.", file=sys.stderr)
        return 2
    client_cfg = {
        "api_key": api_key,
        "base_url": settings.KIMI_BASE_URL.rstrip("/"),
        "model": settings.KIMI_MODEL,
    }
    logger.info("LLM endpoint: %s model=%s", client_cfg["base_url"], client_cfg["model"])

    pmids = [l.strip() for l in args.pmid_file.read_text().splitlines() if l.strip()]
    if not pmids:
        print("No PMIDs to process.")
        return 0

    logger.info("Fetching PubMed records for %d PMIDs...", len(pmids))
    # NCBI recommends batches of <=200; we have 11 so single batch is fine.
    records = fetch_pubmed_records(pmids)
    logger.info("Got %d PubMed records.", len(records))

    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    failed: list[dict] = []
    n_ok = 0

    with ASSOC_PATH.open("a") as assoc_f:
        for i, pmid in enumerate(pmids, 1):
            out_path = PAPERS_DIR / f"PMID{pmid}.json"
            if out_path.exists():
                logger.info("[%d/%d] SKIP (already mined): PMID%s", i, len(pmids), pmid)
                n_ok += 1
                continue

            record = records.get(pmid)
            if not record:
                failed.append({"pmid": pmid, "reason": "PubMed record not found"})
                logger.warning("[%d/%d] FAIL PMID%s: PubMed record not found", i, len(pmids), pmid)
                continue
            if not record.get("abstract"):
                failed.append({"pmid": pmid, "reason": "no abstract available"})
                logger.warning("[%d/%d] FAIL PMID%s: no abstract", i, len(pmids), pmid)
                continue

            try:
                result = mine_abstract(pmid, record, client_cfg)
                out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
                for a in result["associations"]:
                    assoc_f.write(json.dumps({
                        "pmid": result["pmid"], "paper": result["title"], **a,
                    }, ensure_ascii=False) + "\n")
                n_ok += 1
                logger.info(
                    "[%d/%d] OK PMID%s: %d associations (%d quote-verified)",
                    i, len(pmids), pmid, result["n_associations"], result["n_quote_verified"],
                )
            except Exception as e:
                failed.append({"pmid": pmid, "reason": str(e)[:300]})
                logger.warning("[%d/%d] FAIL PMID%s: %s", i, len(pmids), pmid, e)

            time.sleep(args.sleep)

    if failed:
        failed_path = STAGING_DIR / "failed_abstracts.json"
        failed_path.write_text(json.dumps(failed, ensure_ascii=False, indent=1) + "\n")
        logger.info("Wrote failures to %s", failed_path)

    logger.info("done: %d ok, %d failed", n_ok, len(failed))
    return len(failed)


if __name__ == "__main__":
    raise SystemExit(main())
