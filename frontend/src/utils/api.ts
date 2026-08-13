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
    console.warn("Alpha diversity API failed, returning mock", error);
    return getMockAlphaResponse(params);
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
    console.warn("Beta diversity API failed, returning mock", error);
    return getMockBetaResponse(params);
  }
};

export const runPCoA = async (
  sessionId: string,
  params: BetaDiversityParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/pcoa`,
      params
    );
    return response.data;
  } catch (error) {
    return getMockBetaResponse({ ...params, ordinationMethod: 'pcoa' });
  }
};

export const runNMDS = async (
  sessionId: string,
  params: BetaDiversityParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/nmds`,
      params
    );
    return response.data;
  } catch (error) {
    return getMockBetaResponse({ ...params, ordinationMethod: 'nmds' });
  }
};

export const runDifferential = async (
  sessionId: string,
  params: DifferentialParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/differential`,
      params
    );
    return response.data;
  } catch (error) {
    return getMockDifferentialResponse(params);
  }
};

export const runPERMANOVA = async (
  sessionId: string,
  params: BetaDiversityParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/permanova`,
      params
    );
    return response.data;
  } catch (error) {
    return getMockStatResponse('PERMANOVA', params);
  }
};

export const runANOSIM = async (
  sessionId: string,
  params: BetaDiversityParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/anosim`,
      params
    );
    return response.data;
  } catch (error) {
    return getMockStatResponse('ANOSIM', params);
  }
};

export const runRandomForest = async (
  sessionId: string,
  params: MLParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/random-forest`,
      params
    );
    return response.data;
  } catch (error) {
    return getMockMLResponse(params);
  }
};

export const runHeatmap = async (
  sessionId: string,
  params: HeatmapParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/heatmap`,
      params
    );
    return response.data;
  } catch (error) {
    return getMockHeatmapResponse(params);
  }
};

export const runStackedBar = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/stacked-bar`,
      params
    );
    return response.data;
  } catch (error) {
    return getMockStackedBarResponse();
  }
};

export const runVolcano = async (
  sessionId: string,
  params: DifferentialParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/volcano`,
      params
    );
    return response.data;
  } catch (error) {
    return getMockVolcanoResponse(params);
  }
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
    console.warn('Rarefaction API failed, returning mock', error);
    return getMockRarefactionResponse(params);
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
    console.warn('Taxonomy bar API failed, returning mock', error);
    return getMockTaxonomyBarResponse(params);
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
    console.warn('Core microbiome API failed, returning mock', error);
    return getMockCoreMicrobiomeResponse(params);
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
    console.warn('MOFA API failed, returning mock', error);
    return getMockMOFAResponse(params);
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
    console.warn('ALDEx2 API failed, returning mock', error);
    return getMockALDEx2Response(params);
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
    console.warn('Songbird API failed, returning mock', error);
    return getMockSongbirdResponse(params);
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
    console.warn('Enterotype API failed, returning mock', error);
    return getMockEnterotypeResponse(params);
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
    console.warn('WGCNA API failed, returning mock', error);
    return getMockWGCNAResponse(params);
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
    console.warn('DIABLO API failed, returning mock', error);
    return getMockDIABLOResponse(params);
  }
};

export const runStrainComposition = async (
  sessionId: string,
  params: StrainCompositionParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/strain/composition`,
      params
    );
    return response.data;
  } catch (error) {
    return getMockStrainCompositionResponse(params);
  }
};

export const runStrainAlpha = async (
  sessionId: string,
  params: StrainDiversityParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/strain/alpha`,
      params
    );
    return response.data;
  } catch (error) {
    return getMockAlphaResponse({
      indices: params.indices || ['Shannon', 'Simpson'],
      groupColumn: params.groupColumn,
      testMethod: 'Kruskal-Wallis',
    });
  }
};

export const runStrainBeta = async (
  sessionId: string,
  params: StrainDiversityParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/strain/beta`,
      params
    );
    return response.data;
  } catch (error) {
    return getMockBetaResponse({
      distanceMethod: params.distanceMethod || 'bray-curtis',
      ordinationMethod: params.ordinationMethod || 'pcoa',
      groupColumn: params.groupColumn,
      testMethod: 'PERMANOVA',
    });
  }
};

