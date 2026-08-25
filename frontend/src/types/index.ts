export interface Session {
  id: string;
  currentStep: AnalysisStep;
  dataFormat: DataFormat | null;
  uploadedFiles: UploadFile[];
  analysisParams: AnalysisParams | null;
  analysisResults: AnalysisResult | null;
  createdAt: Date;
  updatedAt: Date;
}

export type AnalysisStep =
  | 'home'
  | 'upload'
  | 'microbiome'
  | 'multi-omics'
  | 'multi-site'
  | 'agent'
  | 'workflow-builder'
  | 'results';

export type DataFormat = 'species' | 'function' | 'strain' | 'multiomics';
export type UploadFormat = '2brad-m' | 'qiime' | 'mothur' | 'tsv' | 'metaphlan' | 'humann3';

export interface FilterParams {
  removeConstantFeatures: boolean;
  removeSingleton: 'none' | 'one-sample' | 'one-total';
  lowCountMinCount: number;
  lowCountMethod: 'prevalence' | 'mean' | 'median';
  lowCountPrevalence: number;
  lowVarianceRemoveRatio: number;
  lowVarianceBasedOn: 'iqr' | 'sd' | 'cv';
}

export interface NormalizationParams {
  rarefaction: 'none' | 'rarefy';
  rarefactionReads: number;
  scaling: 'none' | 'tss' | 'css' | 'uq';
  transformation: 'none' | 'clr' | 'rle' | 'tmm';
}

export interface UploadFile {
  id: string;
  name: string;
  size: number;
  type: string;
  progress: number;
  status: 'pending' | 'uploading' | 'success' | 'error';
  errorMessage?: string;
}

export interface AnalysisParams {
  filterParams?: FilterParams;
  normalizationParams?: NormalizationParams;
  filterThreshold: number;
  normalizationMethod: 'cpm' | 'tmm' | 'rle' | 'none';
  analysisType: 'differential' | 'correlation' | 'pca' | 'clustering';
  groupColumn?: string;
  treatmentGroup?: string;
  controlGroup?: string;
  confounders?: string[];
}

export interface AnalysisResult {
  summary: {
    totalFeatures: number;
    significantFeatures: number;
    pValueThreshold: number;
  };
  tables: {
    differentialAbundance?: DataTable;
    correlationMatrix?: DataTable;
    pcaLoadings?: DataTable;
  };
  figures: {
    volcanoPlot?: PlotlyFigure;
    pcaPlot?: PlotlyFigure;
    heatmap?: PlotlyFigure;
    barPlot?: PlotlyFigure;
  };
  reportUrl?: string;
}

export interface DataTable {
  columns: string[];
  rows: Record<string, string | number>[];
}

export interface PlotlyFigure {
  data: unknown[];
  layout: Record<string, unknown>;
}

export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message?: string;
}

export interface StepConfig {
  id: AnalysisStep;
  label: string;
  description: string;
  icon: string;
}

// Analysis-specific types
export interface AlphaDiversityParams {
  indices: string[];
  groupColumn: string;
  testMethod: string;
}

export interface BetaDiversityParams {
  distanceMethod: string;
  ordinationMethod: string;
  groupColumn: string;
  testMethod: string;
}

export interface DifferentialParams {
  method: string;
  groupColumn: string;
  contrastGroups?: string[];
  correctionMethod: string;
  pValueThreshold: number;
  // ANCOM-BC specific
  ancombcZeroCut?: number;       // 0-1, default 0.9
  ancombcLibCut?: number;        // 0-1000, default 0
  ancombcStrucZero?: boolean;    // default true
  ancombcPAdjMethod?: string;    // 'holm', 'hochberg', 'hommel', 'bonferroni', 'BH', 'BY', 'fdr', 'none'
  // MaAsLin3 specific
  maaslin3FixedEffects?: string[]; // metadata columns as fixed effects
  maaslin3RandomEffects?: string[]; // metadata columns as random effects
  maaslin3Normalization?: string; // 'TSS', 'CSS', 'CLR', 'NONE'
  maaslin3Transform?: string;     // 'LOG', 'AST', 'NONE'
  maaslin3Reference?: string;    // reference level for categorical
  // LEfSe specific
  lefseLdaThreshold?: number;     // 1.0-4.0, default 2.0
}

export interface HeatmapParams {
  topN: number;
  clusterMethod: string;
}

export interface NetworkParams {
  correlationMethod: string;
  threshold: number;
}

export interface MLParams {
  method: string;
  groupColumn: string;
  cvFolds: string;
}

export interface StrainCompositionParams {
  visualizationType: 'stacked' | 'heatmap';
  groupColumn?: string;
}

export interface StrainDiversityParams {
  analysisType: 'alpha' | 'beta';
  indices?: string[];
  distanceMethod?: string;
  ordinationMethod?: string;
  groupColumn: string;
}

export interface StrainDifferentialParams {
  scope: 'within-species' | 'cross-species';
  method: string;
  groupColumn: string;
}

export interface StrainNetworkParams {
  speciesScope: 'current' | 'all';
  correlationMethod: string;
  correlationThreshold: number;
  pValueThreshold: number;
}

export interface AnalysisJobResponse {
  success: boolean;
  job_id: string;
  plot_data?: PlotlyFigure;
  statistics?: Record<string, unknown>;
  data?: Record<string, string | number>[];
}

export interface AnalysisHistoryItem {
  id: string;
  type: string;
  label: string;
  timestamp: string;
  status: 'running' | 'success' | 'error';
  plotData?: PlotlyFigure;
  statistics?: Record<string, unknown>;
  tableData?: Record<string, string | number>[];
  params?: Record<string, unknown>;
}

// Multi-omics specific types
export interface MultiOmicsParams {
  analysis_type: string;
  group_column?: string;
  reference_group?: string;
  n_components?: number;
  sparsity_x?: number;
  sparsity_y?: number;
  n_joint?: number;
  n_ortho_x?: number;
  n_ortho_y?: number;
  pvalue_threshold?: number;
  fc_threshold?: number;
}

// Multi-site specific types
export interface MultiSitePCoAParams {
  site_column?: string;
  subject_column?: string;
  group_column?: string;
  distance_metric?: string;
  ordination_method?: string;
  connect_subjects?: boolean;
}

export interface MultiSitePERMANOVAParams {
  site_column?: string;
  group_column?: string;
  distance_metric?: string;
  permutations?: number;
}

export interface MultiSiteMarkerParams {
  site_column?: string;
  reference_site?: string;
  subject_column?: string;
  pvalue_threshold?: number;
  fc_threshold?: number;
}

export interface MultiSiteTemporalParams {
  time_column?: string;
  subject_column?: string;
  group_column?: string;
  site_column?: string;
  distance_metric?: string;
}

export interface MultiSiteNetworkParams {
  site_column?: string;
  threshold?: number;
}

export interface MultiOmicsUploadRequest {
  microbiome_file_id: string;
  metabolome_file_id: string;
  metadata_file_id?: string;
}
