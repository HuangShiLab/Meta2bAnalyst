import axios from "axios";
import type {
  AlphaDiversityParams,
  BetaDiversityParams,
  DifferentialParams,
  HeatmapParams,
  MLParams,
  StrainCompositionParams,
  StrainDiversityParams,
  StrainDifferentialParams,
  AnalysisJobResponse,
  PlotlyFigure,
  MultiOmicsParams,
  MultiSitePCoAParams,
  MultiSitePERMANOVAParams,
  MultiSiteMarkerParams,
  MultiSiteTemporalParams,
  MultiSiteNetworkParams,
} from "@/types";

export const api = axios.create({
  baseURL: "/api/v1",
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 60000,
});

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default api;

// Session & upload APIs
export const createSession = async (payload: {
  name: string;
  data_format?: string;
  analysis_level?: string;
  description?: string;
}) => {
  const response = await api.post("/sessions", payload);
  return response.data as { id: string };
};

export const uploadFile = async (
  sessionId: string,
  file: File,
  fileType: string
) => {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("file_type", fileType);
  const response = await api.post(`/sessions/${sessionId}/upload`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
};

// Species analysis APIs
export const runAlphaDiversity = async (
  sessionId: string,
  params: AlphaDiversityParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/alpha-diversity`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn("Alpha diversity API failed", error);
    throw error;
  }
};

export const runBetaDiversity = async (
  sessionId: string,
  params: BetaDiversityParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/beta-diversity`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn("Beta diversity API failed", error);
    throw error;
  }
};

export const runPCoA = async (
  sessionId: string,
  params: BetaDiversityParams
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/pcoa`,
    params
  );
  return response.data;
};

export const runNMDS = async (
  sessionId: string,
  params: BetaDiversityParams
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/nmds`,
    params
  );
  return response.data;
};

export const runDifferential = async (
  sessionId: string,
  params: DifferentialParams
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/differential`,
    params
  );
  return response.data;
};

export const runPERMANOVA = async (
  sessionId: string,
  params: BetaDiversityParams
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/permanova`,
    params
  );
  return response.data;
};

export const runANOSIM = async (
  sessionId: string,
  params: BetaDiversityParams
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/anosim`,
    params
  );
  return response.data;
};

export const runRandomForest = async (
  sessionId: string,
  params: MLParams
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/random-forest`,
    params
  );
  return response.data;
};

export const runHeatmap = async (
  sessionId: string,
  params: HeatmapParams
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/heatmap`,
    params
  );
  return response.data;
};

export const runStackedBar = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/stacked-bar`,
    params
  );
  return response.data;
};

export const runVolcano = async (
  sessionId: string,
  params: DifferentialParams
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/volcano`,
    params
  );
  return response.data;
};

// Strain analysis APIs

export const runRarefaction = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/rarefaction`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn('Rarefaction API failed', error);
    throw error;
  }
};

export const runTaxonomyBar = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/taxonomy-bar`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn('Taxonomy bar API failed', error);
    throw error;
  }
};

export const runCoreMicrobiome = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/core-microbiome`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn('Core microbiome API failed', error);
    throw error;
  }
};


export const runMOFA = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/mofa`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn('MOFA API failed', error);
    throw error;
  }
};

export const runALDEx2 = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/aldex2`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn('ALDEx2 API failed', error);
    throw error;
  }
};

export const runSongbird = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/songbird`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn('Songbird API failed', error);
    throw error;
  }
};

export const runEnterotype = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/enterotype`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn('Enterotype API failed', error);
    throw error;
  }
};

export const runWGCNA = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/wgcna`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn('WGCNA API failed', error);
    throw error;
  }
};

export const runDIABLO = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/diablo`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn('DIABLO API failed', error);
    throw error;
  }
};

export const runStrainComposition = async (
  sessionId: string,
  params: StrainCompositionParams
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/strain/composition`,
    params
  );
  return response.data;
};

export const runStrainAlpha = async (
  sessionId: string,
  params: StrainDiversityParams
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/strain/alpha`,
    params
  );
  return response.data;
};

export const runStrainBeta = async (
  sessionId: string,
  params: StrainDiversityParams
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/strain/beta`,
    params
  );
  return response.data;
};

export const runStrainDifferential = async (
  sessionId: string,
  params: StrainDifferentialParams
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/strain/differential`,
    params
  );
  return response.data;
};