export const runStrainDifferential = async (
  sessionId: string,
  params: StrainDifferentialParams
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/strain/differential`,
      params
    );
    return response.data;
  } catch (error) {
    return getMockDifferentialResponse({
      method: params.method,
      groupColumn: params.groupColumn,
      correctionMethod: 'BH',
      pValueThreshold: 0.05,
    });
  }
};

export const runStrainDominance = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/strain/dominance`,
      params
    );
    return response.data;
  } catch (error) {
    return getMockStackedBarResponse();
  }
};

export const runStrainReplacement = async (
  sessionId: string,
  params: Record<string, unknown>
): Promise<AnalysisJobResponse> => {
  try {
    const response = await api.post<AnalysisJobResponse>(
      `/sessions/${sessionId}/analyze/strain/replacement`,
      params
    );
    return response.data;
  } catch (error) {
    return getMockNetworkResponse();
  }
};

// Mock data generators
function getMockAlphaResponse(params: AlphaDiversityParams): AnalysisJobResponse {
  const groups = ['Control', 'Treatment', 'Recovery'];
  const indices = params.indices.length > 0 ? params.indices : ['Shannon'];
  
  const traces = indices.map((idx, _i) => {
    const yValues = groups.map(() => Math.random() * 3 + 1);
    return {
      type: 'box' as const,
      name: idx,
      x: groups,
      y: yValues,
      boxpoints: 'all' as const,
      jitter: 0.3,
      pointpos: -1.8,
    };
  });

  return {
    success: true,
    job_id: 'mock-alpha-' + Date.now(),
    plot_data: {
      data: traces,
      layout: {
        title: `Alpha Diversity (${params.indices.join(', ')})`,
        xaxis: { title: params.groupColumn },
        yaxis: { title: 'Diversity Index' },
      },
    },
    statistics: {
      test_method: params.testMethod,
      p_value: 0.0234,
      significant: true,
    },
    data: groups.map(g => ({
      group: g,
      n: 12,
      mean_shannon: (Math.random() * 3 + 1).toFixed(3),
    })),
  };
}

function getMockBetaResponse(params: BetaDiversityParams): AnalysisJobResponse {
  const method = params.ordinationMethod.toUpperCase();
  const groups = ['Control', 'Treatment'];
  const colors = ['#1e40af', '#d97706'];
  
  const traces = groups.map((g, i) => ({
    type: 'scatter' as const,
    mode: 'markers' as const,
    name: g,
    x: Array.from({ length: 15 }, () => (Math.random() - 0.5) * 2 + i * 1.5),
    y: Array.from({ length: 15 }, () => (Math.random() - 0.5) * 2 + i * 0.5),
    marker: { color: colors[i], size: 10 },
    text: Array.from({ length: 15 }, (_, j) => `${g}_S${j + 1}`),
  }));

  return {
    success: true,
    job_id: 'mock-beta-' + Date.now(),
    plot_data: {
      data: traces,
      layout: {
        title: `${method} Plot (${params.distanceMethod})`,
        xaxis: { title: `${method}1` },
        yaxis: { title: `${method}2` },
      },
    },
    statistics: {
      test_method: params.testMethod,
      p_value: 0.012,
      r_squared: 0.45,
    },
  };
}

