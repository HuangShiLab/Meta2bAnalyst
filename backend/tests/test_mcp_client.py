"""Tests for the external MCP client channel (Paper2Agent direction B)."""
import json

import pytest

from app.services import mcp_client


@pytest.fixture(autouse=True)
def clear_cache():
    mcp_client._tools_cache.clear()
    yield
    mcp_client._tools_cache.clear()


def _set_servers(monkeypatch, value):
    from app.config import settings

    monkeypatch.setattr(settings, "EXTERNAL_MCP_SERVERS", value)


def test_no_servers_by_default(monkeypatch):
    _set_servers(monkeypatch, "")
    assert mcp_client.get_external_servers() == []
    assert mcp_client.provider_for("functional_prediction") is None


def test_parse_servers(monkeypatch):
    _set_servers(monkeypatch, json.dumps([
        {"name": "picrust2", "url": "https://x.example/mcp/",
         "provides": ["functional_prediction"], "tool": "predict_metagenome"},
        {"name": "broken"},  # no url -> dropped
    ]))
    servers = mcp_client.get_external_servers()
    assert len(servers) == 1
    assert mcp_client.provider_for("functional_prediction")["name"] == "picrust2"
    assert mcp_client.provider_for("pcoa") is None


def test_invalid_json_disables_channel(monkeypatch):
    _set_servers(monkeypatch, "{not json")
    assert mcp_client.get_external_servers() == []


def test_call_capability_requires_provider(monkeypatch):
    _set_servers(monkeypatch, "")
    with pytest.raises(RuntimeError, match="No external MCP server"):
        mcp_client.call_capability("functional_prediction", {})


def test_call_capability_tags_engine(monkeypatch):
    _set_servers(monkeypatch, json.dumps([
        {"name": "picrust2", "url": "https://x.example/mcp/",
         "provides": ["functional_prediction"], "tool": "predict_metagenome"},
    ]))

    async def fake_call(url, tool, args, timeout):
        assert url == "https://x.example/mcp/"
        assert tool == "predict_metagenome"
        return {"ko_table": {"K00001": 3}}

    monkeypatch.setattr(mcp_client, "call_remote_tool", fake_call)
    result = mcp_client.call_capability("functional_prediction", {"abundance_table": {}})
    assert result["ko_table"] == {"K00001": 3}
    assert result["engine"] == "external-mcp::picrust2"
