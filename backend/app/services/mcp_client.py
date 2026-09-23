"""External MCP client — Meta2bAnalyst as an MCP consumer (Paper2Agent
direction B).

Lets the platform call third-party "paper agent" MCP servers (e.g. a hosted
PICRUSt2 functional-prediction server) when a local engine is unavailable.

Configuration (environment):

    EXTERNAL_MCP_SERVERS='[
      {"name": "picrust2",
       "url": "https://example.hf.space/mcp/",
       "provides": ["functional_prediction"],
       "tool": "predict_metagenome"}
    ]'

Each entry:
  name     — human label, used in result provenance (engine field)
  url      — MCP HTTP endpoint
  provides — list of Meta2bAnalyst capabilities this server can fill
  tool     — the remote tool name to call for that capability
  timeout  — optional seconds (default 300)

Results returned through this channel always carry
``engine = "external-mcp::<name>"`` so they can never be mistaken for local
reference implementations.
"""
import asyncio
import json
import logging
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_cache_lock = threading.Lock()
_tools_cache: Dict[str, List[str]] = {}


def get_external_servers() -> List[Dict[str, Any]]:
    """Parse EXTERNAL_MCP_SERVERS (JSON list). Invalid JSON disables the
    channel rather than crashing the app."""
    from app.config import settings

    raw = getattr(settings, "EXTERNAL_MCP_SERVERS", "") or ""
    if not raw.strip():
        return []
    try:
        servers = json.loads(raw)
        return [s for s in servers if isinstance(s, dict) and s.get("url")]
    except Exception as e:
        logger.error(f"EXTERNAL_MCP_SERVERS is not valid JSON: {e}")
        return []


def provider_for(capability: str) -> Optional[Dict[str, Any]]:
    """Return the configured server entry providing `capability`, if any."""
    for server in get_external_servers():
        if capability in (server.get("provides") or []):
            return server
    return None


async def list_remote_tools(url: str, use_cache: bool = True) -> List[str]:
    """List tool names exposed by a remote MCP server (cached per URL)."""
    if use_cache:
        with _cache_lock:
            if url in _tools_cache:
                return _tools_cache[url]
    from fastmcp import Client

    async with Client(url) as client:
        tools = await client.list_tools()
        names = [t.name for t in tools]
    with _cache_lock:
        _tools_cache[url] = names
    return names


async def call_remote_tool(
    url: str,
    tool: str,
    arguments: Dict[str, Any],
    timeout: float = 300.0,
) -> Dict[str, Any]:
    """Call a tool on a remote MCP server and return its JSON payload."""
    from fastmcp import Client

    async with Client(url) as client:
        result = await asyncio.wait_for(
            client.call_tool(tool, arguments), timeout=timeout
        )
    # fastmcp returns content blocks; expect a single JSON text block.
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"text": text}
    if getattr(result, "structured_content", None):
        return result.structured_content
    return {}


def call_capability(capability: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Synchronously invoke the external provider for a capability.

    Raises RuntimeError when no provider is configured or the call fails —
    callers decide whether that is a hard error or a fallback trigger.
    """
    server = provider_for(capability)
    if server is None:
        raise RuntimeError(f"No external MCP server configured for {capability!r}")
    tool = server.get("tool")
    if not tool:
        raise RuntimeError(f"External MCP server {server.get('name')!r} has no 'tool' set")
    timeout = float(server.get("timeout", 300))
    logger.info(f"Calling external MCP {server['name']}::{tool} for {capability}")
    payload = asyncio.run(call_remote_tool(server["url"], tool, arguments, timeout))
    if not isinstance(payload, dict):
        payload = {"result": payload}
    payload["engine"] = f"external-mcp::{server['name']}"
    return payload