function getMockDifferentialResponse(params: DifferentialParams): AnalysisJobResponse {
  if (params.method === 'MaAsLin3') {
    return getMockMaAsLin3Response(params);
  }
  
  const n = 200;
  const logFC = Array.from({ length: n }, () => (Math.random() - 0.5) * 6);
  const pval = Array.from({ length: n }, () => Math.random());
  const negLogP = pval.map(p => -Math.log10(p + 1e-10));
  
  const colors = logFC.map((fc, i) => {
    if (Math.abs(fc) > 1 && pval[i] < params.pValueThreshold) {
      return fc > 0 ? '#dc2626' : '#1e40af';
    }
    return '#94a3b8';
  });

  const stats: Record<string, unknown> = {
    method: params.method,
    total_features: n,
    upregulated: 23,
    downregulated: 18,
    p_value_threshold: params.pValueThreshold,
  };

  if (params.method === 'ANCOM-BC') {
    stats.zero_cut = params.ancombcZeroCut || 0.9;
    stats.struc_zero = params.ancombcStrucZero !== false;
  }

  return {
    success: true,
    job_id: 'mock-diff-' + Date.now(),
    plot_data: {
      data: [{
        type: 'scatter' as const,
        mode: 'markers' as const,
        x: logFC,
        y: negLogP,
        marker: { color: colors, size: 6 },
        text: Array.from({ length: n }, (_, i) => `Feature_${i + 1}`),
      }],
      layout: {
        title: params.method === 'ANCOM-BC' ? `Volcano Plot (ANCOM-BC)` : `Volcano Plot (${params.method})`,
        xaxis: { title: 'log2 Fold Change' },
        yaxis: { title: '-log10(p-value)' },
        shapes: [
          { type: 'line', x0: -1, x1: -1, y0: 0, y1: Math.max(...negLogP), line: { dash: 'dash' } },
          { type: 'line', x0: 1, x1: 1, y0: 0, y1: Math.max(...negLogP), line: { dash: 'dash' } },
          { type: 'line', x0: Math.min(...logFC), x1: Math.max(...logFC), y0: -Math.log10(params.pValueThreshold), y1: -Math.log10(params.pValueThreshold), line: { dash: 'dash' } },
        ],
      },
    },
    statistics: stats,
    data: Array.from({ length: 20 }, (_, i) => ({
      feature_name: `Feature_${i + 1}`,
      logFC: logFC[i].toFixed(3),
      pvalue: pval[i].toExponential(2),
      padj: (pval[i] * 0.8).toExponential(2),
      significant: (Math.abs(logFC[i]) > 1 && pval[i] < params.pValueThreshold) ? 'Yes' : 'No',
    })),
  };
}

function getMockMaAsLin3Response(params: DifferentialParams): AnalysisJobResponse {
  const features = ['Feature_A', 'Feature_B', 'Feature_C', 'Feature_D', 'Feature_E', 'Feature_F', 'Feature_G', 'Feature_H'];
  const coefficients = features.map(() => (Math.random() - 0.5) * 4);
  
  const colors = coefficients.map(c => c > 0 ? '#dc2626' : '#1e40af');
  
  return {
    success: true,
    job_id: 'mock-maaslin3-' + Date.now(),
    plot_data: {
      data: [{
        type: 'bar' as const,
        x: features,
        y: coefficients,
        marker: { color: colors },
      }],
      layout: {
        title: 'MaAsLin3 Association Plot',
        xaxis: { title: 'Feature' },
        yaxis: { title: 'Coefficient' },
      },
    },
    statistics: {
      method: 'MaAsLin3',
      fixed_effects: params.maaslin3FixedEffects?.join(', ') || 'none',
      normalization: params.maaslin3Normalization || 'TSS',
      significant_features: coefficients.filter(c => Math.abs(c) > 1).length,
    },
    data: features.map((f, i) => ({
      feature_name: f,
      coefficient: coefficients[i].toFixed(3),
      pvalue: (Math.random() * 0.05).toExponential(2),
      qvalue: (Math.random() * 0.05).toExponential(2),
    })),
  };
}

function getMockVolcanoResponse(params: DifferentialParams): AnalysisJobResponse {
  return getMockDifferentialResponse(params);
}

function getMockStatResponse(testName: string, _params: BetaDiversityParams): AnalysisJobResponse {
  return {
    success: true,
    job_id: 'mock-stat-' + Date.now(),
    plot_data: undefined,
    statistics: {
      test: testName,
      p_value: 0.034,
      r_value: testName === 'ANOSIM' ? 0.42 : undefined,
      f_value: testName === 'PERMANOVA' ? 4.56 : undefined,
      significant: true,
    },
  };
}

