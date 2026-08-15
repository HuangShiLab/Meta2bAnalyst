"""P2: section-level writing -- rule draft is the skeleton, LLM polish is optional."""
import pytest

from app.services.agent_engine import PaperWriter


RS = {
    "title": "Oral microbiome shifts in periodontitis",
    "n_samples": 60,
    "data_type": "2bRAD-M",
    "key_findings": ["Shannon diversity decreased in periodontitis (p = 0.01)."],
    "study_design": "case-control",
}


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
        monkeypatch.setattr(lc, "_llm_client", _FakeClient(content) if content is not None else None)
    return _set


class TestSectionWriting:
    def test_default_is_rule_based(self):
        w = PaperWriter()
        s = w.write_section("abstract", RS)
        assert "60" in s.content and "2bRAD-M" in s.content

    def test_use_llm_false_skips_polish(self, fake_llm):
        fake_llm("POLISHED TEXT THAT SHOULD NOT APPEAR")
        w = PaperWriter()
        s = w.write_section("abstract", RS, use_llm=False)
        assert "POLISHED" not in s.content

    def test_llm_polish_replaces_draft(self, fake_llm):
        polished = ("We profiled the oral microbiome of 60 participants using "
                    "2bRAD-M sequencing and found Shannon diversity decreased "
                    "in periodontitis (p = 0.01). " * 3)
        fake_llm(polished)
        w = PaperWriter()
        s = w.write_section("abstract", RS, use_llm=True)
        assert s.content == polished.strip()
        assert s.word_count == len(polished.split())

    def test_llm_failure_keeps_rule_draft(self, fake_llm):
        fake_llm(None)  # client returns nothing
        w = PaperWriter()
        s = w.write_section("abstract", RS, use_llm=True)
        assert "60" in s.content

    def test_llm_suspiciously_short_output_rejected(self, fake_llm):
        fake_llm("too short")
        w = PaperWriter()
        s = w.write_section("abstract", RS, use_llm=True)
        assert "60" in s.content, "truncated LLM output must not replace the draft"

    def test_methods_placeholders_survive_prompt(self, fake_llm):
        """The LLM prompt must include the draft so placeholders can be preserved."""
        seen = {}

        class Recorder(_FakeClient):
            def chat(self, sp, up, max_tokens=6000, timeout=60):
                seen["user_prompt"] = up
                return None

        import app.services.llm_client as lc
        w = PaperWriter()
        draft = w.write_section("methods", RS)
        assert "[" in draft.content  # rule draft emits [PLACEHOLDER]s
        monkeypatch_client = Recorder(None)
        import app.services.llm_client as llm_mod
        from pytest import MonkeyPatch
        mp = MonkeyPatch()
        mp.setattr(llm_mod, "_llm_client", monkeypatch_client)
        try:
            w.write_section("methods", RS, use_llm=True)
        finally:
            mp.undo()
        assert "[SEQUENCING" in seen.get("user_prompt", "") or "[" in seen.get("user_prompt", "")


class TestWritePaperEndpointLLM:
    def test_endpoint_accepts_use_llm(self, client, fake_llm):
        fake_llm(None)  # unavailable -> rule draft, but request must validate
        resp = client.post("/api/v1/agent/write-paper", json={
            "section_type": "abstract",
            "results_summary": RS,
            "use_llm": True,
        })
        assert resp.status_code == 200, resp.text
        assert "60" in resp.json()["content"]

    def test_full_paper_accepts_use_llm(self, client, fake_llm):
        fake_llm(None)
        resp = client.post("/api/v1/agent/write-paper/full", json={
            "results_summary": RS,
            "use_llm": True,
        })
        assert resp.status_code == 200, resp.text
        assert set(resp.json()["sections"]) == {
            "abstract", "introduction", "methods", "results", "discussion", "conclusions"}
