"""Keyword search over the knowledge base, and the /agent/knowledge/search endpoint."""
import pytest

from app.knowledge.loader import KnowledgeBase, search_knowledge


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase()


class TestKnowledgeSearch:
    def test_search_by_function_keyword(self, kb):
        """'butyrate' appears in known_functions/main_products of SCFA producers."""
        results = kb.search("butyrate")
        names = [t["name"] for t in results["taxa"]]
        assert "Faecalibacterium_prausnitzii" in names

    def test_search_by_taxon_name(self, kb):
        results = kb.search("Faecalibacterium")
        assert any(t["name"] == "Faecalibacterium_prausnitzii" for t in results["taxa"])

    def test_search_matches_disease(self, kb):
        results = kb.search("periodontal")
        assert any(d["name"] == "periodontal_disease" for d in results["diseases"])

    def test_search_empty_keyword_returns_empty(self, kb):
        assert kb.search("   ") == {"taxa": [], "diseases": []}

    def test_search_limit_respected(self, kb):
        results = kb.search("a", limit=3)
        assert len(results["taxa"]) <= 3
        assert len(results["diseases"]) <= 3

    def test_module_level_wrapper(self):
        results = search_knowledge("butyrate")
        assert results["taxa"], "module-level search_knowledge should hit the same KB"


class TestTaxonSchemaBackwardCompat:
    """New schema fields (disease_evidence, rank, auto_generated) must have
    sane defaults for hand-curated entries that predate the merge tool."""

    def test_lookup_taxon_has_evidence_fields(self, kb):
        taxon = kb.lookup_taxon("Faecalibacterium_prausnitzii")
        assert taxon is not None
        assert taxon["disease_evidence"] == {}
        assert taxon["auto_generated"] is False
        assert taxon["rank"] is None

    def test_lookup_disease_has_literature_evidence(self, kb):
        disease = kb.lookup_disease("periodontal_disease")
        assert disease is not None
        assert disease["literature_evidence"] == {}


class TestKnowledgeSearchEndpoint:
    def test_endpoint_returns_taxa_and_diseases(self, client):
        resp = client.get("/api/v1/agent/knowledge/search", params={"q": "butyrate"})
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert payload["query"] == "butyrate"
        assert payload["n_taxa"] >= 1
        assert any(t["name"] == "Faecalibacterium_prausnitzii" for t in payload["taxa"])

    def test_endpoint_rejects_empty_query(self, client):
        resp = client.get("/api/v1/agent/knowledge/search", params={"q": "  "})
        assert resp.status_code == 422

    def test_endpoint_missing_query_is_422(self, client):
        resp = client.get("/api/v1/agent/knowledge/search")
        assert resp.status_code == 422

    def test_endpoint_limit_clamped(self, client):
        resp = client.get("/api/v1/agent/knowledge/search",
                          params={"q": "a", "limit": 5000})
        assert resp.status_code == 200
        assert len(resp.json()["taxa"]) <= 100
