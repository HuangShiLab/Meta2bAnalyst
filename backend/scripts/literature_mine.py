#!/usr/bin/env python3
"""Literature mining pipeline: PDF -> structured taxon-condition associations.

Extracts (taxon, condition, direction, evidence) quadruples from microbiome
papers using the configured Kimi LLM, with an honesty guard: every association
must carry a verbatim evidence quote that is verified against the extracted
text; unverifiable or unparseable output goes to the failed/review list, never
into the staging DB.

Output (under --out-dir, default backend/knowledge_staging/):
  papers/<PMID>.json      per-paper extraction (paper meta + associations)
  associations.jsonl      one JSON object per association, all papers
  failed.json             papers that could not be extracted, with reason

Usage (from backend/):
    venv/bin/python3 scripts/literature_mine.py --pdf-dir <dir> [--limit N]

Credentials come from backend/.env (KIMI_API_KEY/KIMI_BASE_URL/KIMI_MODEL).
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("literature_mine")

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

VALID_DIRECTIONS = {"enriched", "depleted", "mixed"}
VALID_RANKS = {"species", "genus", "family", "order", "class", "phylum", "other"}

SYSTEM_PROMPT = """You are a microbiome literature mining assistant. Extract taxon-condition
associations from the paper text provided by the user.

Return ONLY a JSON object (no markdown fences, no commentary) with this schema:
{
  "title": string,           // paper title as printed
  "year": string|null,       // publication year if visible
  "journal": string|null,
  "niche": string,           // e.g. "oral_saliva", "oral_plaque", "gut", "skin", "vaginal", "other"
  "study_type": string,      // "cohort" | "case_control" | "RCT" | "in_vitro" | "animal" | "review" | "other"
  "cohort_size": int|null,   // total human subjects if stated, else null
  "associations": [
    {
      "taxon": string,       // scientific name, e.g. "Porphyromonas gingivalis" or "Prevotella"
      "taxon_rank": string,  // one of species|genus|family|order|class|phylum|other
      "condition": string,   // disease/condition in snake_case English, e.g. "periodontal_disease", "dental_caries", "healthy"
      "direction": string,   // "enriched" | "depleted" | "mixed"  (in condition vs control)
      "evidence_quote": string  // VERBATIM sentence fragment copied from the text that supports this association
    }
  ]
}

