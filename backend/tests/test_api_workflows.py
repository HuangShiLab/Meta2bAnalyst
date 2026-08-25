"""Contract tests for workflow template CRUD (/api/v1/workflows)."""
import pytest


VALID_PLAN = {
    "query": "test workflow",
    "steps": [
        {"id": "s1", "module": "data_validator", "params": {}, "depends_on": []},
        {"id": "s2", "module": "microbiome_pcoa", "params": {}, "depends_on": ["s1"]},
    ],
}


class TestWorkflowTemplates:
    def test_save_and_get_roundtrip(self, client):
        resp = client.post(
            "/api/v1/workflows",
            json={"name": "pcoa-demo", "description": "demo", "plan": VALID_PLAN,
                  "layout": [{"id": "s1", "x": 300, "y": 80}]},
        )
        assert resp.status_code == 200
        saved = resp.json()
        assert saved["n_steps"] == 2

        got = client.get(f"/api/v1/workflows/{saved['id']}")
        assert got.status_code == 200
        detail = got.json()
        assert detail["plan"]["steps"][1]["module"] == "microbiome_pcoa"
        assert detail["layout"][0]["x"] == 300

    def test_save_overwrites_by_name(self, client):
        client.post("/api/v1/workflows", json={"name": "dup", "plan": VALID_PLAN})
        bigger = {**VALID_PLAN, "steps": VALID_PLAN["steps"] + [
            {"id": "s3", "module": "permanova", "params": {}, "depends_on": ["s2"]}
        ]}
        client.post("/api/v1/workflows", json={"name": "dup", "plan": bigger})

        rows = client.get("/api/v1/workflows").json()
        dups = [r for r in rows if r["name"] == "dup"]
        assert len(dups) == 1
        assert dups[0]["n_steps"] == 3

    def test_save_rejects_unknown_module(self, client):
        bad = {"steps": [{"id": "s1", "module": "no_such_module_xyz", "depends_on": []}]}
        resp = client.post("/api/v1/workflows", json={"name": "bad", "plan": bad})
        assert resp.status_code == 422
        assert "no_such_module_xyz" in resp.json()["detail"]

    def test_save_rejects_dangling_dependency(self, client):
        bad = {"steps": [{"id": "s1", "module": "permanova", "depends_on": ["ghost"]}]}
        resp = client.post("/api/v1/workflows", json={"name": "dangling", "plan": bad})
        assert resp.status_code == 422
        assert "dangling" in resp.json()["detail"]

    def test_save_rejects_empty_plan(self, client):
        resp = client.post("/api/v1/workflows", json={"name": "empty", "plan": {"steps": []}})
        assert resp.status_code == 422

    def test_delete_and_missing(self, client):
        saved = client.post("/api/v1/workflows", json={"name": "to-delete", "plan": VALID_PLAN}).json()
        assert client.delete(f"/api/v1/workflows/{saved['id']}").status_code == 200
        assert client.get(f"/api/v1/workflows/{saved['id']}").status_code == 404
        assert client.delete(f"/api/v1/workflows/{saved['id']}").status_code == 404
