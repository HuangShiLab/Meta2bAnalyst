import { useCallback, useEffect, useRef, useState } from "react";
import type {
  AnalysisJobResponse,
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

export function useSectionAnalysis() {
  const [results, setResults] = useState<Record<string, AnalysisJobResponse>>({});
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const run = useCallback(
    async (key: string, type: AnalysisType, sessionId: string, params: Record<string, unknown>) => {
      setLoading((prev) => ({ ...prev, [key]: true }));
      setErrors((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });

      try {
        // Create a temporary useAnalysis to run the analysis
        // This is a workaround - in practice the caller should use runAnalysis directly
        const response = await api.post<AnalysisJobResponse>(
          `/sessions/${sessionId}/analyze/${type}`,
          params
        );
        setResults((prev) => ({ ...prev, [key]: response.data }));
        return response.data;
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
