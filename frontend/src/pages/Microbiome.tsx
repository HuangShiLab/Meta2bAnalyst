import { useState, useRef, useCallback, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { PlotlyChart } from "@/components/shared/PlotlyChart";
import { useSessionStore } from "@/stores/sessionStore";
import { useRequiredSession } from "@/hooks/useRequiredSession";
import { useMetadataColumns } from "@/hooks/useMetadataColumns";
import { NoSessionBanner } from "@/components/shared/NoSessionBanner";
import { useAnalysis } from "@/hooks/useAnalysis";
import { downloadFigure, downloadCSV, downloadPDF } from "@/utils/api";
import type { PlotlyFigure, AnalysisJobResponse } from "@/types";
import {
  Dna,
  BarChart3,
  Network,
  CircleDot,
  BrainCircuit,
  FunctionSquare,
  GitBranch,
  Map,
  Play,
  Image as ImageIcon,
  FileSpreadsheet,
  Loader2,
  HelpCircle,
  FileText,
  FlaskConical,
} from "lucide-react";
import { cn } from "@/lib/utils";


function ParameterItem({ label, children, tooltip }: { label: string; children: React.ReactNode; tooltip?: string }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Label className="text-sm font-medium">{label}</Label>
        {tooltip && (
          <div className="relative group">
            <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block w-48 p-2 bg-popover text-xs rounded shadow border z-50">
              {tooltip}
            </div>
          </div>
        )}
      </div>
      {children}
    </div>
  );
}

