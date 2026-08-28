import { useCallback, useEffect, useRef, useState } from "react";
import { NO_SESSION_MESSAGE } from "@/hooks/useRequiredSession";
import type {
  AnalysisJobResponse,
  PlotlyFigure,
  AlphaDiversityParams,
  BetaDiversityParams,
  DifferentialParams,
  HeatmapParams,
  NetworkParams,
  MLParams,
  StrainCompositionParams,
  StrainDiversityParams,
  StrainDifferentialParams,
  StrainNetworkParams,
  MultiOmicsParams,
} from "@/types";
import {
  runAlphaDiversity,
  runBetaDiversity,
  runPCoA,
  runNMDS,
  runDifferential,
  runPERMANOVA,
  runANOSIM,
  runRandomForest,
  runHeatmap,
  runStackedBar,
  runVolcano,
  runRarefaction,
  runTaxonomyBar,
  runCoreMicrobiome,
  runMOFA,
  runALDEx2,
  runSongbird,
  runEnterotype,
  runWGCNA,
  runDIABLO,
  runStrainComposition,
  runStrainAlpha,
  runStrainBeta,
  runStrainDifferential,
  runStrainDominance,
  runStrainReplacement,
  runMultiOmicsAnalysis,
  runMetabolomicsAnalysis,
  runSparseCCA,
  runRDA,
  runO2PLS,
  runMultiSitePCoA,
  runMultiSitePERMANOVA,
  runMultiSiteMarkers,
  runMultiSiteTemporal,
  runMultiSiteNetworkCompare,
} from "@/utils/api";
import api from "@/utils/api";

export type AnalysisType =
  | 'alpha-diversity'
  | 'beta-diversity'
  | 'pcoa'
  | 'nmds'
  | 'differential'
  | 'permanova'
  | 'anosim'
  | 'random-forest'
  | 'heatmap'
  | 'stacked-bar'
  | 'volcano'
  | 'strain-composition'
  | 'strain-alpha'
  | 'strain-beta'
  | 'strain-differential'
  | 'strain-dominance'
  | 'strain-replacement'
  | 'network'
  | 'cross-omics'
  | 'metabolomics'
  | 'sparse-cca'
  | 'rda'
  | 'o2pls'
  | 'multisite-pcoa'
  | 'multisite-permanova'
  | 'multisite-markers'
  | 'multisite-temporal'
  | 'multisite-network-compare'
  | 'rarefaction'
  | 'taxonomy-bar'
  | 'core-microbiome'
  | 'mofa'
  | 'aldex2'
  | 'songbird'
  | 'enterotype'
  | 'wgcna'
  | 'diablo';

interface AnalysisState {
  isLoading: boolean;
  error: string | null;
  result: AnalysisJobResponse | null;
}

const initialState: AnalysisState = {
  isLoading: false,
  error: null,
  result: null,
};

