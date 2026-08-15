#!/usr/bin/env python3
"""
Re-download papers whose original "PDF" turned out to be an HTML error page.

For each PMID in ``knowledge_staging/redownload_pmids.txt``:

1. Query Europe PMC for an open-access full text (PMCID).
2. If the paper is in the PMC Open Access subset, download the PDF from
   ``https://www.ebi.ac.uk/europepmc/webservices/rest/<PMCID>/fullTextPdf``.
3. Validate the %PDF magic header (the lesson from source_audit.json).
4. Save to ``sample_data/oral_papers_redownloaded/`` using the ORIGINAL
   filename so literature_mine.py can pick it up with the same stem.

Papers without an OA copy are listed in the summary -- those need the
HKU Library subscription route (kimi-webbridge with a logged-in browser).

Usage:
    python scripts/redownload_oa.py [--pmid-file PATH] [--out-dir PATH]
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PMIDS = BACKEND_DIR / "knowledge_staging" / "redownload_pmids.txt"
DEFAULT_OUT = BACKEND_DIR.parent / "sample_data" / "oral_papers_redownloaded"
AUDIT = BACKEND_DIR / "knowledge_staging" / "source_audit.json"

EPMC_SEARCH = ("https://www.ebi.ac.uk/europepmc/webservices/rest/search"
               "?query=EXT_ID:{pmid}%20AND%20OPEN_ACCESS:Y&format=json&resultType=core")
EPMC_PDF = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextPdf"
EPMC_PDF_RENDER = "https://europepmc.org/articles/{pmcid}?pdf=render"


def fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "meta2banalyst-redownload/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def original_filename(pmid: str) -> str:
    """Recover the original staging filename so mining stems stay consistent."""
    if AUDIT.exists():
        audit = json.loads(AUDIT.read_text())
        for entry in audit.get("corrupt", []):
            f = entry.get("file") if isinstance(entry, dict) else entry
            if f and f"PMID{pmid}_" in f:
                return f
    return f"PMID{pmid}.pdf"


def resolve_pmcid(pmid: str) -> str | None:
    data = json.loads(fetch(EPMC_SEARCH.format(pmid=pmid)))
    results = data.get("resultList", {}).get("result", [])
    if not results:
        return None
    r = results[0]
    if r.get("isOpenAccess") == "Y" and r.get("pmcid"):
        return r["pmcid"]
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pmid-file", type=Path, default=DEFAULT_PMIDS)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--sleep", type=float, default=0.4)
    args = ap.parse_args()

    pmids = [l.strip() for l in args.pmid_file.read_text().splitlines() if l.strip()]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    ok, no_oa, failed = [], [], []
    for i, pmid in enumerate(pmids, 1):
        target = args.out_dir / original_filename(pmid)
        if target.exists() and target.read_bytes()[:4] == b"%PDF":
            ok.append(pmid)
            print(f"[{i}/{len(pmids)}] SKIP {pmid} (already downloaded)")
            continue
        try:
            pmcid = resolve_pmcid(pmid)
        except Exception as e:
            failed.append((pmid, f"resolve: {e}"))
            print(f"[{i}/{len(pmids)}] FAIL {pmid}: resolve error {e}")
            time.sleep(args.sleep)
            continue
        if not pmcid:
            no_oa.append(pmid)
            print(f"[{i}/{len(pmids)}] NO-OA {pmid}")
            time.sleep(args.sleep)
            continue
        try:
            try:
                pdf = fetch(EPMC_PDF.format(pmcid=pmcid), timeout=60)
            except Exception:
                # fullTextPdf only serves the OA subset; the web render
                # endpoint covers the rest of open-access PMC.
                pdf = fetch(EPMC_PDF_RENDER.format(pmcid=pmcid), timeout=90)
            if pdf[:4] != b"%PDF":
                raise ValueError("not a PDF (HTML error page?)")
            target.write_bytes(pdf)
            ok.append(pmid)
            print(f"[{i}/{len(pmids)}] OK {pmid} <- {pmcid} ({len(pdf)//1024} KB)")
        except Exception as e:
            failed.append((pmid, f"download: {e}"))
            print(f"[{i}/{len(pmids)}] FAIL {pmid}: {e}")
        time.sleep(args.sleep)

    summary = {
        "total": len(pmids), "ok": ok, "no_open_access": no_oa,
        "failed": [{"pmid": p, "error": e} for p, e in failed],
    }
    (BACKEND_DIR / "knowledge_staging" / "redownload_report.json").write_text(
        json.dumps(summary, indent=1))
    print(f"\nOK: {len(ok)}  NO-OA: {len(no_oa)}  FAILED: {len(failed)}")
    print(f"report: knowledge_staging/redownload_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