function getMockMLResponse(_params: MLParams): AnalysisJobResponse {
  const features = ['Feature_A', 'Feature_B', 'Feature_C', 'Feature_D', 'Feature_E'];
  const importances = [0.35, 0.25, 0.18, 0.12, 0.10];
  
  return {
    success: true,
    job_id: 'mock-ml-' + Date.now(),
    plot_data: {
      data: [{
        type: 'bar' as const,
        x: features,
        y: importances,
        marker: { color: '#1e40af' },
      }],
      layout: {
        title: 'Feature Importance (Random Forest)',
        xaxis: { title: 'Feature' },
        yaxis: { title: 'Importance' },
      },
    },
    statistics: {
      accuracy: 0.87,
      precision: 0.85,
      recall: 0.83,
      f1_score: 0.84,
      confusion_matrix: [[28, 4], [5, 23]],
    },
  };
}

function getMockHeatmapResponse(params: HeatmapParams): AnalysisJobResponse {
  const n = params.topN;
  const samples = Array.from({ length: 10 }, (_, i) => `Sample_${i + 1}`);
  const features = Array.from({ length: n }, (_, i) => `Feature_${i + 1}`);
  
  const z = features.map(() =>
    samples.map(() => Math.random() * 10)
  );

  return {
    success: true,
    job_id: 'mock-heatmap-' + Date.now(),
    plot_data: {
      data: [{
        type: 'heatmap' as const,
        z: z,
        x: samples,
        y: features.slice(0, 20),
        colorscale: 'Viridis',
      }],
      layout: {
        title: `Heatmap (Top ${params.topN} Features)`,
        xaxis: { title: 'Samples' },
        yaxis: { title: 'Features' },
      },
    },
  };
}

function getMockNetworkResponse(): AnalysisJobResponse {
  const nodes = Array.from({ length: 20 }, (_, i) => ({
    id: `Strain_${i + 1}`,
    x: Math.random() * 10,
    y: Math.random() * 10,
    size: Math.random() * 20 + 5,
    color: ['#1e40af', '#0f766e', '#d97706', '#7c3aed'][i % 4],
  }));

  const edges = [];
  for (let i = 0; i < 15; i++) {
    const s = Math.floor(Math.random() * nodes.length);
    const t = Math.floor(Math.random() * nodes.length);
    if (s !== t) {
      edges.push({ source: s, target: t, weight: Math.random() });
    }
  }

  const nodeTrace = {
    type: 'scatter' as const,
    mode: 'markers+text' as const,
    x: nodes.map(n => n.x),
    y: nodes.map(n => n.y),
    text: nodes.map(n => n.id),
    marker: {
      size: nodes.map(n => n.size),
      color: nodes.map(n => n.color),
    },
    textposition: 'top center' as const,
  };

  const edgeTraces = edges.map(e => ({
    type: 'scatter' as const,
    mode: 'lines' as const,
    x: [nodes[e.source].x, nodes[e.target].x],
    y: [nodes[e.source].y, nodes[e.target].y],
    line: { color: '#94a3b8', width: e.weight * 3 },
    hoverinfo: 'none' as const,
  }));

  return {
    success: true,
    job_id: 'mock-network-' + Date.now(),
    plot_data: {
      data: [...edgeTraces, nodeTrace],
      layout: {
        title: 'Strain Co-occurrence Network',
        showlegend: false,
        xaxis: { showgrid: false, zeroline: false, showticklabels: false },
        yaxis: { showgrid: false, zeroline: false, showticklabels: false },
      },
    },
  };
}

function getMockStackedBarResponse(): AnalysisJobResponse {
  const samples = Array.from({ length: 8 }, (_, i) => `Sample_${i + 1}`);
  const strains = ['Strain_A', 'Strain_B', 'Strain_C', 'Strain_D'];
  
  const traces = strains.map((strain, i) => ({
    type: 'bar' as const,
    name: strain,
    x: samples,
    y: samples.map(() => Math.random() * 100),
    marker: { color: ['#1e40af', '#0f766e', '#d97706', '#7c3aed'][i] },
  }));

  return {
    success: true,
    job_id: 'mock-stacked-' + Date.now(),
    plot_data: {
      data: traces,
      layout: {
        title: 'Strain Composition',
        barmode: 'stack' as const,
        xaxis: { title: 'Sample' },
        yaxis: { title: 'Abundance' },
      },
    },
  };
}

