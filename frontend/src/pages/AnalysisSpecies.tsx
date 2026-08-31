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
import { StatusAlert } from "@/components/shared/StatusAlert";
import { useAnalysis } from "@/hooks/useAnalysis";
import { downloadFigure, downloadCSV, downloadPDF } from "@/utils/api";
import type { PlotlyFigure, AnalysisJobResponse, DifferentialParams } from "@/types";
import {
  BarChart3,
  Dna,
  Network,
  BrainCircuit,
  FunctionSquare,
  Play,
  Image as ImageIcon,
  FileSpreadsheet,
  Loader2,
  HelpCircle,
  FileText,
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

export function AnalysisSpecies() {
  const sessionStore = useSessionStore();
  const setCurrentStep = useSessionStore((state) => state.setCurrentStep);
  const { runAnalysis, isLoading, result, clearResult, error: analysisError } = useAnalysis();

  useEffect(() => {
    setCurrentStep("microbiome");
  }, [setCurrentStep]);

  // Community analysis state
  const [communityType, setCommunityType] = useState<"alpha" | "beta">("alpha");
  const [alphaIndices, setAlphaIndices] = useState<string[]>(["Shannon", "Simpson"]);
  const [alphaGroup, setAlphaGroup] = useState("Treatment");
  const [alphaTest, setAlphaTest] = useState("Kruskal-Wallis");

  const [betaDistance, setBetaDistance] = useState("Bray-Curtis");
  const [betaOrdination, setBetaOrdination] = useState("PCoA");
  const [betaGroup, setBetaGroup] = useState("Treatment");
  const [betaTest, setBetaTest] = useState("PERMANOVA");

  // Differential analysis state
  const [diffMethod, setDiffMethod] = useState("Wilcoxon");
  const [diffGroup, setDiffGroup] = useState("Treatment");
  const [diffContrast, setDiffContrast] = useState("Control vs Treatment");
  const [diffCorrection, setDiffCorrection] = useState("BH");
  const [diffPvalue, setDiffPvalue] = useState(0.05);
  // ANCOM-BC params
  const [ancombcZeroCut, setAncombcZeroCut] = useState(0.9);
  const [ancombcLibCut, setAncombcLibCut] = useState(0);
  const [ancombcStrucZero, setAncombcStrucZero] = useState(true);
  const [ancombcPAdjMethod, setAncombcPAdjMethod] = useState('BH');
  // MaAsLin3 params
  const [maaslin3FixedEffects, setMaaslin3FixedEffects] = useState<string[]>([]);
  const [maaslin3RandomEffects, setMaaslin3RandomEffects] = useState<string[]>([]);
  const [maaslin3Normalization, setMaaslin3Normalization] = useState('TSS');
  const [maaslin3Transform, setMaaslin3Transform] = useState('LOG');
  const [maaslin3Reference, setMaaslin3Reference] = useState('Control');
  // LEfSe params
  const [lefseLdaThreshold, setLefseLdaThreshold] = useState(2.0);

  // Clustering state
  const [clusterType, setClusterType] = useState<"heatmap" | "network">("heatmap");
  const [topN, setTopN] = useState(50);
  const [clusterMethod, setClusterMethod] = useState("complete");
  const [corrMethod, setCorrMethod] = useState("Pearson");
  const [corrThreshold, setCorrThreshold] = useState(0.3);

  // ML state
  const [mlMethod, setMlMethod] = useState("Random Forest");
  const [mlGroup, setMlGroup] = useState("Treatment");
  const [mlCV, setMlCV] = useState("5-fold");

  const { sessionId, hasSession } = useRequiredSession();
  // Grouping variables come from the uploaded metadata, not a fixed list.
  const { groupingColumns } = useMetadataColumns(sessionId);
  const metadataColumns = groupingColumns.map((c) => c.name);

  const handleRunCommunity = useCallback(async () => {
    clearResult();
    let response: AnalysisJobResponse;
    if (communityType === "alpha") {
      response = await runAnalysis("alpha-diversity", sessionId, {
        indices: alphaIndices,
        groupColumn: alphaGroup,
        testMethod: alphaTest,
      });
    } else {
      const betaParams = {
        distanceMethod: betaDistance,
        ordinationMethod: betaOrdination,
        groupColumn: betaGroup,
        testMethod: betaTest,
      };
      response = await runAnalysis(
        betaOrdination === "PCoA" ? "pcoa" : "nmds",
        sessionId,
        betaParams
      );
      if (betaTest === "PERMANOVA") {
        await runAnalysis("permanova", sessionId, betaParams);
      } else if (betaTest === "ANOSIM") {
        await runAnalysis("anosim", sessionId, betaParams);
      }
    }

    sessionStore.addAnalysisHistoryItem({
      id: response.job_id,
      type: communityType === "alpha" ? "Alpha Diversity" : "Beta Diversity",
      label: communityType === "alpha" ? alphaIndices.join(", ") : `${betaDistance} ${betaOrdination}`,
      timestamp: new Date().toISOString(),
      status: "success",
      plotData: response.plot_data,
      statistics: response.statistics,
      tableData: response.data,
      params: communityType === "alpha"
        ? { indices: alphaIndices, groupColumn: alphaGroup, testMethod: alphaTest }
        : { distanceMethod: betaDistance, ordinationMethod: betaOrdination, groupColumn: betaGroup, testMethod: betaTest },
    });
  }, [communityType, alphaIndices, alphaGroup, alphaTest, betaDistance, betaOrdination, betaGroup, betaTest, runAnalysis, sessionId, clearResult, sessionStore]);

  const handleRunDifferential = useCallback(async () => {
    clearResult();
    const params: DifferentialParams = {
      method: diffMethod,
      groupColumn: diffGroup,
      correctionMethod: diffCorrection,
      pValueThreshold: diffPvalue,
    };
    if (diffMethod === 'ANCOM-BC') {
      params.ancombcZeroCut = ancombcZeroCut;
      params.ancombcLibCut = ancombcLibCut;
      params.ancombcStrucZero = ancombcStrucZero;
      params.ancombcPAdjMethod = ancombcPAdjMethod;
    } else if (diffMethod === 'MaAsLin3') {
      params.maaslin3FixedEffects = maaslin3FixedEffects;
      params.maaslin3RandomEffects = maaslin3RandomEffects;
      params.maaslin3Normalization = maaslin3Normalization;
      params.maaslin3Transform = maaslin3Transform;
      params.maaslin3Reference = maaslin3Reference;
    } else if (diffMethod === 'lefse') {
      params.lefseLdaThreshold = lefseLdaThreshold;
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

  const handleRunCluster = useCallback(async () => {
    clearResult();
    let response: AnalysisJobResponse;
    if (clusterType === "heatmap") {
      response = await runAnalysis("heatmap", sessionId, {
        topN,
        clusterMethod,
      });
    } else {
      response = await runAnalysis("network", sessionId, {
        method: corrMethod,
        threshold: corrThreshold,
      });
    }

    sessionStore.addAnalysisHistoryItem({
      id: response.job_id,
      type: clusterType === "heatmap" ? "Heatmap" : "Network",
      label: clusterType === "heatmap" ? `Top ${topN}` : `${corrMethod} > ${corrThreshold}`,
      timestamp: new Date().toISOString(),
      status: "success",
      plotData: response.plot_data,
      statistics: response.statistics,
      tableData: response.data,
      params: clusterType === "heatmap" ? { topN, clusterMethod } : { correlationMethod: corrMethod, threshold: corrThreshold },
    });
  }, [clusterType, topN, clusterMethod, corrMethod, corrThreshold, runAnalysis, sessionId, clearResult, sessionStore]);

  const handleRunML = useCallback(async () => {
    clearResult();
    const response = await runAnalysis("random-forest", sessionId, {
      method: mlMethod,
      groupColumn: mlGroup,
      cvFolds: mlCV,
    });

    sessionStore.addAnalysisHistoryItem({
      id: response.job_id,
      type: "Machine Learning",
      label: `${mlMethod} (${mlCV})`,
      timestamp: new Date().toISOString(),
      status: "success",
      plotData: response.plot_data,
      statistics: response.statistics,
      tableData: response.data,
      params: { method: mlMethod, groupColumn: mlGroup, cvFolds: mlCV },
    });
  }, [mlMethod, mlGroup, mlCV, runAnalysis, sessionId, clearResult, sessionStore]);

  return (
    <div data-testid="analysis-species-page" className={cn("space-y-6")}>
      {!hasSession && <NoSessionBanner />}
      {analysisError && <StatusAlert status="error" title="Analysis failed" description={analysisError} />}
      <div>
        <h1 data-testid="analysis-title" className="text-2xl font-bold tracking-tight">Species Analysis</h1>
        <p className="text-muted-foreground">
          Perform statistical analysis at the species level
        </p>
      </div>

      <Tabs defaultValue="community" className="w-full">
        <TabsList className="grid grid-cols-5 w-full">
          <TabsTrigger data-testid="tab-community" value="community" className="gap-2">
            <Dna className="h-4 w-4" /> Community
          </TabsTrigger>
          <TabsTrigger data-testid="tab-differential" value="differential" className="gap-2">
            <BarChart3 className="h-4 w-4" /> Differential
          </TabsTrigger>
          <TabsTrigger data-testid="tab-cluster" value="cluster" className="gap-2">
            <Network className="h-4 w-4" /> Cluster & Network
          </TabsTrigger>
          <TabsTrigger data-testid="tab-ml" value="ml" className="gap-2">
            <BrainCircuit className="h-4 w-4" /> ML
          </TabsTrigger>
          <TabsTrigger data-testid="tab-function" value="function" className="gap-2">
            <FunctionSquare className="h-4 w-4" /> Function
          </TabsTrigger>
        </TabsList>

        <TabsContent value="community" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-1 space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Analysis Parameters</CardTitle>
                  <CardDescription>Configure community analysis</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <ParameterItem label="Analysis Type">
                    <RadioGroup
                      value={communityType}
                      onValueChange={(v) => setCommunityType(v as "alpha" | "beta")}
                      className="grid grid-cols-2 gap-2"
                    >
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="alpha" id="alpha" />
                        <Label htmlFor="alpha" className="cursor-pointer">Alpha Diversity</Label>
                      </div>
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="beta" id="beta" />
                        <Label htmlFor="beta" className="cursor-pointer">Beta Diversity</Label>
                      </div>
                    </RadioGroup>
                  </ParameterItem>

                  {communityType === "alpha" && (
                    <>
                      <ParameterItem label="Diversity Indices" tooltip="Select which diversity indices to calculate">
                        <div className="grid grid-cols-2 gap-2">
                          {["Shannon", "Simpson", "Chao1", "ACE", "Observed", "Pielou"].map((idx) => (
                            <div key={idx} className="flex items-center space-x-2">
                              <Checkbox
                                id={idx}
                                checked={alphaIndices.includes(idx)}
                                onCheckedChange={(checked) => {
                                  if (checked) setAlphaIndices([...alphaIndices, idx]);
                                  else setAlphaIndices(alphaIndices.filter((i) => i !== idx));
                                }}
                              />
                              <Label htmlFor={idx} className="cursor-pointer text-sm">{idx}</Label>
                            </div>
                          ))}
                        </div>
                      </ParameterItem>
                      <ParameterItem label="Group Column">
                        <Select value={alphaGroup} onValueChange={setAlphaGroup}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {metadataColumns.map((col) => (
                              <SelectItem key={col} value={col}>{col}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label="Statistical Test">
                        <Select value={alphaTest} onValueChange={setAlphaTest}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="t-test">t-test</SelectItem>
                            <SelectItem value="Wilcoxon">Wilcoxon</SelectItem>
                            <SelectItem value="Kruskal-Wallis">Kruskal-Wallis</SelectItem>
                            <SelectItem value="ANOVA">ANOVA</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                    </>
                  )}

                  {communityType === "beta" && (
                    <>
                      <ParameterItem label="Distance Algorithm">
                        <Select value={betaDistance} onValueChange={setBetaDistance}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="Bray-Curtis">Bray-Curtis</SelectItem>
                            <SelectItem value="Jaccard">Jaccard</SelectItem>
                            <SelectItem value="Euclidean">Euclidean</SelectItem>
                            <SelectItem value="Manhattan">Manhattan</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label="Ordination Method">
                        <Select value={betaOrdination} onValueChange={setBetaOrdination}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="PCoA">PCoA</SelectItem>
                            <SelectItem value="NMDS">NMDS</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label="Group Column">
                        <Select value={betaGroup} onValueChange={setBetaGroup}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {metadataColumns.map((col) => (
                              <SelectItem key={col} value={col}>{col}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label="Statistical Test">
                        <Select value={betaTest} onValueChange={setBetaTest}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="PERMANOVA">PERMANOVA</SelectItem>
                            <SelectItem value="ANOSIM">ANOSIM</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                    </>
                  )}
                </CardContent>
              </Card>
            </div>

            <div className="lg:col-span-2">
              <ResultSection
                title={communityType === "alpha" ? "Alpha Diversity Boxplot" : `${betaOrdination} Plot`}
                plotData={result?.plot_data}
                tableData={result?.data}
                stats={result?.statistics}
                isLoading={isLoading}
                onRun={handleRunCommunity}
              />
            </div>
          </div>
        </TabsContent>

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
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="t-test">t-test</SelectItem>
                        <SelectItem value="Wilcoxon">Wilcoxon</SelectItem>
                        <SelectItem value="ANOVA">ANOVA</SelectItem>
                        <SelectItem value="DESeq2">DESeq2</SelectItem>
                        <SelectItem value="edgeR">edgeR</SelectItem>
                        <SelectItem value="ANCOM-BC">ANCOM-BC (composition-aware)</SelectItem>
                        <SelectItem value="MaAsLin3">MaAsLin3 (multivariate)</SelectItem>
                        <SelectItem value="lefse">LEfSe (LDA Effect Size)</SelectItem>
                      </SelectContent>
                    </Select>
                  </ParameterItem>
                  <ParameterItem label="Group Column">
                    <Select value={diffGroup} onValueChange={setDiffGroup}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {metadataColumns.map((col) => (
                          <SelectItem key={col} value={col}>{col}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </ParameterItem>
                  <ParameterItem label="Contrast Groups">
                    <Select value={diffContrast} onValueChange={setDiffContrast}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Control vs Treatment">Control vs Treatment</SelectItem>
                        <SelectItem value="Group A vs Group B">Group A vs Group B</SelectItem>
                        <SelectItem value="Pre vs Post">Pre vs Post</SelectItem>
                      </SelectContent>
                    </Select>
                  </ParameterItem>
                  <ParameterItem label="Multiple Testing Correction">
                    <Select value={diffCorrection} onValueChange={setDiffCorrection}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="BH">Benjamini-Hochberg (BH)</SelectItem>
                        <SelectItem value="Bonferroni">Bonferroni</SelectItem>
                        <SelectItem value="None">None</SelectItem>
                      </SelectContent>
                    </Select>
                  </ParameterItem>
                  <ParameterItem label={`P-value Threshold (${diffPvalue.toFixed(3)})`}>
                    <Slider
                      value={[diffPvalue]}
                      onValueChange={(v) => setDiffPvalue(v[0])}
                      min={0.001}
                      max={0.1}
                      step={0.001}
                    />
                  </ParameterItem>
                  {diffMethod === 'ANCOM-BC' && (
                    <>
                      <ParameterItem label={`Zero Cutoff (${ancombcZeroCut.toFixed(2)})`}>
                        <Slider
                          value={[ancombcZeroCut]}
                          onValueChange={(v) => setAncombcZeroCut(v[0])}
                          min={0.5}
                          max={1.0}
                          step={0.01}
                        />
                      </ParameterItem>
                      <ParameterItem label={`Library Cutoff (${ancombcLibCut})`}>
                        <Slider
                          value={[ancombcLibCut]}
                          onValueChange={(v) => setAncombcLibCut(v[0])}
                          min={0}
                          max={100}
                          step={5}
                        />
                      </ParameterItem>
                      <ParameterItem label="Structural Zero Detection">
                        <div className="flex items-center space-x-2">
                          <Checkbox
                            id="struc-zero"
                            checked={ancombcStrucZero}
                            onCheckedChange={(checked) => setAncombcStrucZero(checked === true)}
                          />
                          <Label htmlFor="struc-zero" className="cursor-pointer text-sm">Enable structural zero detection</Label>
                        </div>
                      </ParameterItem>
                      <ParameterItem label="P-value Adjustment">
                        <Select value={ancombcPAdjMethod} onValueChange={setAncombcPAdjMethod}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="holm">holm</SelectItem>
                            <SelectItem value="hochberg">hochberg</SelectItem>
                            <SelectItem value="hommel">hommel</SelectItem>
                            <SelectItem value="bonferroni">bonferroni</SelectItem>
                            <SelectItem value="BH">BH</SelectItem>
                            <SelectItem value="BY">BY</SelectItem>
                            <SelectItem value="fdr">fdr</SelectItem>
                            <SelectItem value="none">none</SelectItem>
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
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
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
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="LOG">LOG</SelectItem>
                            <SelectItem value="AST">AST</SelectItem>
                            <SelectItem value="NONE">NONE</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label="Reference Level">
                        <Select value={maaslin3Reference} onValueChange={setMaaslin3Reference}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value={diffContrast.split(' vs ')[0]}>{diffContrast.split(' vs ')[0]}</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                    </>
                  )}
                  {diffMethod === 'lefse' && (
                    <>
                      <ParameterItem label={`LDA Threshold (${lefseLdaThreshold.toFixed(1)})`} tooltip="LDA score threshold for identifying differentially abundant features">
                        <Slider
                          value={[lefseLdaThreshold]}
                          onValueChange={(v) => setLefseLdaThreshold(v[0])}
                          min={1.0}
                          max={4.0}
                          step={0.1}
                        />
                      </ParameterItem>
                      <div className="p-3 bg-blue-50 rounded-lg text-xs text-blue-700">
                        LEfSe performs LDA analysis on features significantly different between groups (Kruskal-Wallis p &lt; 0.05)
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>
            </div>
            <div className="lg:col-span-2">
              <ResultSection
                title={diffMethod === 'MaAsLin3' ? "MaAsLin3 Association Plot" : "Volcano Plot"}
                plotData={result?.plot_data}
                tableData={result?.data}
                stats={result?.statistics}
                isLoading={isLoading}
                onRun={handleRunDifferential}
              />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="cluster" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-1 space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Clustering Parameters</CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  <ParameterItem label="Analysis Type">
                    <RadioGroup
                      value={clusterType}
                      onValueChange={(v) => setClusterType(v as "heatmap" | "network")}
                      className="grid grid-cols-2 gap-2"
                    >
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="heatmap" id="heatmap" />
                        <Label htmlFor="heatmap" className="cursor-pointer">Heatmap</Label>
                      </div>
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="network" id="network" />
                        <Label htmlFor="network" className="cursor-pointer">Network</Label>
                      </div>
                    </RadioGroup>
                  </ParameterItem>

                  {clusterType === "heatmap" && (
                    <>
                      <ParameterItem label={`Top N Features (${topN})`}>
                        <Slider
                          value={[topN]}
                          onValueChange={(v) => setTopN(v[0])}
                          min={20}
                          max={200}
                          step={10}
                        />
                      </ParameterItem>
                      <ParameterItem label="Clustering Method">
                        <Select value={clusterMethod} onValueChange={setClusterMethod}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="complete">Complete</SelectItem>
                            <SelectItem value="single">Single</SelectItem>
                            <SelectItem value="average">Average</SelectItem>
                            <SelectItem value="ward">Ward</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                    </>
                  )}

                  {clusterType === "network" && (
                    <>
                      <ParameterItem label="Correlation Method">
                        <Select value={corrMethod} onValueChange={setCorrMethod}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="Pearson">Pearson</SelectItem>
                            <SelectItem value="Spearman">Spearman</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label={`Correlation Threshold (${corrThreshold.toFixed(2)})`}>
                        <Slider
                          value={[corrThreshold]}
                          onValueChange={(v) => setCorrThreshold(v[0])}
                          min={0.1}
                          max={0.5}
                          step={0.05}
                        />
                      </ParameterItem>
                    </>
                  )}
                </CardContent>
              </Card>
            </div>
            <div className="lg:col-span-2">
              <ResultSection
                title={clusterType === "heatmap" ? "Heatmap" : "Correlation Network"}
                plotData={result?.plot_data}
                tableData={result?.data}
                stats={result?.statistics}
                isLoading={isLoading}
                onRun={handleRunCluster}
              />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="ml" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-1 space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Machine Learning Parameters</CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  <ParameterItem label="Method">
                    <Select value={mlMethod} onValueChange={setMlMethod}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Random Forest">Random Forest</SelectItem>
                      </SelectContent>
                    </Select>
                  </ParameterItem>
                  <ParameterItem label="Group Column">
                    <Select value={mlGroup} onValueChange={setMlGroup}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {metadataColumns.map((col) => (
                          <SelectItem key={col} value={col}>{col}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </ParameterItem>
                  <ParameterItem label="Cross-Validation">
                    <Select value={mlCV} onValueChange={setMlCV}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="3-fold">3-fold</SelectItem>
                        <SelectItem value="5-fold">5-fold</SelectItem>
                        <SelectItem value="10-fold">10-fold</SelectItem>
                      </SelectContent>
                    </Select>
                  </ParameterItem>
                </CardContent>
              </Card>
            </div>
            <div className="lg:col-span-2">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <Button onClick={handleRunML} disabled={isLoading} className="gap-2">
                    {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                    {isLoading ? "Running..." : "Run Analysis"}
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

                {result && !isLoading && mlMethod === "Random Forest" && (
                  <>
                    <div className="mb-4 p-3 bg-green-50 rounded-lg">
                      <p className="text-sm font-semibold text-green-700">
                        Random Forest Classification Results
                      </p>
                      <p className="text-xs text-green-600">
                        Accuracy: {result.statistics?.accuracy !== undefined ? ((result.statistics.accuracy as number) * 100).toFixed(1) : 'N/A'}%
                      </p>
                      <p className="text-xs text-green-600">
                        Cross-validation: {String(result.statistics?.cv_method || '5-fold')}
                      </p>
                    </div>
                    
                    {/* Feature Importance Chart */}
                    {result.plot_data && (
                      <Card>
                        <CardHeader className="pb-2">
                          <div className="flex items-center justify-between">
                            <CardTitle className="text-lg">Top Feature Importance</CardTitle>
                            <div className="flex gap-2">
                              <Button variant="outline" size="sm" className="gap-1" onClick={() => downloadFigure(result.plot_data!, 'png')}>
                                <ImageIcon className="h-3.5 w-3.5" /> PNG
                              </Button>
                              <Button variant="outline" size="sm" className="gap-1" onClick={() => downloadFigure(result.plot_data!, 'svg')}>
                                <ImageIcon className="h-3.5 w-3.5" /> SVG
                              </Button>
                            </div>
                          </div>
                        </CardHeader>
                        <CardContent>
                          <div className="h-[400px] w-full">
                            <PlotlyChart figure={result.plot_data} className="h-full" />
                          </div>
                        </CardContent>
                      </Card>
                    )}
                    
                    {/* Confusion Matrix */}
                    {result.statistics?.confusion_matrix_plot && (
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-lg">Confusion Matrix</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="h-[400px] w-full">
                            <PlotlyChart figure={result.statistics.confusion_matrix_plot as PlotlyFigure} className="h-full" />
                          </div>
                        </CardContent>
                      </Card>
                    )}
                    
                    {/* Feature Importance Table */}
                    {result.data && result.data.length > 0 && (
                      <Card>
                        <CardHeader className="pb-2">
                          <div className="flex items-center justify-between">
                            <CardTitle className="text-lg">Feature Importance Table</CardTitle>
                            <div className="flex gap-2">
                              <Button variant="outline" size="sm" className="gap-1" onClick={() => downloadCSV(result.data!, 'feature_importance.csv')}>
                                <FileSpreadsheet className="h-3.5 w-3.5" /> CSV
                              </Button>
                              <Button variant="outline" size="sm" className="gap-1" onClick={() => downloadPDF(result.plot_data, result.data || [], 'rf_analysis.pdf')}>
                                <FileText className="h-3.5 w-3.5" /> PDF
                              </Button>
                            </div>
                          </div>
                        </CardHeader>
                        <CardContent>
                          <div className="overflow-auto max-h-64">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="border-b">
                                  {Object.keys(result.data[0]).map((col) => (
                                    <th key={col} className="text-left px-3 py-2 font-medium text-muted-foreground">{col}</th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {result.data.slice(0, 20).map((row, i) => (
                                  <tr key={i} className="border-b last:border-0 hover:bg-muted/50">
                                    {Object.values(row).map((val, j) => (
                                      <td key={j} className="px-3 py-2 font-mono text-xs">{String(val)}</td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                            {result.data.length > 20 && (
                              <p className="text-xs text-muted-foreground mt-2 text-center">Showing 20 of {result.data.length} rows</p>
                            )}
                          </div>
                        </CardContent>
                      </Card>
                    )}
                  </>
                )}

                {result && !isLoading && mlMethod !== "Random Forest" && (
                  <ResultSection
                    title="Feature Importance"
                    plotData={result?.plot_data}
                    tableData={result?.data}
                    stats={result?.statistics}
                    isLoading={isLoading}
                    onRun={handleRunML}
                  />
                )}
              </div>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="function" className="space-y-4 mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Function Prediction</CardTitle>
              <CardDescription>
                Function prediction analysis is coming soon. This will include PICRUSt2, Tax4Fun, and FAPROTAX functional profiling.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-center h-48 text-muted-foreground">
                <div className="text-center">
                  <FunctionSquare className="h-12 w-12 mx-auto mb-2 opacity-50" />
                  <p>Function prediction module will be available in a future update.</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
