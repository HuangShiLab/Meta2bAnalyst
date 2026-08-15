"""
LLM Enhancement Layer for Meta2bAnalyst Agent
==============================================

Integrates external LLM (Kimi API) to enhance interpretation quality
while maintaining structured knowledge base as the ground truth.

Architecture:
- KB-driven interpretation (existing) provides structured facts
- LLM rewrites narrative for clarity, depth, and publication readiness
- LLM is only called when API key is available
- KB results are always included as structured data fields
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ───────────────────────────────────────────────────────────────
# LLM Client
# ───────────────────────────────────────────────────────────────

class KimiLLMClient:
    """Lightweight client for Kimi API (OpenAI-compatible).

    Resolution order for credentials: explicit constructor arg, then the
    KIMI_API_KEY environment variable, then app.config.settings (which reads
    backend/.env). Base URL and model are configurable the same way.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        from app.config import settings

        self.api_key = api_key or os.getenv("KIMI_API_KEY") or settings.KIMI_API_KEY
        self.base_url = (
            base_url or os.getenv("KIMI_BASE_URL") or settings.KIMI_BASE_URL
        ).rstrip("/")
        self.model = model or os.getenv("KIMI_MODEL") or settings.KIMI_MODEL
        # None = omit temperature from the payload (required by reasoning
        # models such as kimi-for-coding, which only accept temperature=1).
        temp_env = os.getenv("KIMI_TEMPERATURE")
        self.temperature = float(temp_env) if temp_env else None
        self._available = bool(self.api_key)

    @property
    def available(self) -> bool:
        return self._available

    def enhance_narrative(
        self,
        integrated_narrative: str,
        biological_context: List[str],
        caveats: List[str],
        follow_up: List[str],
        contradictions: List[str],
        disease_relevance: List[Dict[str, Any]],
        question: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Use LLM to rewrite the integrated narrative while preserving all facts.
        Returns enhanced text + reasoning trace.
        """
        if not self.available:
            return {"enhanced_narrative": integrated_narrative, "llm_used": False}

        system_prompt = (
            "You are a senior microbiome bioinformatician and scientific writer. "
            "Your task is to rewrite a draft interpretation of microbiome analysis results "
            "into a clear, professional, publication-ready narrative. "
            "You must preserve ALL factual claims and statistics exactly. "
            "Do not invent new data. Make the writing more engaging and structured. "
            "Respond in the same language as the input (Chinese or English)."
        )

        # Build the user prompt
        sections = []
        sections.append("## DRAFT INTERPRETATION\n" + integrated_narrative)

        if biological_context:
            sections.append("## BIOLOGICAL CONTEXT (from knowledge base)\n" + "\n".join(f"- {c}" for c in biological_context[:5]))
        if caveats:
            sections.append("## METHOD CAVEATS\n" + "\n".join(f"- {c}" for c in caveats[:5]))
        if follow_up:
            sections.append("## FOLLOW-UP SUGGESTIONS\n" + "\n".join(f"- {s}" for s in follow_up[:5]))
        if contradictions:
            sections.append("## DETECTED CONTRADICTIONS\n" + "\n".join(f"- {c}" for c in contradictions[:3]))
        if disease_relevance:
            sections.append("## DISEASE RELEVANCE\n" + "\n".join(
                f"- {d['disease']}: {d['description'][:100]}..." for d in disease_relevance[:3]
            ))

        if question:
            sections.append(f"## USER QUESTION\n{question}")
            sections.append(
                "Please rewrite the interpretation to directly address the user's question "
                "while maintaining scientific accuracy. Structure the answer clearly."
            )
        else:
            sections.append(
                "Please rewrite the interpretation into a cohesive, well-structured narrative. "
                "Use markdown formatting (headers, bullet points) for readability."
            )

        user_prompt = "\n\n".join(sections)

        try:
            import urllib.request
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                # kimi-for-coding is a reasoning model: it rejects any
                # temperature other than 1 and its reasoning tokens count
                # against max_tokens, so omit temperature and keep headroom.
                "max_tokens": 6000,
            }
            if self.temperature is not None:
                payload["temperature"] = self.temperature
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(payload).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                response = json.loads(r.read().decode())
                content = response["choices"][0]["message"]["content"]
                return {
                    "enhanced_narrative": content,
                    "llm_used": True,
                    "model": self.model,
                }
        except Exception as e:
            logger.warning(f"LLM enhancement failed: {e}. Falling back to KB-only.")
            return {"enhanced_narrative": integrated_narrative, "llm_used": False, "error": str(e)}


# Singleton client
_llm_client: Optional[KimiLLMClient] = None

def get_llm_client() -> KimiLLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = KimiLLMClient()
    return _llm_client
