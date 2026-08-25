#!/usr/bin/env python3
"""Exercise every analysis pipeline against a running server with real data.

The unit tests cover functions in isolation with synthetic input. This harness
covers the thing they cannot: whether an actual upload flows through each
endpoint end to end and comes back describing the right samples.

Usage:
    python scripts/pipeline_smoke.py [--base http://127.0.0.1:8000] [--json out.json]

Exit code is the number of failing pipelines, so it can gate CI.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import urllib.error
import urllib.request

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent


def _find_data_dir() -> Path:
    """Locate the example datasets.

    In a checkout they sit at the repository root; in the container image they
    are copied to /app/examples. Resolving both keeps `python
    scripts/pipeline_smoke.py` working in either place. Override with
    META2B_DATA_DIR.
    """
    candidates = [
        Path(os.environ["META2B_DATA_DIR"]) if os.environ.get("META2B_DATA_DIR") else None,
        REPO / "sample_data",    # source checkout (datasets live here since 2026-08-26)
        REPO,                    # legacy layout: datasets at repo root
        BACKEND / "examples",    # container image
        Path("/app/examples"),
    ]
    for candidate in candidates:
        if candidate and (candidate / "Huang_mBio_metadata.tsv").exists():
            return candidate
    return REPO


DATA_DIR = _find_data_dir()

# Real datasets shipped with the repo.
MICROBIOME = DATA_DIR / "Huang_mBio_microbiome.tsv"  # 261 samples x 44 genera (samples in rows)
METABOLOME = DATA_DIR / "Huang_mBio_metabolome.tsv"  # 261 samples x 1125 metabolites
METADATA = DATA_DIR / "Huang_mBio_metadata.tsv"      # Visit(7)/Plaque(2)/Bleeding/Subject(24)
STRAIN = BACKEND / "examples" / "strain2bscan_output.csv"

N_SAMPLES = 261
GROUP = "Visit"
SITE = "Plaque"


class Result:
    def __init__(self, name: str, status: Optional[int], ok: bool, note: str):
        self.name, self.status, self.ok, self.note = name, status, ok, note


def _request(method: str, url: str, body: Any = None, files: Dict[str, Path] = None,
             form: Dict[str, str] = None, timeout: int = 900):
    """Minimal HTTP client (stdlib only, so the harness has no extra deps)."""
    if files:
        boundary = "----meta2bsmoke"
        parts: List[bytes] = []
        for key, value in (form or {}).items():
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode()
            )
        for key, path in files.items():
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"; "
                f"filename=\"{path.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
            )
            parts.append(path.read_bytes())
            parts.append(b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        data = b"".join(parts)
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    elif body is not None:
        data = json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
    else:
        data, headers = None, {}

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, raw[:400].decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw[:400].decode("utf-8", "replace")
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _samples_in(payload: Any) -> Optional[int]:
    """Best-effort count of how many samples a result describes."""
    if not isinstance(payload, dict):
        return None
    rd = payload.get("result_data") or payload
    if not isinstance(rd, dict):
        return None
    for key in ("sample_diversity", "coordinates", "distance_matrix"):
        if isinstance(rd.get(key), dict):
            return len(rd[key])
    if isinstance(rd.get("n_samples"), int):
        return rd["n_samples"]
    stats = rd.get("statistics")
    if isinstance(stats, dict) and isinstance(stats.get("n_samples"), int):
        return stats["n_samples"]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--json", default=None, help="write full results here")
    ap.add_argument("--keep", action="store_true", help="do not delete the session afterwards")
    args = ap.parse_args()
    api = args.base.rstrip("/") + "/api/v1"

    results: List[Result] = []

    def check(name: str, status: Optional[int], payload: Any, *,
              expect: tuple = (200, 201), expect_samples: Optional[int] = None) -> Any:
        ok = status in expect
        note = ""
        if not ok:
            detail = payload.get("detail") if isinstance(payload, dict) else payload
            note = f"HTTP {status}: {str(detail)[:160]}"
        elif expect_samples is not None:
            got = _samples_in(payload)
            if got is not None and got != expect_samples:
                ok, note = False, f"describes {got} samples, expected {expect_samples}"
            elif got is None:
                note = "sample count not reported"
        results.append(Result(name, status, ok, note))
        print(f"  {'PASS' if ok else 'FAIL'}  {name:38s} {status}  {note}")
        return payload

    print(f"== Meta2bAnalyst pipeline smoke test against {args.base} ==\n")
    status, health = _request("GET", args.base.rstrip('/') + "/health")
    if status != 200:
        print(f"server not reachable at {args.base} ({status}: {health})")
        return 1

    # ── Session + upload ────────────────────────────────────────────────
    print("-- session & upload")
    _, sess = _request("POST", f"{api}/sessions", {"name": "pipeline-smoke"})
    sid = sess["id"]
    print(f"  session {sid}")

    for ftype, path in (("metadata", METADATA), ("feature_table", MICROBIOME),
                        ("metabolome", METABOLOME)):
        if not path.exists():
            results.append(Result(f"upload:{ftype}", None, False, f"missing {path}"))
            print(f"  FAIL  upload:{ftype:31s} -   missing {path}")
            continue
        st, payload = _request("POST", f"{api}/sessions/{sid}/upload",
                               files={"file": path}, form={"file_type": ftype})
        note = ""
        ok = st in (200, 201)
        if ok and ftype != "metadata":
            if payload.get("sample_count") != N_SAMPLES:
                ok, note = False, (f"sample_count={payload.get('sample_count')} "
                                   f"feature_count={payload.get('feature_count')}, "
                                   f"expected {N_SAMPLES} samples")
        results.append(Result(f"upload:{ftype}", st, ok, note))
        print(f"  {'PASS' if ok else 'FAIL'}  {'upload:'+ftype:38s} {st}  {note}")

    # ── Data inspection / preprocessing ─────────────────────────────────
    print("\n-- data pipeline")
    check("inspect", *_request("GET", f"{api}/sessions/{sid}/inspect"))
    check("files", *_request("GET", f"{api}/sessions/{sid}/files"))
    check("metadata/columns", *_request("GET", f"{api}/sessions/{sid}/metadata/columns"))
    check("filter", *_request("POST", f"{api}/sessions/{sid}/filter",
                              {"min_prevalence": 0.1, "min_abundance": 0.0001}))
    check("normalize", *_request("POST", f"{api}/sessions/{sid}/normalize", {"method": "tss"}))

    # ── Core microbiome analyses (must all describe 261 samples) ────────
    print("\n-- core analyses")
    core = ["alpha-diversity", "beta-diversity", "pcoa", "nmds", "permanova", "anosim",
            "random-forest", "heatmap", "stacked-bar", "library-size", "rarefaction",
            "taxonomy-bar", "core-microbiome", "hierarchical-clustering", "correlation",
            "network", "advanced-dimred"]
    for ep in core:
        st, payload = _request("POST", f"{api}/sessions/{sid}/analyze/{ep}",
                               {"group_column": GROUP, "parameters": {}})
        # Only ordination/diversity endpoints are expected to report per-sample counts.
        want = N_SAMPLES if ep in {"alpha-diversity", "beta-diversity", "pcoa", "nmds",
                                   "rarefaction", "taxonomy-bar"} else None
        check(f"analyze/{ep}", st, payload, expect_samples=want)

    # ── Differential abundance (explicit contrast) ──────────────────────
    print("\n-- differential abundance")
    for method in ["wilcoxon", "ttest", "lefse", "deseq2", "edger", "ancombc", "maaslin3"]:
        st, payload = _request("POST", f"{api}/sessions/{sid}/analyze/differential", {
            "group_column": GROUP, "comparisons": ["T4", "T9"], "reference_group": "T4",
            "parameters": {"test_method": method, "allow_approximation": True},
        })
        check(f"differential:{method}", st, payload)

    print("\n-- approximation guard (must refuse without opt-in)")
    st, payload = _request("POST", f"{api}/sessions/{sid}/analyze/differential", {
        "group_column": GROUP, "comparisons": ["T4", "T9"],
        "parameters": {"test_method": "ancombc"}})
    # 400 on a no-R image (honest refusal), 201 on the full-R image where
    # ANCOMBC really runs. Both are correct behaviour; anything else is a bug.
    check("guard:ancombc-refused-or-real", st, payload, expect=(400, 201))
    st, payload = _request("POST", f"{api}/sessions/{sid}/analyze/differential",
                           {"group_column": GROUP, "parameters": {"test_method": "wilcoxon"}})
    check("guard:ambiguous-groups", st, payload, expect=(400,))
    for ep in ("phylogenetic", "functional-prediction"):
        st, payload = _request("POST", f"{api}/sessions/{sid}/analyze/{ep}",
                               {"group_column": GROUP, "parameters": {}})
        check(f"guard:{ep}-unvalidated", st, payload, expect=(400,))

    # ── Compositional / advanced single-omics ───────────────────────────
    print("\n-- advanced single-omics")
    for ep, body in [
        ("aldex2", {"group_column": GROUP, "parameters": {"allow_approximation": True}}),
        ("songbird", {"group_column": GROUP, "parameters": {}}),
        # Abundance-weighted metric: every sample carries every genus here, so a
        # presence/absence metric would make all distances zero.
        ("enterotype", {"parameters": {"n_clusters": 3, "distance_metric": "braycurtis"}}),
        ("wgcna", {"parameters": {"allow_approximation": True}}),
        ("lefse", {"group_column": GROUP, "parameters": {"allow_approximation": True}}),
        ("pathway", {"parameters": {}}),
        ("source-tracking", {"group_column": GROUP, "parameters": {}}),
    ]:
        st, payload = _request("POST", f"{api}/sessions/{sid}/analyze/{ep}", body)
        check(f"analyze/{ep}", st, payload)

    # ── Multi-omics integration ─────────────────────────────────────────
    print("\n-- multi-omics integration")
    for ep, body in [
        ("cross-omics", {"group_column": GROUP, "parameters": {"analysis_type": "procrustes"}}),
        ("metabolomics", {"group_column": GROUP, "parameters": {}}),
        ("sparse-cca", {"parameters": {}}),
        ("rda", {"group_column": GROUP, "parameters": {}}),
        ("o2pls", {"parameters": {}}),
        ("mofa", {"parameters": {"n_factors": 5}}),
        ("diablo", {"group_column": GROUP, "parameters": {"allow_approximation": True}}),
    ]:
        st, payload = _request("POST", f"{api}/sessions/{sid}/analyze/{ep}", body)
        check(f"analyze/{ep}", st, payload)

    # ── Multi-site ──────────────────────────────────────────────────────
    print("\n-- multi-site")
    for ep in ["multisite-pcoa", "multisite-permanova", "multisite-markers",
               "multisite-temporal", "multisite-network-compare"]:
        st, payload = _request("POST", f"{api}/sessions/{sid}/analyze/{ep}",
                               {"site_column": SITE, "group_column": GROUP,
                                "time_column": GROUP, "parameters": {}})
        check(f"analyze/{ep}", st, payload)

    # ── Agent ───────────────────────────────────────────────────────────
    print("\n-- agent")
    check("agent/modules", *_request("GET", f"{api}/agent/modules"))
    check("agent/templates", *_request("GET", f"{api}/agent/templates"))
    st, plan = _request("POST", f"{api}/agent/plan",
                        {"query": "find differential markers comparing visits", "session_id": sid})
    ok_plan = st == 200 and isinstance(plan, dict) and plan.get("n_steps", 0) > 1
    results.append(Result("agent/plan", st, ok_plan,
                          "" if ok_plan else f"n_steps={plan.get('n_steps') if isinstance(plan,dict) else plan}"))
    print(f"  {'PASS' if ok_plan else 'FAIL'}  {'agent/plan':38s} {st}  "
          f"{'' if ok_plan else 'planned no real steps'}")
    # The question field is named research_question; data_summary is derived from session_id.
    check("agent/recommend", *_request("POST", f"{api}/agent/recommend",
                                       {"session_id": sid,
                                        "research_question": "which taxa differ by visit?"}))
    check("agent/analyze", *_request("POST", f"{api}/agent/analyze",
                                     {"query": "marker discovery", "session_id": sid}))
    # The section field is named section_type, matching the response and the engine.
    check("agent/write-paper", *_request("POST", f"{api}/agent/write-paper",
                                         {"section_type": "methods",
                                          "results_summary": {"n_samples": N_SAMPLES}}))

    # ── Export ──────────────────────────────────────────────────────────
    print("\n-- export")
    check("export", *_request("POST", f"{api}/sessions/{sid}/export", {"format": "csv"}))
    check("export/report", *_request("POST", f"{api}/sessions/{sid}/export/report", {"format": "pdf"}))

    # ── Teardown ────────────────────────────────────────────────────────
    if not args.keep:
        _request("DELETE", f"{api}/sessions/{sid}")

    failed = [r for r in results if not r.ok]
    print("\n" + "=" * 72)
    print(f"{len(results) - len(failed)}/{len(results)} pipelines passed")
    if failed:
        print("\nFAILURES:")
        for r in failed:
            print(f"  {r.name:38s} {r.status}  {r.note}")

    if args.json:
        Path(args.json).write_text(json.dumps(
            [{"name": r.name, "status": r.status, "ok": r.ok, "note": r.note} for r in results],
            indent=2))

    return len(failed)


if __name__ == "__main__":
    sys.exit(main())