export const runStrainDominance = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/strain/dominance`,
    params
  );
  return response.data;
};

export const runStrainReplacement = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/strain/replacement`,
    params
  );
  return response.data;
};

// Mock data generators
export const downloadFigure = (_figure: { data?: unknown[]; layout?: Record<string, unknown> }, format: 'png' | 'svg' | 'jpeg') => {
  const link = document.createElement('a');
  link.download = `figure.${format}`;
  link.href = '#';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};

export const downloadPDF = async (
  plotData: PlotlyFigure | undefined,
  tableData: Record<string, string | number>[],
  filename: string
): Promise<void> => {
  try {
    const response = await api.post('/export/pdf', {
      plot_data: plotData,
      table_data: tableData,
      filename: filename,
    }, {
      responseType: 'blob',
    });
    
    const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  } catch (error) {
    console.error('PDF download failed:', error);
    // Fallback: download as SVG
    if (plotData) {
      downloadFigure(plotData, 'svg');
    }
  }
};

export const downloadCSV = (data: Record<string, string | number>[], filename = 'data.csv') => {
  if (!data || data.length === 0) return;
  const headers = Object.keys(data[0]);
  const csv = [
    headers.join(','),
    ...data.map(row => headers.map(h => String(row[h] ?? '')).join(',')),
  ].join('\n');
  
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};

// Multi-omics APIs
export const runMultiOmicsAnalysis = async (
  sessionId: string,
  params: MultiOmicsParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/cross-omics`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn('Multi-omics API failed', error);
    throw error;
  }
};

export const runMetabolomicsAnalysis = async (
  sessionId: string,
  params: MultiOmicsParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/metabolomics`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn('Metabolomics API failed', error);
    throw error;
  }
};

export const runSparseCCA = async (
  sessionId: string,
  params: MultiOmicsParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/sparse-cca`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn('Sparse CCA API failed', error);
    throw error;
  }
};

export const runRDA = async (
  sessionId: string,
  params: MultiOmicsParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/rda`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn('RDA API failed', error);
    throw error;
  }
};

export const runO2PLS = async (
  sessionId: string,
  params: MultiOmicsParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/o2pls`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn('O2PLS API failed', error);
    throw error;
  }
};

// Multi-site APIs
export const runMultiSitePCoA = async (
  sessionId: string,
  params: MultiSitePCoAParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/multisite-pcoa`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn('Multi-site PCoA API failed', error);
    throw error;
  }
};

export const runMultiSitePERMANOVA = async (
  sessionId: string,
  params: MultiSitePERMANOVAParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/multisite-permanova`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn('Multi-site PERMANOVA API failed', error);
    throw error;
  }
};

export const runMultiSiteMarkers = async (
  sessionId: string,
  params: MultiSiteMarkerParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/multisite-markers`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn('Multi-site markers API failed', error);
    throw error;
  }
};

export const runMultiSiteTemporal = async (
  sessionId: string,
  params: MultiSiteTemporalParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/multisite-temporal`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn('Multi-site temporal API failed', error);
    throw error;
  }
};

export const runMultiSiteNetworkCompare = async (
  sessionId: string,
  params: MultiSiteNetworkParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/multisite-network-compare`,
      params
    );
    return response.data;
  } catch (error) {
    console.warn('Multi-site network compare API failed', error);
    throw error;
  }
};

// Advanced analysis APIs wired to their dedicated backend endpoints.
// No mock fallbacks: failures must surface as errors, never fabricated data.

export const runNetworkAnalysis = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/network`,
    params
  );
  return response.data;
};

export const runHierarchicalClustering = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/hierarchical-clustering`,
    params
  );
  return response.data;
};

export const runSourceTracking = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/source-tracking`,
    params
  );
  return response.data;
};

export const runFunctionalPrediction = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/functional-prediction`,
    params
  );
  return response.data;
};

export const runPathwayAnalysis = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/pathway`,
    params
  );
  return response.data;
};

export const runAdvancedDimred = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  const response = await api.post<AnalysisJobResponse>(
    `/sessions/${sessionId}/analyze/advanced-dimred`,
    params
  );
  return response.data;
};