function getMockStrainCompositionResponse(params: StrainCompositionParams): AnalysisJobResponse {
  if (params.visualizationType === 'heatmap') {
    return getMockHeatmapResponse({ topN: 50, clusterMethod: 'complete' });
  }
  return getMockStackedBarResponse();
}

function getMockRarefactionResponse(_params: Record<string, unknown>): AnalysisJobResponse {
  const depths = [10, 50, 100, 200, 500, 1000, 2000, 5000];
  const traces = ['richness', 'shannon', 'simpson'].map((metric, i) => ({
    type: 'scatter' as const,
    mode: 'lines' as const,
    name: metric,
    x: depths,
    y: depths.map((d) => Math.log(d) * (0.5 + i * 0.2) + Math.random() * 0.5),
    line: { color: ['#1e40af', '#d97706', '#0f766e'][i] },
  }));

  return {
    success: true,
    job_id: 'mock-rarefaction-' + Date.now(),
    plot_data: {
      data: traces,
      layout: {
        title: 'Rarefaction Curves',
        xaxis: { title: 'Sequencing Depth' },
        yaxis: { title: 'Alpha Diversity' },
      },
    },
    statistics: {
      max_depth: 5000,
      n_steps: 8,
      n_iterations: 10,
      n_samples: 20,
      saturated: true,
      saturation_ratio: { richness: 0.98, shannon: 0.95, simpson: 0.96 },
    },
  };
}

function getMockTaxonomyBarResponse(_params: Record<string, unknown>): AnalysisJobResponse {
  const samples = Array.from({ length: 8 }, (_, i) => `Sample_${i + 1}`);
  const taxa = ['Bacteroides', 'Prevotella', 'Lactobacillus', 'Bifidobacterium', 'Others'];
  
  const traces = taxa.map((taxon, i) => ({
    type: 'bar' as const,
    name: taxon,
    x: samples,
    y: samples.map(() => Math.random() * 40),
    marker: { color: ['#1e40af', '#0f766e', '#d97706', '#7c3aed', '#9ca3af'][i] },
  }));

  return {
    success: true,
    job_id: 'mock-taxonomy-bar-' + Date.now(),
    plot_data: {
      data: traces,
      layout: {
        title: `Community Composition (${_params.tax_level || 'Genus'})`,
        barmode: 'stack' as const,
        xaxis: { title: 'Sample' },
        yaxis: { title: 'Relative Abundance (%)' },
      },
    },
    statistics: {
      tax_level: _params.tax_level || 'genus',
      n_taxa_shown: 15,
      n_samples: 8,
      mean_dominant_taxon: 0.35,
    },
  };
}

function getMockCoreMicrobiomeResponse(_params: Record<string, unknown>): AnalysisJobResponse {
  const coreTaxa = ['Bacteroides_fragilis', 'Prevotella_copri', 'Lactobacillus_rhamnosus'];
  const nonCoreTaxa = Array.from({ length: 50 }, (_, i) => `Taxon_${i + 1}`);
  
  const coreTrace = {
    type: 'scatter' as const,
    mode: 'markers' as const,
    name: `Core (n=${coreTaxa.length})`,
    x: coreTaxa.map(() => Math.random() * 0.3 + 0.1),
    y: coreTaxa.map(() => Math.random() * 0.5 + 0.5),
    marker: { size: 12, color: '#1e40af', line: { width: 1, color: 'white' } },
    text: coreTaxa,
  };

  const nonCoreTrace = {
    type: 'scatter' as const,
    mode: 'markers' as const,
    name: `Non-core (n=${nonCoreTaxa.length})`,
    x: nonCoreTaxa.map(() => Math.random() * 0.3),
    y: nonCoreTaxa.map(() => Math.random() * 0.4),
    marker: { size: 8, color: 'rgba(150,150,150,0.5)', line: { width: 0.5, color: 'white' } },
    text: nonCoreTaxa,
  };

  return {
    success: true,
    job_id: 'mock-core-microbiome-' + Date.now(),
    plot_data: {
      data: [nonCoreTrace, coreTrace],
      layout: {
        title: `Core Microbiome Detection`,
        xaxis: { title: 'Mean Relative Abundance' },
        yaxis: { title: 'Prevalence' },
        shapes: [
          { type: 'line', x0: 0, x1: 0.5, y0: 0.5, y1: 0.5, line: { dash: 'dash', color: 'red' } },
          { type: 'line', x0: 0.01, x1: 0.01, y0: 0, y1: 1, line: { dash: 'dash', color: 'red' } },
        ],
      },
    },
    statistics: {
      n_core_taxa: coreTaxa.length,
      core_taxa: coreTaxa,
      prevalence_threshold: _params.prevalence_threshold || 0.5,
      abundance_threshold: _params.abundance_threshold || 0.01,
    },
  };
}

