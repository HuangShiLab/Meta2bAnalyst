import { useCallback, useState } from "react";

export interface InterpretFullResponse {
  integrated_narrative: string;
  biological_context: string[];
  caveats: string[];
  follow_up_suggestions: string[];
  contradictions: string[];
  disease_relevance: Array<{
    disease: string;
    matched_taxa: string[];
    description: string;
    indicators: string[];
  }>;
}

export interface UseAgentInterpretationReturn {
  result: InterpretFullResponse | null;
  loading: boolean;
  error: string | null;
  interpretFull: (results: Record<string, unknown>, metadataSummary?: Record<string, unknown>) => Promise<InterpretFullResponse | null>;
  clear: () => void;
}

export function useAgentInterpretation(): UseAgentInterpretationReturn {
  const [result, setResult] = useState<InterpretFullResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Returns the fresh interpretation so callers can use it immediately -
  // the `result` state only updates on the next render, and awaiting this
  // promise inside an event handler would otherwise read a stale null.
  const interpretFull = useCallback(async (
    results: Record<string, unknown>,
    metadataSummary?: Record<string, unknown>
  ): Promise<InterpretFullResponse | null> => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/agent/interpret-full", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          results,
          metadata_summary: metadataSummary,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Interpretation failed");
      }
      const data: InterpretFullResponse = await res.json();
      setResult(data);
      return data;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const clear = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  return { result, loading, error, interpretFull, clear };
}