function ResultSection({
  title,
  plotData,
  tableData,
  stats,
  isLoading,
  onRun,
  runLabel = "Run Analysis",
}: {
  title: string;
  plotData?: PlotlyFigure;
  tableData?: Record<string, string | number>[];
  stats?: Record<string, unknown>;
  isLoading: boolean;
  onRun: () => void;
  runLabel?: string;
}) {
  const resultRef = useRef<HTMLDivElement>(null);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Button onClick={onRun} disabled={isLoading} className="gap-2">
          {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          {isLoading ? "Running..." : runLabel}
        </Button>
        {isLoading && <Progress value={65} className="w-40 h-2" />}
      </div>

      {isLoading && (
        <div className="flex items-center justify-center h-64 rounded-lg border border-border bg-muted/50">
          <div className="flex flex-col items-center gap-2">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-sm text-muted-foreground">Analysis in progress...</p>
          </div>
        </div>
      )}

      <div ref={resultRef} className="space-y-4">
        {plotData && !isLoading && (
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">{title}</CardTitle>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" className="gap-1" onClick={() => downloadFigure(plotData, 'png')}>
                    <ImageIcon className="h-3.5 w-3.5" /> PNG
                  </Button>
                  <Button variant="outline" size="sm" className="gap-1" onClick={() => downloadFigure(plotData, 'svg')}>
                    <ImageIcon className="h-3.5 w-3.5" /> SVG
                  </Button>
                  {tableData && (
                    <Button variant="outline" size="sm" className="gap-1" onClick={() => downloadCSV(tableData, 'data.csv')}>
                      <FileSpreadsheet className="h-3.5 w-3.5" /> CSV
                    </Button>
                  )}
                  <Button variant="outline" size="sm" className="gap-1" onClick={() => downloadPDF(plotData, tableData || [], 'analysis_result.pdf')}>
                    <FileText className="h-3.5 w-3.5" /> PDF
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="h-[400px] w-full">
                <PlotlyChart figure={plotData} className="h-full" />
              </div>
            </CardContent>
          </Card>
        )}

        {stats && !isLoading && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-lg">Statistics</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-4">
                {Object.entries(stats).map(([key, value]) => (
                  <div key={key} className="rounded-lg bg-muted/50 p-3">
                    <p className="text-xs text-muted-foreground uppercase">{key.replace(/_/g, ' ')}</p>
                    <p className="text-lg font-semibold mt-1">
                      {typeof value === 'number' ? value.toFixed(4) : String(value)}
                    </p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {tableData && !isLoading && tableData.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-lg">Data Table</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-auto max-h-64">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      {Object.keys(tableData[0]).map((col) => (
                        <th key={col} className="text-left px-3 py-2 font-medium text-muted-foreground">{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tableData.slice(0, 20).map((row, i) => (
                      <tr key={i} className="border-b last:border-0 hover:bg-muted/50">
                        {Object.values(row).map((val, j) => (
                          <td key={j} className="px-3 py-2 font-mono text-xs">{String(val)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {tableData.length > 20 && (
                  <p className="text-xs text-muted-foreground mt-2 text-center">Showing 20 of {tableData.length} rows</p>
                )}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

export function Microbiome() {
  const sessionStore = useSessionStore();
  const setCurrentStep = useSessionStore((state) => state.setCurrentStep);
  const { runAnalysis, isLoading, result, clearResult } = useAnalysis();

  useEffect(() => {
    setCurrentStep("microbiome");
  }, [setCurrentStep]);

  // ─── Tab 1: Community Structure ───
  const [communitySubTab, setCommunitySubTab] = useState<"alpha" | "beta" | "composition" | "permanova" | "rarefaction" | "taxonomy-bar" | "core-microbiome">("alpha");
  const [alphaIndices, setAlphaIndices] = useState<string[]>(["Shannon", "Simpson", "Pielou"]);
  const [alphaGroup, setAlphaGroup] = useState("Visit");
  const [alphaTest, setAlphaTest] = useState("Kruskal-Wallis");

  const [betaDistance, setBetaDistance] = useState("braycurtis");
  const [betaOrdination, setBetaOrdination] = useState<"PCoA" | "NMDS">("PCoA");
  const [betaGroup, setBetaGroup] = useState("Visit");

  const [compType, setCompType] = useState<"stacked-bar" | "heatmap">("stacked-bar");
  const [compTopN, setCompTopN] = useState(30);
  const [compTaxLevel, setCompTaxLevel] = useState("Genus");
  const [compGroup, setCompGroup] = useState("Visit");

  const [permanovaGroup, setPermanovaGroup] = useState("Visit");
  const [permanovaDistance, setPermanovaDistance] = useState("braycurtis");
  const [anosimGroup, setAnosimGroup] = useState("Visit");
  const [anosimDistance, setAnosimDistance] = useState("braycurtis");

  // Rarefaction
  const [rarefactionMetrics, setRarefactionMetrics] = useState<string[]>(["richness", "shannon"]);
  const [rarefactionGroup, setRarefactionGroup] = useState("Visit");
  const [rarefactionSteps, setRarefactionSteps] = useState(20);
  const [rarefactionIterations, setRarefactionIterations] = useState(10);
  // Taxonomy Bar
  const [taxonomyBarLevel, setTaxonomyBarLevel] = useState("Genus");
  const [taxonomyBarTopN, setTaxonomyBarTopN] = useState(15);
  const [taxonomyBarGroup, setTaxonomyBarGroup] = useState("Visit");
  // Core Microbiome
  const [corePrevalence, setCorePrevalence] = useState(0.5);
  const [coreAbundance, setCoreAbundance] = useState(0.01);
  const [coreGroup, setCoreGroup] = useState("Visit");

  // ─── Tab 2: Differential Analysis ───
  const [diffMethod, setDiffMethod] = useState("Wilcoxon");
  const [diffGroup, setDiffGroup] = useState("Visit");
  const [diffContrast, setDiffContrast] = useState("Control vs Treatment");
  const [diffCorrection, setDiffCorrection] = useState("BH");
  const [diffPvalue, setDiffPvalue] = useState(0.05);
  // LEfSe
  const [lefseLdaThreshold, setLefseLdaThreshold] = useState(2.0);
  // ANCOM-BC
  const [ancombcZeroCut, setAncombcZeroCut] = useState(0.9);
  const [ancombcLibCut, setAncombcLibCut] = useState(0);
  const [ancombcStrucZero, setAncombcStrucZero] = useState(true);
  const [ancombcPAdjMethod, setAncombcPAdjMethod] = useState('BH');
  // MaAsLin3
  const [maaslin3FixedEffects, setMaaslin3FixedEffects] = useState<string[]>([]);
  const [maaslin3RandomEffects, setMaaslin3RandomEffects] = useState<string[]>([]);
  const [maaslin3Normalization, setMaaslin3Normalization] = useState('TSS');
  const [maaslin3Transform, setMaaslin3Transform] = useState('LOG');
  const [maaslin3Reference, setMaaslin3Reference] = useState('Control');

  // ─── Tab 3: Network & Function ───
  const [networkSubTab, setNetworkSubTab] = useState<"network" | "functional" | "metabolomics">("network");
  const [corrMethod, setCorrMethod] = useState("sparcc");
  const [corrThreshold, setCorrThreshold] = useState(0.3);
  const [networkTopN, setNetworkTopN] = useState(50);

  // ─── Tab 4: Advanced Methods ───
  const [advancedSubTab, setAdvancedSubTab] = useState<"dimred" | "clustering" | "network" | "aldex2" | "songbird" | "wgcna" | "enterotype">("dimred");
  const [dimredMethod, setDimredMethod] = useState<"tsne" | "umap">("umap");
  const [dimredPerplexity, setDimredPerplexity] = useState(30);
  const [dimredNeighbors, setDimredNeighbors] = useState(15);
  const [dimredGroup, setDimredGroup] = useState("Visit");

  const [hclustMethod, setHclustMethod] = useState("ward");
  const [hclustDistance, setHclustDistance] = useState("braycurtis");
  const [hclustTopN, setHclustTopN] = useState(50);

  const [sourceTrackingSink, setSourceTrackingSink] = useState("sample");

  // ALDEx2
  const [aldex2Group, setAldex2Group] = useState("Visit");
  const [aldex2Method, setAldex2Method] = useState("welch");
  // Songbird
  const [songbirdGroup, setSongbirdGroup] = useState("Visit");
  const [songbirdEpochs, setSongbirdEpochs] = useState(1000);
  // WGCNA
  const [wgcnaPower, setWgcnaPower] = useState(6);
  const [wgcnaMinModule, setWgcnaMinModule] = useState(10);
  const [wgcnaGroup, setWgcnaGroup] = useState("Visit");
  // Enterotype
  const [enterotypeN, setEnterotypeN] = useState(3);
  const [enterotypeDistance, setEnterotypeDistance] = useState("jaccard");

  const { sessionId, hasSession } = useRequiredSession();
  // Grouping variables come from the uploaded metadata, not a fixed list.
  const { groupingColumns } = useMetadataColumns(sessionId);
  const metadataColumns = groupingColumns.map((c) => c.name);

  // ─── Handlers ───

  const handleRunCommunity = useCallback(async () => {
    clearResult();
    let response: AnalysisJobResponse;

    if (communitySubTab === "alpha") {
      response = await runAnalysis("alpha-diversity", sessionId, {
        indices: alphaIndices,
        group_column: alphaGroup,
        test_method: alphaTest,
      });
      sessionStore.addAnalysisHistoryItem({
        id: response.job_id,
        type: "Alpha Diversity",
        label: alphaIndices.join(", "),
        timestamp: new Date().toISOString(),
        status: "success",
        plotData: response.plot_data,
        statistics: response.statistics,
        tableData: response.data,
        params: { indices: alphaIndices, group_column: alphaGroup, test_method: alphaTest },
      });
    } else if (communitySubTab === "beta") {
      const betaParams = {
        distance_metric: betaDistance,
        ordination: betaOrdination,
        group_column: betaGroup,
      };
      response = await runAnalysis(
        betaOrdination === "PCoA" ? "pcoa" : "nmds",
        sessionId,
        betaParams
      );
      sessionStore.addAnalysisHistoryItem({
        id: response.job_id,
        type: "Beta Diversity",
        label: `${betaDistance} ${betaOrdination}`,
        timestamp: new Date().toISOString(),
        status: "success",
        plotData: response.plot_data,
        statistics: response.statistics,
        tableData: response.data,
        params: betaParams,
      });
    } else if (communitySubTab === "composition") {
      response = await runAnalysis(
        compType === "stacked-bar" ? "stacked-bar" : "heatmap",
        sessionId,
        {
          top_n: compTopN,
          tax_level: compTaxLevel,
          group_column: compGroup,
        }
      );
      sessionStore.addAnalysisHistoryItem({
        id: response.job_id,
        type: "Species Composition",
        label: compType === "stacked-bar" ? "Stacked Bar" : "Heatmap",
        timestamp: new Date().toISOString(),
        status: "success",
        plotData: response.plot_data,
        statistics: response.statistics,
        tableData: response.data,
        params: { top_n: compTopN, tax_level: compTaxLevel, group_column: compGroup },
      });
    } else if (communitySubTab === "rarefaction") {
      response = await runAnalysis("rarefaction", sessionId, {
        metrics: rarefactionMetrics,
        group_column: rarefactionGroup,
        steps: rarefactionSteps,
        iterations: rarefactionIterations,
      });
      sessionStore.addAnalysisHistoryItem({
        id: response.job_id,
        type: "Rarefaction",
        label: rarefactionMetrics.join(", "),
        timestamp: new Date().toISOString(),
        status: "success",
        plotData: response.plot_data,
        statistics: response.statistics,
        tableData: response.data,
        params: { metrics: rarefactionMetrics, group_column: rarefactionGroup, steps: rarefactionSteps, iterations: rarefactionIterations },
      });
    } else if (communitySubTab === "taxonomy-bar") {
      response = await runAnalysis("taxonomy-bar", sessionId, {
        tax_level: taxonomyBarLevel.toLowerCase(),
        top_n: taxonomyBarTopN,
        group_column: taxonomyBarGroup,
      });
      sessionStore.addAnalysisHistoryItem({
        id: response.job_id,
        type: "Taxonomy Bar",
        label: taxonomyBarLevel,
        timestamp: new Date().toISOString(),
        status: "success",
        plotData: response.plot_data,
        statistics: response.statistics,
        tableData: response.data,
        params: { tax_level: taxonomyBarLevel, top_n: taxonomyBarTopN, group_column: taxonomyBarGroup },
      });
    } else if (communitySubTab === "core-microbiome") {
      response = await runAnalysis("core-microbiome", sessionId, {
        group_column: coreGroup,
        prevalence_threshold: corePrevalence,
        abundance_threshold: coreAbundance,
      });
      sessionStore.addAnalysisHistoryItem({
        id: response.job_id,
        type: "Core Microbiome",
        label: `prevalence ≥ ${corePrevalence}`,
        timestamp: new Date().toISOString(),
        status: "success",
        plotData: response.plot_data,
        statistics: response.statistics,
        tableData: response.data,
        params: { group_column: coreGroup, prevalence_threshold: corePrevalence, abundance_threshold: coreAbundance },
      });
    } else {
      // permanova / anosim
      response = await runAnalysis("permanova", sessionId, {
        group_column: permanovaGroup,
        distance_metric: permanovaDistance,
      });
      const anosimResp = await runAnalysis("anosim", sessionId, {
        group_column: anosimGroup,
        distance_metric: anosimDistance,
      });
      sessionStore.addAnalysisHistoryItem({
        id: response.job_id,
        type: "PERMANOVA / ANOSIM",
        label: `${permanovaGroup} | ${anosimGroup}`,
        timestamp: new Date().toISOString(),
        status: "success",
        plotData: response.plot_data,
        statistics: { ...response.statistics, anosim: anosimResp.statistics },
        tableData: response.data,
        params: { permanova: { group_column: permanovaGroup, distance_metric: permanovaDistance }, anosim: { group_column: anosimGroup, distance_metric: anosimDistance } },
      });
    }
  }, [communitySubTab, alphaIndices, alphaGroup, alphaTest, betaDistance, betaOrdination, betaGroup, compType, compTopN, compTaxLevel, compGroup, permanovaGroup, permanovaDistance, anosimGroup, anosimDistance, rarefactionMetrics, rarefactionGroup, rarefactionSteps, rarefactionIterations, taxonomyBarLevel, taxonomyBarTopN, taxonomyBarGroup, corePrevalence, coreAbundance, coreGroup, runAnalysis, sessionId, clearResult, sessionStore]);

  const handleRunDifferential = useCallback(async () => {
    clearResult();
    const params: Record<string, unknown> = {
      method: diffMethod,
      group_column: diffGroup,
      correction_method: diffCorrection,
      pvalue_threshold: diffPvalue,
    };
    if (diffMethod === 'ANCOM-BC') {
      params.zero_cut = ancombcZeroCut;
      params.lib_cut = ancombcLibCut;
      params.struc_zero = ancombcStrucZero;
      params.padj_method = ancombcPAdjMethod;
    } else if (diffMethod === 'MaAsLin3') {
      params.fixed_effects = maaslin3FixedEffects;
      params.random_effects = maaslin3RandomEffects;
      params.normalization = maaslin3Normalization;
      params.transform = maaslin3Transform;
      params.reference = maaslin3Reference;
    } else if (diffMethod === 'lefse') {
      params.lda_threshold = lefseLdaThreshold;
    }
    const response = await runAnalysis("differential", sessionId, params);

    sessionStore.addAnalysisHistoryItem({
      id: response.job_id,
      type: "Differential Analysis",
      label: diffMethod,
      timestamp: new Date().toISOString(),
      status: "success",
      plotData: response.plot_data,
      statistics: response.statistics,
      tableData: response.data,
      params: { ...params },
    });
  }, [diffMethod, diffGroup, diffCorrection, diffPvalue, ancombcZeroCut, ancombcLibCut, ancombcStrucZero, ancombcPAdjMethod, maaslin3FixedEffects, maaslin3RandomEffects, maaslin3Normalization, maaslin3Transform, maaslin3Reference, lefseLdaThreshold, runAnalysis, sessionId, clearResult, sessionStore]);

  const handleRunVolcano = useCallback(async () => {
    clearResult();
    const response = await runAnalysis("volcano", sessionId, {
      method: diffMethod,
      group_column: diffGroup,
      pvalue_threshold: diffPvalue,
    });
    sessionStore.addAnalysisHistoryItem({
      id: response.job_id,
      type: "Volcano Plot",
      label: `${diffMethod} | ${diffGroup}`,
      timestamp: new Date().toISOString(),
      status: "success",
      plotData: response.plot_data,
      statistics: response.statistics,
      tableData: response.data,
      params: { method: diffMethod, group_column: diffGroup, pvalue_threshold: diffPvalue },
    });
  }, [diffMethod, diffGroup, diffPvalue, runAnalysis, sessionId, clearResult, sessionStore]);

  const handleRunRandomForest = useCallback(async () => {
    clearResult();
    const response = await runAnalysis("random-forest", sessionId, {
      group_column: diffGroup,
    });
    sessionStore.addAnalysisHistoryItem({
      id: response.job_id,
      type: "Random Forest",
      label: diffGroup,
      timestamp: new Date().toISOString(),
      status: "success",
      plotData: response.plot_data,
      statistics: response.statistics,
      tableData: response.data,
      params: { group_column: diffGroup },
    });
  }, [diffGroup, runAnalysis, sessionId, clearResult, sessionStore]);

  const handleRunNetworkFunction = useCallback(async () => {
    clearResult();
    let response: AnalysisJobResponse;

    if (networkSubTab === "network") {
      response = await runAnalysis("network", sessionId, {
        correlation_method: corrMethod,
        threshold: corrThreshold,
        top_n: networkTopN,
      });
      sessionStore.addAnalysisHistoryItem({
        id: response.job_id,
        type: "Network Analysis",
        label: `${corrMethod} > ${corrThreshold}`,
        timestamp: new Date().toISOString(),
        status: "success",
        plotData: response.plot_data,
        statistics: response.statistics,
        tableData: response.data,
        params: { correlation_method: corrMethod, threshold: corrThreshold, top_n: networkTopN },
      });
    } else if (networkSubTab === "functional") {
      response = await runAnalysis("metabolomics", sessionId, {
        method: "picrust2",
      });
      sessionStore.addAnalysisHistoryItem({
        id: response.job_id,
        type: "Functional Prediction",
        label: "PICRUSt2",
        timestamp: new Date().toISOString(),
        status: "success",
        plotData: response.plot_data,
        statistics: response.statistics,
        tableData: response.data,
        params: { method: "picrust2" },
      });
    } else {
      response = await runAnalysis("metabolomics", sessionId, {
        database: "KEGG",
      });
      sessionStore.addAnalysisHistoryItem({
        id: response.job_id,
        type: "Pathway Analysis",
        label: "KEGG",
        timestamp: new Date().toISOString(),
        status: "success",
        plotData: response.plot_data,
        statistics: response.statistics,
        tableData: response.data,
        params: { database: "KEGG" },
      });
    }
  }, [networkSubTab, corrMethod, corrThreshold, networkTopN, runAnalysis, sessionId, clearResult, sessionStore]);

  const handleRunAdvanced = useCallback(async () => {
    clearResult();
    let response: AnalysisJobResponse;

    if (advancedSubTab === "dimred") {
      response = await runAnalysis("metabolomics", sessionId, {
        analysis_type: dimredMethod,
        perplexity: dimredMethod === "tsne" ? dimredPerplexity : undefined,
        n_neighbors: dimredMethod === "umap" ? dimredNeighbors : undefined,
        group_column: dimredGroup,
      });
      sessionStore.addAnalysisHistoryItem({
        id: response.job_id,
        type: "Dimensionality Reduction",
        label: dimredMethod.toUpperCase(),
        timestamp: new Date().toISOString(),
        status: "success",
        plotData: response.plot_data,
        statistics: response.statistics,
        tableData: response.data,
        params: { analysis_type: dimredMethod, group_column: dimredGroup },
      });
    } else if (advancedSubTab === "clustering") {
      response = await runAnalysis("network", sessionId, {
        cluster_method: hclustMethod,
        distance_metric: hclustDistance,
        top_n: hclustTopN,
      });
      sessionStore.addAnalysisHistoryItem({
        id: response.job_id,
        type: "Hierarchical Clustering",
        label: `${hclustMethod} | ${hclustDistance}`,
        timestamp: new Date().toISOString(),
        status: "success",
        plotData: response.plot_data,
        statistics: response.statistics,
        tableData: response.data,
        params: { cluster_method: hclustMethod, distance_metric: hclustDistance, top_n: hclustTopN },
      });
    } else if (advancedSubTab === "aldex2") {
      response = await runAnalysis("aldex2", sessionId, {
        group_column: aldex2Group,
        test_method: aldex2Method,
      });
      sessionStore.addAnalysisHistoryItem({
        id: response.job_id,
        type: "ALDEx2",
        label: aldex2Method,
        timestamp: new Date().toISOString(),
        status: "success",
        plotData: response.plot_data,
        statistics: response.statistics,
        tableData: response.data,
        params: { group_column: aldex2Group, test_method: aldex2Method },
      });
    } else if (advancedSubTab === "songbird") {
      response = await runAnalysis("songbird", sessionId, {
        group_column: songbirdGroup,
        epochs: songbirdEpochs,
      });
      sessionStore.addAnalysisHistoryItem({
        id: response.job_id,
        type: "Songbird",
        label: `${songbirdEpochs} epochs`,
        timestamp: new Date().toISOString(),
        status: "success",
        plotData: response.plot_data,
        statistics: response.statistics,
        tableData: response.data,
        params: { group_column: songbirdGroup, epochs: songbirdEpochs },
      });
    } else if (advancedSubTab === "wgcna") {
      response = await runAnalysis("wgcna", sessionId, {
        power: wgcnaPower,
        min_module_size: wgcnaMinModule,
        group_column: wgcnaGroup,
      });
      sessionStore.addAnalysisHistoryItem({
        id: response.job_id,
        type: "WGCNA",
        label: `power=${wgcnaPower}`,
        timestamp: new Date().toISOString(),
        status: "success",
        plotData: response.plot_data,
        statistics: response.statistics,
        tableData: response.data,
        params: { power: wgcnaPower, min_module_size: wgcnaMinModule, group_column: wgcnaGroup },
      });
    } else if (advancedSubTab === "enterotype") {
      response = await runAnalysis("enterotype", sessionId, {
        n_clusters: enterotypeN,
        distance_metric: enterotypeDistance,
      });
      sessionStore.addAnalysisHistoryItem({
        id: response.job_id,
        type: "Enterotype",
        label: `${enterotypeN} clusters`,
        timestamp: new Date().toISOString(),
        status: "success",
        plotData: response.plot_data,
        statistics: response.statistics,
        tableData: response.data,
        params: { n_clusters: enterotypeN, distance_metric: enterotypeDistance },
      });
    } else {
      response = await runAnalysis("network", sessionId, {
        sink: sourceTrackingSink,
      });
      sessionStore.addAnalysisHistoryItem({
        id: response.job_id,
        type: "Source Tracking",
        label: "FEAST",
        timestamp: new Date().toISOString(),
        status: "success",
        plotData: response.plot_data,
        statistics: response.statistics,
        tableData: response.data,
        params: { sink: sourceTrackingSink },
      });
    }
  }, [advancedSubTab, dimredMethod, dimredPerplexity, dimredNeighbors, dimredGroup, hclustMethod, hclustDistance, hclustTopN, sourceTrackingSink, aldex2Group, aldex2Method, songbirdGroup, songbirdEpochs, wgcnaPower, wgcnaMinModule, wgcnaGroup, enterotypeN, enterotypeDistance, runAnalysis, sessionId, clearResult, sessionStore]);

  return (
    <div data-testid="analysis-microbiome-page" className={cn("space-y-6")}>
      {!hasSession && <NoSessionBanner />}
      <div>
        <h1 data-testid="analysis-title" className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Dna className="h-6 w-6" /> Microbiome Analysis
        </h1>
        <p className="text-muted-foreground">
          Comprehensive 16S / metagenomics analysis workflows
        </p>
      </div>

      <Tabs defaultValue="community" className="w-full">
        <TabsList className="grid grid-cols-4 w-full">
          <TabsTrigger data-testid="tab-community" value="community" className="gap-2">
            <BarChart3 className="h-4 w-4" /> Community Structure
          </TabsTrigger>
          <TabsTrigger data-testid="tab-differential" value="differential" className="gap-2">
            <BrainCircuit className="h-4 w-4" /> Differential Analysis
          </TabsTrigger>
          <TabsTrigger data-testid="tab-network" value="network" className="gap-2">
            <Network className="h-4 w-4" /> Network & Function
          </TabsTrigger>
          <TabsTrigger data-testid="tab-advanced" value="advanced" className="gap-2">
            <GitBranch className="h-4 w-4" /> Advanced Methods
          </TabsTrigger>
        </TabsList>

        {/* ═══════════════════════════════════════════════════════
            TAB 1: COMMUNITY STRUCTURE
            ═══════════════════════════════════════════════════════ */}
        <TabsContent value="community" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Parameter Panel */}
            <div className="lg:col-span-1 space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Analysis Parameters</CardTitle>
                  <CardDescription>Configure community structure analysis</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <ParameterItem label="Analysis Sub-type">
                    <RadioGroup
                      value={communitySubTab}
                      onValueChange={(v) => setCommunitySubTab(v as typeof communitySubTab)}
                      className="grid grid-cols-2 gap-2"
                    >
                      {[
                        { value: "alpha", label: "Alpha Diversity" },
                        { value: "beta", label: "Beta Diversity" },
                        { value: "composition", label: "Composition" },
                        { value: "permanova", label: "PERMANOVA" },
                        { value: "rarefaction", label: "Rarefaction" },
                        { value: "taxonomy-bar", label: "Taxonomy Bar" },
                        { value: "core-microbiome", label: "Core Microbiome" },
                      ].map((opt) => (
                        <div key={opt.value} className="flex items-center space-x-2">
                          <RadioGroupItem value={opt.value} id={opt.value} />
                          <Label htmlFor={opt.value} className="cursor-pointer text-sm">{opt.label}</Label>
                        </div>
                      ))}
                    </RadioGroup>
                  </ParameterItem>

                  {communitySubTab === "alpha" && (
                    <>
                      <ParameterItem label="Diversity Indices" tooltip="Select which diversity indices to calculate">
                        <div className="grid grid-cols-2 gap-2">
                          {["Shannon", "Simpson", "InverseSimpson", "Pielou", "Observed", "Chao1"].map((idx) => (
                            <div key={idx} className="flex items-center space-x-2">
                              <Checkbox
                                id={`alpha-${idx}`}
                                checked={alphaIndices.includes(idx)}
                                onCheckedChange={(checked) => {
                                  if (checked) setAlphaIndices([...alphaIndices, idx]);
                                  else setAlphaIndices(alphaIndices.filter((i) => i !== idx));
                                }}
                              />
                              <Label htmlFor={`alpha-${idx}`} className="cursor-pointer text-sm">{idx}</Label>
                            </div>
                          ))}
                        </div>
                      </ParameterItem>
                      <ParameterItem label="Group Column">
                        <Select value={alphaGroup} onValueChange={setAlphaGroup}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {metadataColumns.map((col) => (
                              <SelectItem key={col} value={col}>{col}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label="Statistical Test">
                        <Select value={alphaTest} onValueChange={setAlphaTest}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="t-test">t-test</SelectItem>
                            <SelectItem value="Wilcoxon">Wilcoxon rank-sum</SelectItem>
                            <SelectItem value="Kruskal-Wallis">Kruskal-Wallis</SelectItem>
                            <SelectItem value="ANOVA">ANOVA</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                    </>
                  )}

                  {communitySubTab === "beta" && (
                    <>
                      <ParameterItem label="Distance Metric">
                        <Select value={betaDistance} onValueChange={setBetaDistance}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="braycurtis">Bray-Curtis</SelectItem>
                            <SelectItem value="unifrac">UniFrac</SelectItem>
                            <SelectItem value="weighted_unifrac">Weighted UniFrac</SelectItem>
                            <SelectItem value="jaccard">Jaccard</SelectItem>
                            <SelectItem value="euclidean">Euclidean</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label="Ordination Method">
                        <RadioGroup
                          value={betaOrdination}
                          onValueChange={(v) => setBetaOrdination(v as "PCoA" | "NMDS")}
                          className="grid grid-cols-2 gap-2"
                        >
                          <div className="flex items-center space-x-2">
                            <RadioGroupItem value="PCoA" id="pcoa" />
                            <Label htmlFor="pcoa" className="cursor-pointer text-sm">PCoA</Label>
                          </div>
                          <div className="flex items-center space-x-2">
                            <RadioGroupItem value="NMDS" id="nmds" />
                            <Label htmlFor="nmds" className="cursor-pointer text-sm">NMDS</Label>
                          </div>
                        </RadioGroup>
                      </ParameterItem>
                      <ParameterItem label="Group Column">
                        <Select value={betaGroup} onValueChange={setBetaGroup}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {metadataColumns.map((col) => (
                              <SelectItem key={col} value={col}>{col}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                    </>
                  )}

                  {communitySubTab === "composition" && (
                    <>
                      <ParameterItem label="Visualization Type">
                        <RadioGroup
                          value={compType}
                          onValueChange={(v) => setCompType(v as typeof compType)}
                          className="grid grid-cols-2 gap-2"
                        >
                          <div className="flex items-center space-x-2">
                            <RadioGroupItem value="stacked-bar" id="stacked-bar" />
                            <Label htmlFor="stacked-bar" className="cursor-pointer text-sm">Stacked Bar</Label>
                          </div>
                          <div className="flex items-center space-x-2">
                            <RadioGroupItem value="heatmap" id="heatmap" />
                            <Label htmlFor="heatmap" className="cursor-pointer text-sm">Heatmap</Label>
                          </div>
                        </RadioGroup>
                      </ParameterItem>
                      <ParameterItem label={`Top N Taxa (${compTopN})`}>
                        <Slider value={[compTopN]} onValueChange={(v) => setCompTopN(v[0])} min={10} max={100} step={5} />
                      </ParameterItem>
                      <ParameterItem label="Taxonomic Level">
                        <Select value={compTaxLevel} onValueChange={setCompTaxLevel}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="Phylum">Phylum</SelectItem>
                            <SelectItem value="Class">Class</SelectItem>
                            <SelectItem value="Order">Order</SelectItem>
                            <SelectItem value="Family">Family</SelectItem>
                            <SelectItem value="Genus">Genus</SelectItem>
                            <SelectItem value="Species">Species</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label="Group Column">
                        <Select value={compGroup} onValueChange={setCompGroup}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {metadataColumns.map((col) => (
                              <SelectItem key={col} value={col}>{col}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                    </>
                  )}

                  {communitySubTab === "permanova" && (
                    <>
                      <ParameterItem label="PERMANOVA Group Column">
                        <Select value={permanovaGroup} onValueChange={setPermanovaGroup}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {metadataColumns.map((col) => (
                              <SelectItem key={col} value={col}>{col}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label="PERMANOVA Distance Metric">
                        <Select value={permanovaDistance} onValueChange={setPermanovaDistance}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="braycurtis">Bray-Curtis</SelectItem>
                            <SelectItem value="unifrac">UniFrac</SelectItem>
                            <SelectItem value="weighted_unifrac">Weighted UniFrac</SelectItem>
                            <SelectItem value="jaccard">Jaccard</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <div className="border-t pt-4 mt-4 space-y-4">
                        <ParameterItem label="ANOSIM Group Column">
                          <Select value={anosimGroup} onValueChange={setAnosimGroup}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              {metadataColumns.map((col) => (
                                <SelectItem key={col} value={col}>{col}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </ParameterItem>
                        <ParameterItem label="ANOSIM Distance Metric">
                          <Select value={anosimDistance} onValueChange={setAnosimDistance}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="braycurtis">Bray-Curtis</SelectItem>
                              <SelectItem value="unifrac">UniFrac</SelectItem>
                              <SelectItem value="weighted_unifrac">Weighted UniFrac</SelectItem>
                              <SelectItem value="jaccard">Jaccard</SelectItem>
                            </SelectContent>
                          </Select>
                        </ParameterItem>
                      </div>
                    </>
                  )}

                  {communitySubTab === "rarefaction" && (
                    <>
                      <ParameterItem label="Metrics" tooltip="Select alpha diversity metrics to compute">
                        <div className="grid grid-cols-2 gap-2">
                          {["richness", "shannon", "simpson"].map((idx) => (
                            <div key={idx} className="flex items-center space-x-2">
                              <Checkbox
                                id={`rare-${idx}`}
                                checked={rarefactionMetrics.includes(idx)}
                                onCheckedChange={(checked) => {
                                  if (checked) setRarefactionMetrics([...rarefactionMetrics, idx]);
                                  else setRarefactionMetrics(rarefactionMetrics.filter((i) => i !== idx));
                                }}
                              />
                              <Label htmlFor={`rare-${idx}`} className="cursor-pointer text-sm">{idx.charAt(0).toUpperCase() + idx.slice(1)}</Label>
                            </div>
                          ))}
                        </div>
                      </ParameterItem>
                      <ParameterItem label="Group Column">
                        <Select value={rarefactionGroup} onValueChange={setRarefactionGroup}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {metadataColumns.map((col) => (
                              <SelectItem key={col} value={col}>{col}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label={`Steps (${rarefactionSteps})`}>
                        <Slider value={[rarefactionSteps]} onValueChange={(v) => setRarefactionSteps(v[0])} min={5} max={50} step={5} />
                      </ParameterItem>
                      <ParameterItem label={`Iterations (${rarefactionIterations})`}>
                        <Slider value={[rarefactionIterations]} onValueChange={(v) => setRarefactionIterations(v[0])} min={5} max={30} step={5} />
                      </ParameterItem>
                    </>
                  )}

                  {communitySubTab === "taxonomy-bar" && (
                    <>
                      <ParameterItem label="Taxonomic Level">
                        <Select value={taxonomyBarLevel} onValueChange={setTaxonomyBarLevel}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="Phylum">Phylum</SelectItem>
                            <SelectItem value="Class">Class</SelectItem>
                            <SelectItem value="Order">Order</SelectItem>
                            <SelectItem value="Family">Family</SelectItem>
                            <SelectItem value="Genus">Genus</SelectItem>
                            <SelectItem value="Species">Species</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label={`Top N Taxa (${taxonomyBarTopN})`}>
                        <Slider value={[taxonomyBarTopN]} onValueChange={(v) => setTaxonomyBarTopN(v[0])} min={5} max={30} step={1} />
                      </ParameterItem>
                      <ParameterItem label="Group Column">
                        <Select value={taxonomyBarGroup} onValueChange={setTaxonomyBarGroup}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {metadataColumns.map((col) => (
                              <SelectItem key={col} value={col}>{col}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                    </>
                  )}

                  {communitySubTab === "core-microbiome" && (
                    <>
                      <ParameterItem label={`Prevalence Threshold (${corePrevalence.toFixed(2)})`} tooltip="Minimum fraction of samples a taxon must be present in">
                        <Slider value={[corePrevalence]} onValueChange={(v) => setCorePrevalence(v[0])} min={0.1} max={1.0} step={0.05} />
                      </ParameterItem>
                      <ParameterItem label={`Abundance Threshold (${coreAbundance.toFixed(3)})`} tooltip="Minimum relative abundance to count as present">
                        <Slider value={[coreAbundance]} onValueChange={(v) => setCoreAbundance(v[0])} min={0.001} max={0.1} step={0.001} />
                      </ParameterItem>
                      <ParameterItem label="Group Column">
                        <Select value={coreGroup} onValueChange={setCoreGroup}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {metadataColumns.map((col) => (
                              <SelectItem key={col} value={col}>{col}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                    </>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Results Panel */}
            <div className="lg:col-span-2">
              <ResultSection
                title={
                  communitySubTab === "alpha"
                    ? "Alpha Diversity Boxplot"
                    : communitySubTab === "beta"
                    ? `${betaOrdination} Plot (${betaDistance})`
                    : communitySubTab === "composition"
                    ? compType === "stacked-bar"
                      ? "Stacked Bar Composition"
                      : "Taxa Heatmap"
                    : communitySubTab === "rarefaction"
                    ? "Rarefaction Curves"
                    : communitySubTab === "taxonomy-bar"
                    ? `Taxonomy Bar (${taxonomyBarLevel})`
                    : communitySubTab === "core-microbiome"
                    ? "Core Microbiome Detection"
                    : "PERMANOVA / ANOSIM Results"
                }
                plotData={result?.plot_data}
                tableData={result?.data}
                stats={result?.statistics}
                isLoading={isLoading}
                onRun={handleRunCommunity}
              />
            </div>
          </div>
        </TabsContent>

        {/* ═══════════════════════════════════════════════════════
            TAB 2: DIFFERENTIAL ANALYSIS
            ═══════════════════════════════════════════════════════ */}
        <TabsContent value="differential" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-1 space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Differential Parameters</CardTitle>
                  <CardDescription>Configure differential abundance analysis</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <ParameterItem label="Method">
                    <Select value={diffMethod} onValueChange={setDiffMethod}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Wilcoxon">Wilcoxon rank-sum</SelectItem>
                        <SelectItem value="t-test">t-test</SelectItem>
                        <SelectItem value="lefse">LEfSe (LDA Effect Size)</SelectItem>
                        <SelectItem value="ANCOM-BC">ANCOM-BC (composition-aware)</SelectItem>
                        <SelectItem value="MaAsLin3">MaAsLin3 (multivariate)</SelectItem>
                      </SelectContent>
                    </Select>
                  </ParameterItem>
                  <ParameterItem label="Group Column">
                    <Select value={diffGroup} onValueChange={setDiffGroup}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {metadataColumns.map((col) => (
                          <SelectItem key={col} value={col}>{col}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </ParameterItem>
                  <ParameterItem label="Contrast Groups">
                    <Select value={diffContrast} onValueChange={setDiffContrast}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Control vs Treatment">Control vs Treatment</SelectItem>
                        <SelectItem value="Group A vs Group B">Group A vs Group B</SelectItem>
                        <SelectItem value="Pre vs Post">Pre vs Post</SelectItem>
                        <SelectItem value="Baseline vs Follow-up">Baseline vs Follow-up</SelectItem>
                      </SelectContent>
                    </Select>
                  </ParameterItem>
                  <ParameterItem label="Multiple Testing Correction">
                    <Select value={diffCorrection} onValueChange={setDiffCorrection}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="BH">Benjamini-Hochberg (BH)</SelectItem>
                        <SelectItem value="Bonferroni">Bonferroni</SelectItem>
                        <SelectItem value="None">None</SelectItem>
                      </SelectContent>
                    </Select>
                  </ParameterItem>
                  <ParameterItem label={`P-value Threshold (${diffPvalue.toFixed(3)})`}>
                    <Slider value={[diffPvalue]} onValueChange={(v) => setDiffPvalue(v[0])} min={0.001} max={0.1} step={0.001} />
                  </ParameterItem>

                  {diffMethod === 'lefse' && (
                    <>
                      <ParameterItem label={`LDA Threshold (${lefseLdaThreshold.toFixed(1)})`} tooltip="LDA score threshold for identifying differentially abundant features">
                        <Slider value={[lefseLdaThreshold]} onValueChange={(v) => setLefseLdaThreshold(v[0])} min={1.0} max={4.0} step={0.1} />
                      </ParameterItem>
                      <div className="p-3 bg-blue-50 rounded-lg text-xs text-blue-700">
                        LEfSe performs LDA analysis on features significantly different between groups (Kruskal-Wallis p &lt; 0.05)
                      </div>
                    </>
                  )}

                  {diffMethod === 'ANCOM-BC' && (
                    <>
                      <ParameterItem label={`Zero Cutoff (${ancombcZeroCut.toFixed(2)})`}>
                        <Slider value={[ancombcZeroCut]} onValueChange={(v) => setAncombcZeroCut(v[0])} min={0.5} max={1.0} step={0.01} />
                      </ParameterItem>
                      <ParameterItem label={`Library Cutoff (${ancombcLibCut})`}>
                        <Slider value={[ancombcLibCut]} onValueChange={(v) => setAncombcLibCut(v[0])} min={0} max={100} step={5} />
                      </ParameterItem>
                      <ParameterItem label="Structural Zero Detection">
                        <div className="flex items-center space-x-2">
                          <Checkbox id="struc-zero" checked={ancombcStrucZero} onCheckedChange={(checked) => setAncombcStrucZero(checked === true)} />
                          <Label htmlFor="struc-zero" className="cursor-pointer text-sm">Enable structural zero detection</Label>
                        </div>
                      </ParameterItem>
                      <ParameterItem label="P-value Adjustment">
                        <Select value={ancombcPAdjMethod} onValueChange={setAncombcPAdjMethod}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {['holm','hochberg','hommel','bonferroni','BH','BY','fdr','none'].map((m) => (
                              <SelectItem key={m} value={m}>{m}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                    </>
                  )}

                  {diffMethod === 'MaAsLin3' && (
                    <>
                      <ParameterItem label="Fixed Effects">
                        <div className="grid grid-cols-2 gap-2">
                          {metadataColumns.filter(col => col !== diffGroup).map((col) => (
                            <div key={col} className="flex items-center space-x-2">
                              <Checkbox
                                id={`fixed-${col}`}
                                checked={maaslin3FixedEffects.includes(col)}
                                onCheckedChange={(checked) => {
                                  if (checked) setMaaslin3FixedEffects([...maaslin3FixedEffects, col]);
                                  else setMaaslin3FixedEffects(maaslin3FixedEffects.filter((i) => i !== col));
                                }}
                              />
                              <Label htmlFor={`fixed-${col}`} className="cursor-pointer text-sm">{col}</Label>
                            </div>
                          ))}
                        </div>
                      </ParameterItem>
                      <ParameterItem label="Random Effects">
                        <div className="grid grid-cols-2 gap-2">
                          {metadataColumns.map((col) => (
                            <div key={col} className="flex items-center space-x-2">
                              <Checkbox
                                id={`random-${col}`}
                                checked={maaslin3RandomEffects.includes(col)}
                                onCheckedChange={(checked) => {
                                  if (checked) setMaaslin3RandomEffects([...maaslin3RandomEffects, col]);
                                  else setMaaslin3RandomEffects(maaslin3RandomEffects.filter((i) => i !== col));
                                }}
                              />
                              <Label htmlFor={`random-${col}`} className="cursor-pointer text-sm">{col}</Label>
                            </div>
                          ))}
                        </div>
                      </ParameterItem>
                      <ParameterItem label="Normalization">
                        <Select value={maaslin3Normalization} onValueChange={setMaaslin3Normalization}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="TSS">TSS</SelectItem>
                            <SelectItem value="CSS">CSS</SelectItem>
                            <SelectItem value="CLR">CLR</SelectItem>
                            <SelectItem value="NONE">NONE</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label="Transformation">
                        <Select value={maaslin3Transform} onValueChange={setMaaslin3Transform}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="LOG">LOG</SelectItem>
                            <SelectItem value="AST">AST</SelectItem>
                            <SelectItem value="NONE">NONE</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label="Reference Level">
                        <Select value={maaslin3Reference} onValueChange={setMaaslin3Reference}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="Control">Control</SelectItem>
                            <SelectItem value="Baseline">Baseline</SelectItem>
                            <SelectItem value="Group A">Group A</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                    </>
                  )}
                </CardContent>
              </Card>
            </div>
            <div className="lg:col-span-2 space-y-6">
              <ResultSection
                title={diffMethod === 'MaAsLin3' ? "MaAsLin3 Association Plot" : "Differential Abundance Results"}
                plotData={result?.plot_data}
                tableData={result?.data}
                stats={result?.statistics}
                isLoading={isLoading}
                onRun={handleRunDifferential}
              />

              <Card>
                <CardHeader>
                  <CardTitle>Additional Plots</CardTitle>
                  <CardDescription>Generate supplementary visualizations</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <Button variant="outline" onClick={handleRunVolcano} disabled={isLoading} className="gap-2">
                      {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <BarChart3 className="h-4 w-4" />}
                      Generate Volcano Plot
                    </Button>
                    <Button variant="outline" onClick={handleRunRandomForest} disabled={isLoading} className="gap-2">
                      {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <BrainCircuit className="h-4 w-4" />}
                      Random Forest Importance
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </TabsContent>

        {/* ═══════════════════════════════════════════════════════
            TAB 3: NETWORK & FUNCTION
            ═══════════════════════════════════════════════════════ */}
        <TabsContent value="network" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-1 space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Network & Function Parameters</CardTitle>
                  <CardDescription>Configure network and functional analysis</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <ParameterItem label="Analysis Sub-type">
                    <RadioGroup
                      value={networkSubTab}
                      onValueChange={(v) => setNetworkSubTab(v as typeof networkSubTab)}
                      className="grid grid-cols-1 gap-2"
                    >
                      {[
                        { value: "network", label: "Correlation Network", icon: Network },
                        { value: "functional", label: "PICRUSt2 Functional Prediction", icon: FunctionSquare },
                        { value: "metabolomics", label: "KEGG Pathway Analysis", icon: BarChart3 },
                      ].map((opt) => (
                        <div key={opt.value} className="flex items-center space-x-2">
                          <RadioGroupItem value={opt.value} id={opt.value} />
                          <Label htmlFor={opt.value} className="cursor-pointer text-sm flex items-center gap-1">
                            <opt.icon className="h-3.5 w-3.5" /> {opt.label}
                          </Label>
                        </div>
                      ))}
                    </RadioGroup>
                  </ParameterItem>

                  {networkSubTab === "network" && (
                    <>
                      <ParameterItem label="Correlation Method">
                        <Select value={corrMethod} onValueChange={setCorrMethod}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="sparcc">SparCC (composition-aware)</SelectItem>
                            <SelectItem value="pearson">Pearson</SelectItem>
                            <SelectItem value="spearman">Spearman</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label={`Correlation Threshold (${corrThreshold.toFixed(2)})`}>
                        <Slider value={[corrThreshold]} onValueChange={(v) => setCorrThreshold(v[0])} min={0.1} max={0.9} step={0.05} />
                      </ParameterItem>
                      <ParameterItem label={`Top N Features (${networkTopN})`}>
                        <Slider value={[networkTopN]} onValueChange={(v) => setNetworkTopN(v[0])} min={10} max={200} step={10} />
                      </ParameterItem>
                    </>
                  )}

                  {networkSubTab === "functional" && (
                    <div className="p-3 bg-green-50 rounded-lg text-xs text-green-700">
                      PICRUSt2 predicts metagenome functional content from 16S rRNA gene sequences using phylogenetic information.
                    </div>
                  )}

                  {networkSubTab === "metabolomics" && (
                    <div className="p-3 bg-amber-50 rounded-lg text-xs text-amber-700">
                      KEGG pathway enrichment analysis identifies significantly over-represented pathways in your dataset.
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
            <div className="lg:col-span-2">
              <ResultSection
                title={
                  networkSubTab === "network"
                    ? "Correlation Network"
                    : networkSubTab === "functional"
                    ? "PICRUSt2 Functional Prediction"
                    : "KEGG Pathway Analysis"
                }
                plotData={result?.plot_data}
                tableData={result?.data}
                stats={result?.statistics}
                isLoading={isLoading}
                onRun={handleRunNetworkFunction}
              />
            </div>
          </div>
        </TabsContent>

        {/* ═══════════════════════════════════════════════════════
            TAB 4: ADVANCED METHODS
            ═══════════════════════════════════════════════════════ */}
        <TabsContent value="advanced" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-1 space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Advanced Parameters</CardTitle>
                  <CardDescription>Configure advanced analysis methods</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <ParameterItem label="Analysis Sub-type">
                    <RadioGroup
                      value={advancedSubTab}
                      onValueChange={(v) => setAdvancedSubTab(v as typeof advancedSubTab)}
                      className="grid grid-cols-1 gap-2"
                    >
                      {[
                        { value: "dimred", label: "Dimensionality Reduction", icon: BarChart3 },
                        { value: "clustering", label: "Hierarchical Clustering", icon: GitBranch },
                        { value: "network", label: "Source Tracking (FEAST)", icon: Map },
                        { value: "aldex2", label: "ALDEx2", icon: FlaskConical },
                        { value: "songbird", label: "Songbird", icon: Dna },
                        { value: "wgcna", label: "WGCNA", icon: Network },
                        { value: "enterotype", label: "Enterotype", icon: CircleDot },
                      ].map((opt) => (
                        <div key={opt.value} className="flex items-center space-x-2">
                          <RadioGroupItem value={opt.value} id={opt.value} />
                          <Label htmlFor={opt.value} className="cursor-pointer text-sm flex items-center gap-1">
                            <opt.icon className="h-3.5 w-3.5" /> {opt.label}
                          </Label>
                        </div>
                      ))}
                    </RadioGroup>
                  </ParameterItem>

                  {advancedSubTab === "dimred" && (
                    <>
                      <ParameterItem label="Method">
                        <RadioGroup
                          value={dimredMethod}
                          onValueChange={(v) => setDimredMethod(v as "tsne" | "umap")}
                          className="grid grid-cols-2 gap-2"
                        >
                          <div className="flex items-center space-x-2">
                            <RadioGroupItem value="tsne" id="tsne" />
                            <Label htmlFor="tsne" className="cursor-pointer text-sm">t-SNE</Label>
                          </div>
                          <div className="flex items-center space-x-2">
                            <RadioGroupItem value="umap" id="umap" />
                            <Label htmlFor="umap" className="cursor-pointer text-sm">UMAP</Label>
                          </div>
                        </RadioGroup>
                      </ParameterItem>
                      {dimredMethod === "tsne" && (
                        <ParameterItem label={`Perplexity (${dimredPerplexity})`} tooltip="t-SNE perplexity balances local and global structure">
                          <Slider value={[dimredPerplexity]} onValueChange={(v) => setDimredPerplexity(v[0])} min={5} max={100} step={5} />
                        </ParameterItem>
                      )}
                      {dimredMethod === "umap" && (
                        <ParameterItem label={`n_neighbors (${dimredNeighbors})`} tooltip="UMAP neighborhood size">
                          <Slider value={[dimredNeighbors]} onValueChange={(v) => setDimredNeighbors(v[0])} min={2} max={100} step={1} />
                        </ParameterItem>
                      )}
                      <ParameterItem label="Group Column">
                        <Select value={dimredGroup} onValueChange={setDimredGroup}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {metadataColumns.map((col) => (
                              <SelectItem key={col} value={col}>{col}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                    </>
                  )}

                  {advancedSubTab === "clustering" && (
                    <>
                      <ParameterItem label="Clustering Method">
                        <Select value={hclustMethod} onValueChange={setHclustMethod}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="ward">Ward</SelectItem>
                            <SelectItem value="complete">Complete</SelectItem>
                            <SelectItem value="average">Average</SelectItem>
                            <SelectItem value="single">Single</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label="Distance Metric">
                        <Select value={hclustDistance} onValueChange={setHclustDistance}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="braycurtis">Bray-Curtis</SelectItem>
                            <SelectItem value="euclidean">Euclidean</SelectItem>
                            <SelectItem value="manhattan">Manhattan</SelectItem>
                            <SelectItem value="correlation">Correlation</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label={`Top N Features (${hclustTopN})`}>
                        <Slider value={[hclustTopN]} onValueChange={(v) => setHclustTopN(v[0])} min={10} max={200} step={10} />
                      </ParameterItem>
                    </>
                  )}

                  {advancedSubTab === "network" && (
                    <>
                      <ParameterItem label="Sink Definition" tooltip="Define how sink samples are identified">
                        <Select value={sourceTrackingSink} onValueChange={setSourceTrackingSink}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="sample">By Sample ID</SelectItem>
                            <SelectItem value="group">By Group Column</SelectItem>
                            <SelectItem value="auto">Auto-detect</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <div className="p-3 bg-emerald-50 rounded-lg text-xs text-emerald-700">
                        FEAST (Fast Expectation-Maximization for microbial Source Tracking) estimates the proportion of each source community contributing to a sink sample.
                      </div>
                    </>
                  )}

                  {advancedSubTab === "aldex2" && (
                    <>
                      <ParameterItem label="Group Column">
                        <Select value={aldex2Group} onValueChange={setAldex2Group}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {metadataColumns.map((col) => (
                              <SelectItem key={col} value={col}>{col}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label="Test Method">
                        <Select value={aldex2Method} onValueChange={setAldex2Method}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="welch">Welch t-test</SelectItem>
                            <SelectItem value="mannwhitney">Mann-Whitney U</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <div className="p-3 bg-blue-50 rounded-lg text-xs text-blue-700">
                        ALDEx2 performs CLR transformation followed by Welch's t-test or Wilcoxon rank-sum test, accounting for compositional bias.
                      </div>
                    </>
                  )}

                  {advancedSubTab === "songbird" && (
                    <>
                      <ParameterItem label="Group Column">
                        <Select value={songbirdGroup} onValueChange={setSongbirdGroup}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {metadataColumns.map((col) => (
                              <SelectItem key={col} value={col}>{col}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label={`Epochs (${songbirdEpochs})`}>
                        <Slider value={[songbirdEpochs]} onValueChange={(v) => setSongbirdEpochs(v[0])} min={100} max={5000} step={100} />
                      </ParameterItem>
                      <div className="p-3 bg-purple-50 rounded-lg text-xs text-purple-700">
                        Songbird uses multinomial regression to estimate differential abundance, providing consistent log-fold changes across all features.
                      </div>
                    </>
                  )}

                  {advancedSubTab === "wgcna" && (
                    <>
                      <ParameterItem label={`Soft-thresholding Power (${wgcnaPower})`} tooltip="Higher power emphasizes strong correlations">
                        <Slider value={[wgcnaPower]} onValueChange={(v) => setWgcnaPower(v[0])} min={1} max={20} step={1} />
                      </ParameterItem>
                      <ParameterItem label={`Min Module Size (${wgcnaMinModule})`}>
                        <Slider value={[wgcnaMinModule]} onValueChange={(v) => setWgcnaMinModule(v[0])} min={5} max={50} step={5} />
                      </ParameterItem>
                      <ParameterItem label="Group Column">
                        <Select value={wgcnaGroup} onValueChange={setWgcnaGroup}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {metadataColumns.map((col) => (
                              <SelectItem key={col} value={col}>{col}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <div className="p-3 bg-amber-50 rounded-lg text-xs text-amber-700">
                        WGCNA identifies co-occurrence modules via soft-thresholded correlation networks and hierarchical clustering.
                      </div>
                    </>
                  )}

                  {advancedSubTab === "enterotype" && (
                    <>
                      <ParameterItem label={`Number of Clusters (${enterotypeN})`}>
                        <Slider value={[enterotypeN]} onValueChange={(v) => setEnterotypeN(v[0])} min={2} max={6} step={1} />
                      </ParameterItem>
                      <ParameterItem label="Distance Metric">
                        <Select value={enterotypeDistance} onValueChange={setEnterotypeDistance}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="jaccard">Jaccard</SelectItem>
                            <SelectItem value="braycurtis">Bray-Curtis</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <div className="p-3 bg-rose-50 rounded-lg text-xs text-rose-700">
                        Enterotype clustering partitions samples into distinct community types using PAM clustering on ecological distance matrices.
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>
            </div>
            <div className="lg:col-span-2">
              <ResultSection
                title={
                  advancedSubTab === "dimred"
                    ? `${dimredMethod.toUpperCase()} Projection`
                    : advancedSubTab === "clustering"
                    ? "Hierarchical Clustering Dendrogram"
                    : advancedSubTab === "aldex2"
                    ? "ALDEx2 Differential Abundance"
                    : advancedSubTab === "songbird"
                    ? "Songbird Multinomial Regression"
                    : advancedSubTab === "wgcna"
                    ? `WGCNA Co-occurrence Network (power=${wgcnaPower})`
                    : advancedSubTab === "enterotype"
                    ? `Enterotype Clustering (${enterotypeN} clusters)`
                    : "Source Tracking (FEAST) Proportions"
                }
                plotData={result?.plot_data}
                tableData={result?.data}
                stats={result?.statistics}
                isLoading={isLoading}
                onRun={handleRunAdvanced}
              />
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