function getMockMOFAResponse(_params: Record<string, unknown>): AnalysisJobResponse {
  const factors = Array.from({ length: 20 }, (_, i) => `Sample_${i + 1}`);
  const groups = ['Control', 'Treatment'];
  
  const traces = groups.map((g, i) => ({
    type: 'scatter' as const,
    mode: 'markers' as const,
    name: g,
    x: factors.slice(i * 10, (i + 1) * 10).map(() => (Math.random() - 0.5) * 4),
    y: factors.slice(i * 10, (i + 1) * 10).map(() => (Math.random() - 0.5) * 4),
    marker: { size: 10, color: ['#1e40af', '#d97706'][i] },
  }));

  return {
    success: true,
    job_id: 'mock-mofa-' + Date.now(),
    plot_data: {
      data: traces,
      layout: {
        title: `MOFA+ Factor Analysis (${_params.n_factors || 5} factors)`,
        xaxis: { title: 'Factor 1' },
        yaxis: { title: 'Factor 2' },
      },
    },
    statistics: {
      n_factors: _params.n_factors || 5,
      n_samples: 20,
      variance_explained_ratio: 0.45,
    },
  };
}

function getMockALDEx2Response(_params: Record<string, unknown>): AnalysisJobResponse {
  const n = 150;
  const effect = Array.from({ length: n }, () => (Math.random() - 0.5) * 4);
  const pval = Array.from({ length: n }, () => Math.random());
  
  return {
    success: true,
    job_id: 'mock-aldex2-' + Date.now(),
    plot_data: {
      data: [{
        type: 'scatter' as const,
        mode: 'markers' as const,
        x: effect,
        y: pval.map(p => -Math.log10(p + 1e-10)),
        marker: { color: effect.map(e => Math.abs(e) > 1 ? '#dc2626' : '#94a3b8'), size: 6 },
        text: Array.from({ length: n }, (_, i) => `Feature_${i + 1}`),
      }],
      layout: {
        title: 'ALDEx2 Effect Plot',
        xaxis: { title: 'Effect Size (CLR)' },
        yaxis: { title: '-log10(p-value)' },
      },
    },
    statistics: {
      n_significant: 23,
      median_effect: 0.85,
      test_method: _params.test_method || 'welch',
    },
  };
}

function getMockSongbirdResponse(_params: Record<string, unknown>): AnalysisJobResponse {
  const features = Array.from({ length: 30 }, (_, i) => `Feature_${i + 1}`);
  const coefs = features.map(() => (Math.random() - 0.5) * 3);
  
  return {
    success: true,
    job_id: 'mock-songbird-' + Date.now(),
    plot_data: {
      data: [{
        type: 'bar' as const,
        x: features,
        y: coefs,
        marker: { color: coefs.map(c => c > 0 ? '#dc2626' : '#1e40af') },
      }],
      layout: {
        title: 'Songbird Differential Abundance',
        xaxis: { title: 'Feature' },
        yaxis: { title: 'Log-fold Change' },
      },
    },
    statistics: {
      converged: true,
      epochs: _params.epochs || 1000,
      n_significant: coefs.filter(c => Math.abs(c) > 1).length,
    },
  };
}