export function useAnalysis() {
  const [state, setState] = useState<AnalysisState>(initialState);
  const [resultsCache, setResultsCache] = useState<Record<string, AnalysisJobResponse>>({});

  const runAnalysis = useCallback(
    async (
      type: AnalysisType,
      sessionId: string,
      params:
        | AlphaDiversityParams
        | BetaDiversityParams
        | DifferentialParams
        | HeatmapParams
        | NetworkParams
        | MLParams
        | StrainCompositionParams
        | StrainDiversityParams
        | StrainDifferentialParams
        | StrainNetworkParams
        | MultiOmicsParams
        | Record<string, unknown>
    ) => {
      // Single choke point: an absent session must fail with an explanation
      // rather than requesting /sessions//analyze/... or a placeholder id.
      if (!sessionId) {
        setState({ isLoading: false, error: NO_SESSION_MESSAGE, result: null });
        throw new Error(NO_SESSION_MESSAGE);
      }

      setState((prev) => ({ ...prev, isLoading: true, error: null }));

      const cacheKey = `${type}-${JSON.stringify(params)}`;
      if (resultsCache[cacheKey]) {
        setState({ isLoading: false, error: null, result: resultsCache[cacheKey] });
        return resultsCache[cacheKey];
      }

      try {
        let response: AnalysisJobResponse;

        switch (type) {
          case 'alpha-diversity':
            response = await runAlphaDiversity(sessionId, params as AlphaDiversityParams);
            break;
          case 'beta-diversity':
            response = await runBetaDiversity(sessionId, params as BetaDiversityParams);
            break;
          case 'pcoa':
            response = await runPCoA(sessionId, params as BetaDiversityParams);
            break;
          case 'nmds':
            response = await runNMDS(sessionId, params as BetaDiversityParams);
            break;
          case 'differential':
            response = await runDifferential(sessionId, params as DifferentialParams);
            break;
          case 'permanova':
            response = await runPERMANOVA(sessionId, params as BetaDiversityParams);
            break;
          case 'anosim':
            response = await runANOSIM(sessionId, params as BetaDiversityParams);
            break;
          case 'random-forest':
            response = await runRandomForest(sessionId, params as MLParams);
            break;
          case 'heatmap':
            response = await runHeatmap(sessionId, params as HeatmapParams);
            break;
          case 'stacked-bar':
            response = await runStackedBar(sessionId, params as Record<string, unknown>);
            break;
          case 'volcano':
            response = await runVolcano(sessionId, params as DifferentialParams);
            break;
          case 'strain-composition':
            response = await runStrainComposition(sessionId, params as StrainCompositionParams);
            break;
          case 'strain-alpha':
            response = await runStrainAlpha(sessionId, params as StrainDiversityParams);
            break;
          case 'strain-beta':
            response = await runStrainBeta(sessionId, params as StrainDiversityParams);
            break;
          case 'strain-differential':
            response = await runStrainDifferential(sessionId, params as StrainDifferentialParams);
            break;
          case 'strain-dominance':
            response = await runStrainDominance(sessionId, params as Record<string, unknown>);
            break;
          case 'strain-replacement':
            response = await runStrainReplacement(sessionId, params as Record<string, unknown>);
            break;
          case 'network':
            response = await runStrainReplacement(sessionId, params as Record<string, unknown>);
            break;
          case 'cross-omics':
            response = await runMultiOmicsAnalysis(sessionId, params as MultiOmicsParams);
            break;
          case 'metabolomics':
            response = await runMetabolomicsAnalysis(sessionId, params as MultiOmicsParams);
            break;
          case 'sparse-cca':
            response = await runSparseCCA(sessionId, params as MultiOmicsParams);
            break;
          case 'rda':
            response = await runRDA(sessionId, params as MultiOmicsParams);
            break;
          case 'o2pls':
            response = await runO2PLS(sessionId, params as MultiOmicsParams);
            break;
          case 'multisite-pcoa':
            response = await runMultiSitePCoA(sessionId, params as Record<string, unknown>);
            break;
          case 'multisite-permanova':
            response = await runMultiSitePERMANOVA(sessionId, params as Record<string, unknown>);
            break;
          case 'multisite-markers':
            response = await runMultiSiteMarkers(sessionId, params as Record<string, unknown>);
            break;
          case 'multisite-temporal':
            response = await runMultiSiteTemporal(sessionId, params as Record<string, unknown>);
            break;
          case 'multisite-network-compare':
            response = await runMultiSiteNetworkCompare(sessionId, params as Record<string, unknown>);
            break;
          case 'rarefaction':
            response = await runRarefaction(sessionId, params as Record<string, unknown>);
            break;
          case 'taxonomy-bar':
            response = await runTaxonomyBar(sessionId, params as Record<string, unknown>);
            break;
          case 'core-microbiome':
            response = await runCoreMicrobiome(sessionId, params as Record<string, unknown>);
            break;
          case 'mofa':
            response = await runMOFA(sessionId, params as Record<string, unknown>);
            break;
          case 'aldex2':
            response = await runALDEx2(sessionId, params as Record<string, unknown>);
            break;
          case 'songbird':
            response = await runSongbird(sessionId, params as Record<string, unknown>);
            break;
          case 'enterotype':
            response = await runEnterotype(sessionId, params as Record<string, unknown>);
            break;
          case 'wgcna':
            response = await runWGCNA(sessionId, params as Record<string, unknown>);
            break;
          case 'diablo':
            response = await runDIABLO(sessionId, params as Record<string, unknown>);
            break;
          default:
            throw new Error(`Unknown analysis type: ${type}`);
        }

        setResultsCache((prev) => ({ ...prev, [cacheKey]: response }));
        setState({ isLoading: false, error: null, result: response });
        return response;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Analysis failed";
        setState({ isLoading: false, error: message, result: null });
        throw err;
      }
    },
    [resultsCache]
  );

  const clearResult = useCallback(() => {
    setState(initialState);
  }, []);

  const clearCache = useCallback(() => {
    setResultsCache({});
  }, []);

  return {
    runAnalysis,
    clearResult,
    clearCache,
    isLoading: state.isLoading,
    error: state.error,
    result: state.result,
    resultsCache,
  };
}

