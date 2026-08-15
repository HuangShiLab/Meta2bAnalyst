import { useEffect, useState } from "react";
import api from "@/utils/api";

export interface MetadataColumn {
  name: string;
  dtype: string;
  is_categorical: boolean;
  n_levels: number;
  /** Distinct values, sorted; empty for continuous columns. */
  values: string[];
  n_missing: number;
}

/** Shown until a session with metadata exists. */
const FALLBACK_COLUMNS: MetadataColumn[] = [];

/**
 * Load the grouping columns actually present in the session's metadata.
 *
 * The analysis pages previously rendered a hardcoded list
 * (["Visit", "Treatment", "Group", "Site", "Timepoint", "Gender", "Age"]),
 * so users could not select their own metadata columns and the defaults only
 * matched one in-house dataset.
 */
export function useMetadataColumns(sessionId: string) {
  const [columns, setColumns] = useState<MetadataColumn[]>(FALLBACK_COLUMNS);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionId) {
      setColumns(FALLBACK_COLUMNS);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    api
      .get<{ columns: MetadataColumn[] }>(`/sessions/${sessionId}/metadata/columns`)
      .then((response) => {
        if (cancelled) return;
        setColumns(response.data.columns ?? []);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setColumns(FALLBACK_COLUMNS);
        setError(
          err instanceof Error
            ? err.message
            : "Could not load metadata columns. Upload a metadata file to enable grouping."
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  /** Columns suitable as a grouping variable (categorical, >=2 levels). */
  const groupingColumns = columns.filter((c) => c.is_categorical && c.n_levels >= 2);

  /** Distinct values of a column, for comparison-group selectors. */
  const levelsOf = (name: string): string[] =>
    columns.find((c) => c.name === name)?.values ?? [];

  return { columns, groupingColumns, levelsOf, loading, error };
}