Rules:
- Only extract associations the paper actually measured or explicitly cites as established.
- direction describes the taxon IN the condition relative to the comparison baseline.
- evidence_quote MUST be copied character-for-character from the paper text (a single sentence or clause).
- If the paper reports no usable taxon-level associations, return an empty "associations" list.
- Do not invent PMIDs, cohort sizes, or taxa.
"""


def extract_text(pdf_path: Path, max_pages: int = 25) -> str:
    """Extract text from a PDF with pypdf, capped at max_pages."""
    from pypdf import PdfReader

    # Fast integrity gate: failed downloads are often HTML error pages saved
    # with a .pdf suffix; reject before pypdf emits parser noise.
    with open(pdf_path, "rb") as fh:
        if not fh.read(5) == b"%PDF-":
            raise ValueError("not a real PDF (missing %PDF header) - likely a failed download")

    reader = PdfReader(str(pdf_path))
    chunks: List[str] = []
    for page in reader.pages[:max_pages]:
        try:
            chunks.append(page.extract_text() or "")
        except Exception as e:  # single bad page must not kill the paper
            logger.warning("%s: page extraction failed: %s", pdf_path.name, e)
    return "\n".join(chunks)


def pmid_from_filename(name: str) -> Optional[str]:
    m = re.match(r"PMID(\d+)", name)
    return m.group(1) if m else None


def normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def verify_quote(quote: str, text: str) -> bool:
    """Evidence honesty guard: the quote must exist in the extracted text.

    PDF extraction mangles whitespace/hyphenation, so compare on
    whitespace-normalised text and accept a prefix match for long quotes.
    """
    if not quote or len(quote) < 15:
        return False
    hay = normalize_ws(text)
    needle = normalize_ws(quote)
    if needle in hay:
        return True
    # tolerate LLM truncation: quote prefix of >=60 chars present
    return len(needle) >= 60 and needle[:60] in hay


def chat_json(client_cfg: Dict[str, str], user_prompt: str, max_tokens: int = 8000) -> Dict[str, Any]:
    """One chat-completion call that must return a JSON object."""
    payload = {
        "model": client_cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
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
    # tolerate models that ignore response_format and wrap JSON in fences
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    return json.loads(content)


def validate_association(a: Dict[str, Any], text: str) -> Dict[str, Any]:
    """Coerce one association into the schema and flag verification status."""
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


def mine_paper(pdf_path: Path, client_cfg: Dict[str, str], max_chars: int) -> Dict[str, Any]:
    text = extract_text(pdf_path)
    if len(text) < 2000:
        raise ValueError(f"extracted text too short ({len(text)} chars) - scanned PDF?")

    pmid = pmid_from_filename(pdf_path.name)

    def _prompt(chars: int) -> str:
        return (
            f"Paper file: {pdf_path.name}\n"
            f"PMID: {pmid or 'unknown'}\n\n"
            "=== PAPER TEXT (truncated) ===\n" + text[:chars]
        )

    # The reasoning model can exceed the socket timeout on long papers;
    # retry once with a shorter prompt before declaring failure.
    try:
        raw = chat_json(client_cfg, _prompt(max_chars))
    except (TimeoutError, OSError) as e:
        logger.warning("%s: %s - retrying with half the context", pdf_path.name, e)
        raw = chat_json(client_cfg, _prompt(max_chars // 2))

    associations = []
    for a in raw.get("associations") or []:
        if isinstance(a, dict):
            associations.append(validate_association(a, text))

    return {
        "pmid": pmid,
        "source_file": pdf_path.name,
        "title": raw.get("title"),
        "year": raw.get("year"),
        "journal": raw.get("journal"),
        "niche": raw.get("niche"),
        "study_type": raw.get("study_type"),
        "cohort_size": raw.get("cohort_size"),
        "n_associations": len(associations),
        "n_quote_verified": sum(1 for a in associations if a["quote_verified"]),
        "associations": associations,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", required=True, type=Path)
    ap.add_argument("--out-dir", type=Path, default=BACKEND / "knowledge_staging")
    ap.add_argument("--limit", type=int, default=0, help="process at most N PDFs (0 = all)")
    ap.add_argument("--max-chars", type=int, default=90000)
    ap.add_argument("--sleep", type=float, default=1.0, help="seconds between API calls")
    args = ap.parse_args()

    from app.config import settings

    api_key = settings.KIMI_API_KEY
    if not api_key:
        print("KIMI_API_KEY not configured (backend/.env) - aborting.", file=sys.stderr)
        return 2
    client_cfg = {
        "api_key": api_key,
        "base_url": settings.KIMI_BASE_URL.rstrip("/"),
        "model": settings.KIMI_MODEL,
    }
    logger.info("LLM endpoint: %s model=%s", client_cfg["base_url"], client_cfg["model"])

    pdfs = sorted(args.pdf_dir.glob("*.pdf"))
    if args.limit:
        pdfs = pdfs[: args.limit]
    logger.info("%d PDFs to process from %s", len(pdfs), args.pdf_dir)

    papers_dir = args.out_dir / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)
    failed: List[Dict[str, str]] = []
    n_ok = 0

    assoc_path = args.out_dir / "associations.jsonl"
    with assoc_path.open("w") as assoc_f:
        for i, pdf in enumerate(pdfs, 1):
            out_path = papers_dir / f"{pdf.stem}.json"
            if out_path.exists():
                logger.info("[%d/%d] skip (already mined): %s", i, len(pdfs), pdf.name)
                n_ok += 1
                continue
            try:
                result = mine_paper(pdf, client_cfg, args.max_chars)
                out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
                for a in result["associations"]:
                    assoc_f.write(json.dumps({
                        "pmid": result["pmid"], "paper": result["title"], **a,
                    }, ensure_ascii=False) + "\n")
                n_ok += 1
                logger.info(
                    "[%d/%d] OK %s: %d associations (%d quote-verified)",
                    i, len(pdfs), pdf.name, result["n_associations"], result["n_quote_verified"],
                )
            except Exception as e:
                failed.append({"file": pdf.name, "reason": str(e)[:300]})
                logger.warning("[%d/%d] FAIL %s: %s", i, len(pdfs), pdf.name, e)
            time.sleep(args.sleep)

    (args.out_dir / "failed.json").write_text(json.dumps(failed, ensure_ascii=False, indent=1) + "\n")
    logger.info("done: %d ok, %d failed -> %s", n_ok, len(failed), args.out_dir)
    return len(failed)


if __name__ == "__main__":
    raise SystemExit(main())
