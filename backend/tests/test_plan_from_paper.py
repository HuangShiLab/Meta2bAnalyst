"""P2: plan-from-paper -- LLM maps a paper's methods onto platform modules."""
import io
import json

import pytest

import app.services.paper_to_plan as p2p


FAKE_LLM_JSON = json.dumps({
    "analyses_found": ["PERMANOVA on Bray-Curtis", "LEfSe-like marker analysis",
                       "PCoA ordination"],
    "unmatched_analyses": ["WGCNA co-expression (custom R script)"],
    "steps": [
        {"id": "step1_validate", "module": "data_validator"},
        {"id": "step2_pcoa", "module": "microbiome_pcoa",
         "params": {"distance": "braycurtis"}, "depends_on": ["step1_validate"]},
        {"id": "step3_permanova", "module": "permanova",
         "params": {"distance": "braycurtis"}, "depends_on": ["step2_pcoa"]},
        {"id": "step4_marker", "module": "microbiome_marker",
         "params": {"transformation": "clr", "test_method": "mannwhitney"},
         "depends_on": ["step1_validate"]},
        {"id": "step5_magic", "module": "definitely_not_a_module"},
    ],
})


class _FakeClient:
    available = True
    model = "kimi-for-coding"

    def __init__(self, content):
        self._content = content

    def chat(self, system_prompt, user_prompt, max_tokens=6000, timeout=60):
        return self._content


@pytest.fixture
def fake_llm(monkeypatch):
    def _set(content):
        import app.services.llm_client as lc
        monkeypatch.setattr(lc, "_llm_client", _FakeClient(content))
    return _set


PAPER_TEXT = ("We collected saliva samples from 60 participants. " * 5 +
              "Beta diversity was assessed by PCoA on Bray-Curtis distances "
              "and group differences tested with PERMANOVA (999 permutations). "
              "Differential taxa were identified per standard marker analysis. " * 3)


class TestPlanFromText:
    def test_maps_paper_methods_to_valid_plan(self, fake_llm):
        fake_llm(FAKE_LLM_JSON)
        out = p2p.plan_from_text(PAPER_TEXT)
        plan = out["plan"]
        modules = [s.module for s in plan.steps]
        assert modules == ["data_validator", "microbiome_pcoa", "permanova",
                           "microbiome_marker"]
        assert "definitely_not_a_module" not in modules
        assert out["analyses_found"]
        assert out["unmatched_analyses"] == ["WGCNA co-expression (custom R script)"]

    def test_rejects_short_text(self, fake_llm):
        fake_llm(FAKE_LLM_JSON)
        with pytest.raises(ValueError, match="too short"):
            p2p.plan_from_text("too short")

    def test_raises_when_llm_unavailable(self, monkeypatch):
        import app.services.llm_client as lc
        monkeypatch.setattr(lc, "_llm_client", _FakeClient(None))
        monkeypatch.setattr(_FakeClient, "available", False)
        with pytest.raises(ValueError, match="not configured"):
            p2p.plan_from_text(PAPER_TEXT)

    def test_raises_when_no_valid_steps(self, fake_llm):
        fake_llm(json.dumps({"steps": [{"module": "nope"}],
                             "analyses_found": [], "unmatched_analyses": []}))
        with pytest.raises(ValueError, match="no valid platform steps"):
            p2p.plan_from_text(PAPER_TEXT)

    def test_code_fence_stripped(self, fake_llm):
        fake_llm("```json\n" + FAKE_LLM_JSON + "\n```")
        out = p2p.plan_from_text(PAPER_TEXT)
        assert len(out["plan"].steps) == 4


class TestPlanFromPaperEndpoint:
    def test_text_submission(self, client, fake_llm):
        fake_llm(FAKE_LLM_JSON)
        resp = client.post("/api/v1/agent/plan-from-paper",
                           data={"paper_text": PAPER_TEXT})
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert payload["plan"]["n_steps"] == 4
        assert payload["confirmed"] is False
        assert payload["explanation"]["n_steps"] == 4
        assert payload["source"]["type"] == "text"

    def test_pdf_submission(self, client, fake_llm, monkeypatch):
        """Build a tiny valid PDF in memory and submit it; patch text
        extraction so the LLM mapping is what is under test."""
        from pypdf import PdfWriter
        buf = io.BytesIO()
        w = PdfWriter()
        w.add_blank_page(width=72, height=72)
        w.write(buf)
        buf.seek(0)
        fake_llm(FAKE_LLM_JSON)
        # The endpoint imports extract_pdf_text at call time from the service
        # module, so patching the module attribute takes effect.
        monkeypatch.setattr(p2p, "extract_pdf_text", lambda raw: PAPER_TEXT)
        resp = client.post(
            "/api/v1/agent/plan-from-paper",
            files={"file": ("paper.pdf", buf, "application/pdf")},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["source"]["filename"] == "paper.pdf"

    def test_rejects_html_masquerading_as_pdf(self, client):
        resp = client.post(
            "/api/v1/agent/plan-from-paper",
            files={"file": ("paper.pdf", io.BytesIO(b"<html>nope</html>"),
                            "application/pdf")},
        )
        assert resp.status_code == 422

    def test_requires_input(self, client):
        resp = client.post("/api/v1/agent/plan-from-paper")
        assert resp.status_code == 422


class TestWindowText:
    """The paper-text windowing policy: opening + Methods, recentred on the
    statistical-analysis subheading for long methods sections."""

    def _paper(self):
        head = "Intro. " * 700                                    # ~4.9k chars
        results = "Some results text. " * 300                     # ~5.7k
        wetlab = "Cohort and sequencing protocol. " * 700         # ~22.4k
        stats = ("Statistical analyses 803\n" +
                 "Alpha diversity with Shannon index; PERMANOVA on Bray-Curtis. " * 200)
        return (head + "\nResults.\n" + results +
                "\nMaterials and Methods 626\n" + "Ethics statement.\n" +
                wetlab + "\n" + stats + "\nReferences\n1. Doe et al.")

    def test_short_text_returned_whole(self):
        assert p2p._window_text("x" * 1000, 24000) == "x" * 1000

    def test_no_methods_heading_takes_head(self):
        full = "y" * 50000
        assert p2p._window_text(full, 24000) == "y" * 24000

    def test_methods_window_recentred_on_stats_section(self):
        # Methods (~35k chars) exceeds its 18k window and the stats
        # subheading sits beyond the window tail, so the window must shift
        # to keep the computational analyses - the part the planner maps
        # to modules.
        out = p2p._window_text(self._paper(), 24000)
        assert "[... METHODS SECTION ...]" in out
        assert "PERMANOVA on Bray-Curtis" in out
        assert len(out) <= 24000 + 100  # budget + separator slack

    def test_stats_heading_inside_references_does_not_trigger_shift(self):
        # A "Statistical analyses" line after the References heading must
        # not pull the window past the methods section.
        paper = ("Intro. " * 700 + "\nMethods\n" + "Wet-lab protocol. " * 400 +
                 "\nReferences\nStatistical analyses in review.\n" + "1. Doe et al. " * 300)
        out = p2p._window_text(paper, 8000)
        assert "Wet-lab protocol" in out
        assert "Doe et al." not in out