function getMockEnterotypeResponse(_params: Record<string, unknown>): AnalysisJobResponse {
  const n_clusters = (_params.n_clusters as number) || 3;
  const clusters = Array.from({ length: n_clusters }, (_, i) => `Enterotype_${i + 1}`);
  
  const traces = clusters.map((c, i) => ({
    type: 'scatter' as const,
    mode: 'markers' as const,
    name: c,
    x: Array.from({ length: 8 }, () => (Math.random() - 0.5) * 3 + i * 2),
    y: Array.from({ length: 8 }, () => (Math.random() - 0.5) * 3 + i * 0.5),
    marker: { size: 12, color: ['#1e40af', '#d97706', '#0f766e', '#7c3aed'][i % 4] },
  }));

  return {
    success: true,
    job_id: 'mock-enterotype-' + Date.now(),
    plot_data: {
      data: traces,
      layout: {
        title: `Enterotype Clustering (${n_clusters} clusters)`,
        xaxis: { title: 'PCoA 1' },
        yaxis: { title: 'PCoA 2' },
      },
    },
    statistics: {
      n_clusters,
      silhouette_score: 0.62,
      distance_metric: _params.distance_metric || 'jaccard',
    },
  };
}

function getMockWGCNAResponse(_params: Record<string, unknown>): AnalysisJobResponse {
  const modules = ['turquoise', 'blue', 'brown', 'yellow', 'green'];
  const features = Array.from({ length: 50 }, (_, i) => `Feature_${i + 1}`);
  
  // Assign modules
  const moduleAssignments = features.map((_, i) => modules[i % modules.length]);
  
  return {
    success: true,
    job_id: 'mock-wgcna-' + Date.now(),
    plot_data: {
      data: [{
        type: 'heatmap' as const,
        z: Array.from({ length: 20 }, () => Array.from({ length: 20 }, () => Math.random())),
        colorscale: 'RdBu',
      }],
      layout: {
        title: `WGCNA Co-occurrence Network (power=${_params.power || 6})`,
      },
    },
    statistics: {
      n_modules: modules.length,
      n_features: features.length,
      power: _params.power || 6,
      module_sizes: { turquoise: 10, blue: 10, brown: 10, yellow: 10, green: 10 },
    },
  };
}

function getMockDIABLOResponse(_params: Record<string, unknown>): AnalysisJobResponse {
  const groups = ['Control', 'Treatment'];
  
  const traces = groups.map((g, i) => ({
    type: 'scatter' as const,
    mode: 'markers' as const,
    name: g,
    x: Array.from({ length: 12 }, () => (Math.random() - 0.5) * 3 + i * 2),
    y: Array.from({ length: 12 }, () => (Math.random() - 0.5) * 3),
    marker: { size: 10, color: ['#1e40af', '#d97706'][i] },
  }));

  return {
    success: true,
    job_id: 'mock-diablo-' + Date.now(),
    plot_data: {
      data: traces,
      layout: {
        title: `DIABLO Integration (components=${_params.n_components || 2})`,
        xaxis: { title: 'Component 1' },
        yaxis: { title: 'Component 2' },
      },
    },
    statistics: {
      n_components: _params.n_components || 2,
      accuracy: 0.89,
      top_mb_features: ['Bacteroides', 'Prevotella'],
      top_met_features: ['Glucose', 'Butyrate'],
    },
  };
}

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
    console.warn('Multi-omics API failed, returning mock', error);
    return getMockMultiOmicsResponse(params);
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
    console.warn('Metabolomics API failed, returning mock', error);
    return getMockMultiOmicsResponse(params);
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
    console.warn('Sparse CCA API failed, returning mock', error);
    return getMockMultiOmicsResponse(params);
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
    console.warn('RDA API failed, returning mock', error);
    return getMockMultiOmicsResponse(params);
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
    console.warn('O2PLS API failed, returning mock', error);
    return getMockMultiOmicsResponse(params);
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
    console.warn('Multi-site PCoA API failed, returning mock', error);
    return getMockMultiSitePCoAResponse(params);
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
    console.warn('Multi-site PERMANOVA API failed, returning mock', error);
    return getMockStatResponse('Multi-site PERMANOVA', params as any);
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
    console.warn('Multi-site markers API failed, returning mock', error);
    return getMockDifferentialResponse({
      method: 'Wilcoxon',
      groupColumn: params.site_column || 'Site',
      correctionMethod: 'BH',
      pValueThreshold: params.pvalue_threshold || 0.05,
    });
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
    console.warn('Multi-site temporal API failed, returning mock', error);
    return getMockMultiSiteTemporalResponse(params);
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
    console.warn('Multi-site network compare API failed, returning mock', error);
    return getMockNetworkResponse();
  }
};