// ─────────────────────────────── Section Analysis (multi-section state)

// ─────────────────────────────── Section analysis (MultiOmics & friends)

const JOB_POLL_INTERVAL_MS = 2000;
const JOB_POLL_TIMEOUT_MS = 5 * 60 * 1000;

/** Raw shape returned by POST /analyze/* (AnalysisResponse) and GET /jobs/{id}/result. */
interface RawJobPayload {
  job_id?: number | string;
  status?: string;
  result_data?: Record<string, unknown>;
  plot_data?: unknown;
  message?: string;
  detail?: string;
  [key: string]: unknown;
}

const isPlotlyFigure = (v: unknown): v is PlotlyFigure => {
  if (!v || typeof v !== "object") return false;
  const fig = v as PlotlyFigure;
  return Array.isArray(fig.data) && typeof fig.layout === "object" && fig.layout !== null;
};

/** Depth-limited search for a Plotly-shaped dict ({data, layout}). */
const findFigureDeep = (obj: Record<string, unknown>, depth: number): PlotlyFigure | undefined => {
  for (const v of Object.values(obj)) {
    if (isPlotlyFigure(v)) return v;
    if (depth > 0 && v && typeof v === "object" && !Array.isArray(v)) {
      const found = findFigureDeep(v as Record<string, unknown>, depth - 1);
      if (found) return found;
    }
  }
  return undefined;
};

/**
 * The backend nests every analysis payload under result_data, and the exact
 * layout varies by analysis type (pcoa: result_data.plot_data; cross-omics:
 * result_data.plot_data + result_data.statistics; metabolomics marker:
 * result_data.marker_discovery.volcano_plot; permanova: flat scalars).
 * Normalize all of them into the flat AnalysisJobResponse shape the section
 * cards render.
 */
const normalizeJobPayload = (payload: RawJobPayload): AnalysisJobResponse => {
  const rd = (payload.result_data ?? {}) as Record<string, unknown>;

  let plot: PlotlyFigure | undefined;
  if (isPlotlyFigure(payload.plot_data)) plot = payload.plot_data;
  else if (isPlotlyFigure(rd.plot_data)) plot = rd.plot_data;
  else plot = findFigureDeep(rd, 2);

  let statistics: Record<string, unknown> | undefined;
  if (rd.statistics && typeof rd.statistics === "object" && !Array.isArray(rd.statistics)) {
    statistics = rd.statistics as Record<string, unknown>;
  } else {
    // PERMANOVA-style flat results: surface the scalar fields as the stats card.
    const scalars = Object.fromEntries(
      Object.entries(rd).filter(([, v]) => ["string", "number", "boolean"].includes(typeof v))
    );
    if (Object.keys(scalars).length > 0) statistics = scalars;
  }

  const data = Array.isArray(rd.data)
    ? (rd.data as Record<string, string | number>[])
    : undefined;

  return {
    success: true,
    job_id: String(payload.job_id ?? ""),
    plot_data: plot,
    statistics,
    data,
  };
};

