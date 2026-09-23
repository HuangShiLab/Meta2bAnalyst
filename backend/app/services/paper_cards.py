"""Paper knowledge cards (Paper2Agent direction C, paper2skill-flavoured).

For every PMID cited in the taxon / disease knowledge bases, build a
structured "paper card" summarising what the paper contributes to the KB:
which taxa it links to which diseases, in which direction, with which study
types and cohort sizes. Cards are deterministic (built offline from the KB
itself — no network), so they can be regenerated on every startup and can
never drift from the evidence tables.

Cards answer the "what does this paper say / where did this association come
from" questions for the Agent, and are exposed both as REST endpoints and as
MCP tools.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"

_cards_cache: Optional[Dict[str, Dict[str, Any]]] = None


def _collect() -> Dict[str, Dict[str, Any]]:
    """Aggregate evidence rows from both KB files keyed by PMID."""
    papers: Dict[str, Dict[str, Any]] = {}

    def touch(pmid: str) -> Dict[str, Any]:
        return papers.setdefault(
            str(pmid),
            {
                "pmid": str(pmid),
                "years": set(),
                "journals": set(),
                "study_types": set(),
                "associations": [],
            },
        )

    taxon_path = _KNOWLEDGE_DIR / "taxon_db.json"
    if taxon_path.exists():
        taxon_db = json.loads(taxon_path.read_text(encoding="utf-8"))
        for taxon, info in taxon_db.items():
            for disease, rows in (info.get("disease_evidence") or {}).items():
                for row in rows or []:
                    pmid = row.get("pmid")
                    if not pmid:
                        continue
                    card = touch(pmid)
                    if row.get("year"):
                        card["years"].add(str(row["year"]))
                    if row.get("journal"):
                        card["journals"].add(row["journal"])
                    if row.get("study_type"):
                        card["study_types"].add(row["study_type"])
                    card["associations"].append(
                        {
                            "taxon": taxon,
                            "disease": disease,
                            "direction": row.get("direction"),
                            "study_type": row.get("study_type"),
                            "cohort_size": row.get("cohort_size"),
                            "source": "taxon_db",
                        }
                    )

    disease_path = _KNOWLEDGE_DIR / "disease_db.json"
    if disease_path.exists():
        disease_db = json.loads(disease_path.read_text(encoding="utf-8"))
        for disease, info in disease_db.items():
            for taxon, rows in (info.get("literature_evidence") or {}).items():
                for row in rows or []:
                    pmid = row.get("pmid")
                    if not pmid:
                        continue
                    card = touch(pmid)
                    if row.get("year"):
                        card["years"].add(str(row["year"]))
                    if row.get("journal"):
                        card["journals"].add(row["journal"])
                    if row.get("study_type"):
                        card["study_types"].add(row["study_type"])
                    assoc = {
                        "taxon": taxon,
                        "disease": disease,
                        "direction": row.get("direction"),
                        "study_type": row.get("study_type"),
                        "cohort_size": row.get("cohort_size"),
                        "source": "disease_db",
                    }
                    if assoc not in card["associations"]:
                        card["associations"].append(assoc)
    return papers


def _finalise(card: Dict[str, Any]) -> Dict[str, Any]:
    """Convert sets to sorted lists and add a deterministic summary."""
    assocs = card["associations"]
    diseases = sorted({a["disease"] for a in assocs if a.get("disease")})
    enriched = sorted({a["taxon"] for a in assocs if a.get("direction") == "enriched"})
    depleted = sorted({a["taxon"] for a in assocs if a.get("direction") == "depleted"})
    out = {
        "pmid": card["pmid"],
        "years": sorted(card["years"]),
        "journals": sorted(card["journals"]),
        "study_types": sorted(card["study_types"]),
        "diseases": diseases,
        "n_associations": len(assocs),
        "enriched_taxa": enriched,
        "depleted_taxa": depleted,
        "associations": assocs,
    }
    parts = [f"PMID {card['pmid']}"]
    if out["years"]:
        parts.append(f"({', '.join(out['years'])})")
    if out["journals"]:
        parts.append(f"in {', '.join(out['journals'])}")
    parts.append(
        f"contributes {len(assocs)} taxon-disease association(s) across "
        f"{len(diseases)} condition(s): {', '.join(diseases) or 'n/a'}."
    )
    if enriched:
        parts.append(f"Enriched: {', '.join(enriched[:8])}{'…' if len(enriched) > 8 else ''}.")
    if depleted:
        parts.append(f"Depleted: {', '.join(depleted[:8])}{'…' if len(depleted) > 8 else ''}.")
    out["summary"] = " ".join(parts)
    return out


def get_paper_cards(force_rebuild: bool = False) -> Dict[str, Dict[str, Any]]:
    """Return all paper cards keyed by PMID (cached)."""
    global _cards_cache
    if _cards_cache is None or force_rebuild:
        papers = _collect()
        _cards_cache = {pmid: _finalise(card) for pmid, card in papers.items()}
        logger.info(f"Built {len(_cards_cache)} paper knowledge cards from KB evidence.")
    return _cards_cache


def get_paper_card(pmid: str) -> Optional[Dict[str, Any]]:
    return get_paper_cards().get(str(pmid))


def list_paper_cards() -> List[Dict[str, Any]]:
    """Lightweight list (no per-association detail) for browsing."""
    return [
        {k: v for k, v in card.items() if k != "associations"}
        for card in sorted(
            get_paper_cards().values(),
            key=lambda c: (-c["n_associations"], c["pmid"]),
        )
    ]