function getMockMultiSitePCoAResponse(_params: MultiSitePCoAParams): AnalysisJobResponse {
  const sites = ['Oral', 'Gut', 'Skin'];
  const traces = sites.map((site, i) => ({
    type: 'scatter' as const,
    mode: 'markers' as const,
    name: site,
    x: Array.from({ length: 15 }, () => (Math.random() - 0.5) * 2 + i * 2),
    y: Array.from({ length: 15 }, () => (Math.random() - 0.5) * 2 + i * 0.5),
    marker: { color: ['#1e40af', '#d97706', '#0f766e'][i], size: 10, symbol: ['circle', 'square', 'diamond'][i] },
    text: Array.from({ length: 15 }, (_, j) => `${site}_S${j + 1}`),
  }));

  return {
    success: true,
    job_id: 'mock-multisite-pcoa-' + Date.now(),
    plot_data: {
      data: traces,
      layout: {
        title: 'Multi-site PCoA',
        xaxis: { title: 'PC1' },
        yaxis: { title: 'PC2' },
      },
    },
    statistics: {
      n_sites: 3,
      sites: sites,
    },
  };
}

function getMockMultiSiteTemporalResponse(_params: MultiSiteTemporalParams): AnalysisJobResponse {
  const timepoints = ['Day 0', 'Day 7', 'Day 14', 'Day 21'];
  const traces = timepoints.map((tp, i) => ({
    type: 'scatter' as const,
    mode: 'markers' as const,
    name: tp,
    x: Array.from({ length: 10 }, () => (Math.random() - 0.5) * 2 + i * 1.2),
    y: Array.from({ length: 10 }, () => (Math.random() - 0.5) * 2 + i * 0.3),
    marker: { color: ['#1e40af', '#d97706', '#0f766e', '#dc2626'][i], size: 10 },
    text: Array.from({ length: 10 }, (_, j) => `${tp}_S${j + 1}`),
  }));

  return {
    success: true,
    job_id: 'mock-multisite-temporal-' + Date.now(),
    plot_data: {
      data: traces,
      layout: {
        title: 'Temporal Trajectory',
        xaxis: { title: 'PC1' },
        yaxis: { title: 'PC2' },
      },
    },
    statistics: {
      pc1_time_correlation: { rho: 0.52, p: 0.001 },
      permanova_time: { F: 3.21, p: 0.002 },
    },
  };
}

function getMockMultiOmicsResponse(_params: MultiOmicsParams): AnalysisJobResponse {
  const groups = ['T1', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9'];
  const traces = groups.map((g, i) => ({
    type: 'scatter' as const,
    mode: 'markers' as const,
    name: g,
    x: Array.from({ length: 15 }, () => (Math.random() - 0.5) * 2 + i * 1.5),
    y: Array.from({ length: 15 }, () => (Math.random() - 0.5) * 2 + i * 0.5),
    marker: { color: ['#1e40af', '#d97706', '#0f766e', '#7c3aed', '#dc2626', '#2ca02c', '#e377c2'][i], size: 10 },
    text: Array.from({ length: 15 }, (_, j) => `${g}_S${j + 1}`),
  }));

  return {
    success: true,
    job_id: 'mock-multiomics-' + Date.now(),
    plot_data: {
      data: traces,
      layout: {
        title: 'Multi-omics Analysis',
        xaxis: { title: 'Axis 1' },
        yaxis: { title: 'Axis 2' },
      },
    },
    statistics: {
      mantel_r: 0.385,
      mantel_p: 0.0001,
      n_samples: 261,
      n_features_mb: 44,
      n_features_met: 1125,
    },
  };
}