/** Poll a queued (Celery) job until it finishes, then fetch its stored result. */
const waitForJobResult = async (
  sessionId: string,
  jobId: number | string
): Promise<RawJobPayload> => {
  const deadline = Date.now() + JOB_POLL_TIMEOUT_MS;
  for (;;) {
    const statusResp = await api.get(`/sessions/${sessionId}/jobs/${jobId}/status`);
    const jobStatus: string | undefined = statusResp.data?.status;

    if (jobStatus === "success" || jobStatus === "completed") {
      const resultResp = await api.get(`/sessions/${sessionId}/jobs/${jobId}/result`);
      return resultResp.data as RawJobPayload;
    }
    if (jobStatus === "failed") {
      throw new Error(statusResp.data?.message || "Analysis job failed");
    }
    if (Date.now() > deadline) {
      throw new Error("Analysis is taking too long; please check Results page later.");
    }
    await new Promise((resolve) => setTimeout(resolve, JOB_POLL_INTERVAL_MS));
  }
};

export function useSectionAnalysis() {
  const [results, setResults] = useState<Record<string, AnalysisJobResponse>>({});
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const run = useCallback(
    async (key: string, type: AnalysisType, sessionId: string, params: Record<string, unknown>) => {
      if (!sessionId) {
        setErrors((prev) => ({ ...prev, [key]: NO_SESSION_MESSAGE }));
        throw new Error(NO_SESSION_MESSAGE);
      }
      setLoading((prev) => ({ ...prev, [key]: true }));
      setErrors((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });

      try {
        const response = await api.post<RawJobPayload>(
          `/sessions/${sessionId}/analyze/${type}`,
          params
        );
        let payload = response.data;

        // Large datasets are queued to Celery: the POST returns
        // {status: 'pending', job_id} with no result yet. Poll until the
        // worker finishes, then load the stored result.
        if (payload?.status === "pending" || payload?.status === "running") {
          if (payload.job_id === undefined || payload.job_id === null) {
            throw new Error("Analysis was queued but no job id was returned");
          }
          payload = await waitForJobResult(sessionId, payload.job_id);
        }

        const normalized = normalizeJobPayload(payload);
        setResults((prev) => ({ ...prev, [key]: normalized }));
        return normalized;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Analysis failed";
        setErrors((prev) => ({ ...prev, [key]: message }));
        throw err;
      } finally {
        setLoading((prev) => ({ ...prev, [key]: false }));
      }
    },
    []
  );

  const clear = useCallback((key: string) => {
    setResults((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
    setErrors((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }, []);

  return { results, loading, errors, run, clear };
}

export function useAnalysisHistory() {
  const [history, setHistory] = useState<{
    id: string;
    type: string;
    label: string;
    timestamp: string;
    status: 'running' | 'success' | 'error';
    result?: AnalysisJobResponse;
  }[]>([]);

  const addHistoryItem = useCallback(
    (item: {
      id: string;
      type: string;
      label: string;
      timestamp: string;
      status: 'running' | 'success' | 'error';
      result?: AnalysisJobResponse;
    }) => {
      setHistory((prev) => [item, ...prev]);
    },
    []
  );

  const updateHistoryItem = useCallback(
    (id: string, updates: Partial<{ status: 'running' | 'success' | 'error'; result?: AnalysisJobResponse }>) => {
      setHistory((prev) =>
        prev.map((item) => (item.id === id ? { ...item, ...updates } : item))
      );
    },
    []
  );

  const removeHistoryItem = useCallback((id: string) => {
    setHistory((prev) => prev.filter((item) => item.id !== id));
  }, []);

  return { history, addHistoryItem, updateHistoryItem, removeHistoryItem };
}

// ─────────────────────────────── Async Job Polling

export interface JobStatus {
  job_id: number;
  status: 'pending' | 'running' | 'success' | 'failed';
  progress: number;
  message: string;
  celery_task_id?: string;
}

export interface PagedResult<T> {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  data: T[];
}

export function useAnalysisPolling(sessionId: string, jobId: number | null, isStrain: boolean = false) {
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [progress, setProgress] = useState(0);
  const [isPolling, setIsPolling] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const startPolling = useCallback(() => {
    if (!jobId || !sessionId) return;
    setIsPolling(true);
  }, [jobId, sessionId]);

  const stopPolling = useCallback(() => {
    setIsPolling(false);
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!isPolling || !jobId || !sessionId) return;

    const poll = async () => {
      try {
        const endpoint = isStrain
          ? `/sessions/${sessionId}/strain-jobs/${jobId}/status`
          : `/sessions/${sessionId}/jobs/${jobId}/status`;
        const response = await api.get(endpoint);
        const data = response.data as JobStatus;
        setStatus(data);
        setProgress(data.progress || 0);

        // Stop polling if complete or failed
        if (data.status === 'success' || data.status === 'failed') {
          stopPolling();
        }
      } catch (err) {
        console.warn('Polling failed:', err);
      }
    };

    // Poll immediately, then every 2 seconds
    poll();
    intervalRef.current = setInterval(poll, 2000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [isPolling, jobId, sessionId, isStrain, stopPolling]);

  const getResult = useCallback(
    async <T = unknown>(): Promise<{ result_data: T } | null> => {
      if (!jobId || !sessionId) return null;
      try {
        const endpoint = isStrain
          ? `/sessions/${sessionId}/strain-jobs/${jobId}/result`
          : `/sessions/${sessionId}/jobs/${jobId}/result`;
        const response = await api.get(endpoint);
        return response.data;
      } catch (err) {
        console.warn('Failed to fetch result:', err);
        return null;
      }
    },
    [jobId, sessionId, isStrain]
  );

  return {
    status,
    progress,
    isPolling,
    startPolling,
    stopPolling,
    getResult,
  };
}

export function usePagedResults<T = Record<string, string | number>>(
  sessionId: string,
  jobId: number | null,
  initialPageSize: number = 100
) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(initialPageSize);
  const [totalPages, setTotalPages] = useState(1);
  const [data, setData] = useState<T[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [sortBy, setSortBy] = useState('padj');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

  const fetchPage = useCallback(
    async (targetPage: number = page, targetPageSize: number = pageSize) => {
      if (!jobId || !sessionId) return;
      setIsLoading(true);
      try {
        const response = await api.get(
          `/sessions/${sessionId}/jobs/${jobId}/result`,
          {
            params: {
              page: targetPage,
              page_size: targetPageSize,
              sort_by: sortBy,
              sort_order: sortOrder,
            },
          }
        );
        const result = response.data;
        if (result.result_data?.paged_results) {
          const paged = result.result_data.paged_results as PagedResult<T>;
          setData(paged.data);
          setPage(paged.page);
          setTotalPages(paged.total_pages);
        } else if (result.result_data?.data) {
          setData(result.result_data.data as T[]);
          setTotalPages(1);
        }
      } catch (err) {
        console.warn('Failed to fetch paged results:', err);
      } finally {
        setIsLoading(false);
      }
    },
    [sessionId, jobId, page, pageSize, sortBy, sortOrder]
  );

  useEffect(() => {
    fetchPage();
    // Intentionally not keyed on fetchPage: its identity changes with
    // page/pageSize, and goToPage already fetches explicitly — keying on it
    // would double-fetch on every page turn.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, sortBy, sortOrder]);

  const goToPage = useCallback(
    (targetPage: number) => {
      if (targetPage < 1 || targetPage > totalPages) return;
      setPage(targetPage);
      fetchPage(targetPage, pageSize);
    },
    [fetchPage, totalPages, pageSize]
  );

  const changePageSize = useCallback(
    (newSize: number) => {
      setPageSize(newSize);
      setPage(1);
      fetchPage(1, newSize);
    },
    [fetchPage]
  );

  const toggleSort = useCallback(
    (column: string) => {
      if (sortBy === column) {
        setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'));
      } else {
        setSortBy(column);
        setSortOrder('asc');
      }
    },
    [sortBy]
  );

  return {
    page,
    pageSize,
    totalPages,
    data,
    isLoading,
    sortBy,
    sortOrder,
    goToPage,
    changePageSize,
    toggleSort,
    refresh: () => fetchPage(page, pageSize),
  };
}
