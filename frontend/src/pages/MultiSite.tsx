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
  Globe,
  MapPin,
  Clock,
  GitMerge,
  BarChart3,
  Play,
  Image as ImageIcon,
  FileSpreadsheet,
  Loader2,
  HelpCircle,
  FileText,
  Upload,
  Database,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";

const siteOptions = ["Oral", "Gut", "Skin", "Nasal", "Vaginal"];

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

export function MultiSite() {
  const sessionStore = useSessionStore();
  const setCurrentStep = useSessionStore((state) => state.setCurrentStep);
  const { runAnalysis, isLoading, result, clearResult } = useAnalysis();

  useEffect(() => {
    setCurrentStep("multi-site");
  }, [setCurrentStep]);

  // Data mapping state
  const [siteColumn, setSiteColumn] = useState("Site");
  const [subjectColumn, setSubjectColumn] = useState("Subject");
  const [timeColumn, setTimeColumn] = useState("Visit");
  const [referenceSite, setReferenceSite] = useState("Oral");

  // Tab 1: Cross-Site Comparison state
  const [comparisonType, setComparisonType] = useState<"pcoa" | "permanova" | "pairwise">("pcoa");
  const [comparisonDistance, setComparisonDistance] = useState("Bray-Curtis");
  const [comparisonShapeBy, setComparisonShapeBy] = useState("Site");

  // Tab 2: Site-Specific Markers state
  const [markerMethod, setMarkerMethod] = useState("Wilcoxon");
  const [markerComparison, setMarkerComparison] = useState("Each vs Reference");
  const [markerPvalue, setMarkerPvalue] = useState(0.05);
  const [markerCorrection, setMarkerCorrection] = useState("BH");
  const [showVenn, setShowVenn] = useState(true);

  // Tab 3: Temporal/Progression Analysis state
  const [temporalType, setTemporalType] = useState<"trajectory" | "anova" | "trend">("trajectory");
  const [temporalDistance, setTemporalDistance] = useState("Bray-Curtis");

  // Tab 4: Cross-Site Network state
  const [networkType, setNetworkType] = useState<"compare" | "shared" | "hubs">("compare");
  const [networkCorrMethod, setNetworkCorrMethod] = useState("Spearman");
  const [networkThreshold, setNetworkThreshold] = useState(0.3);

  const { sessionId, hasSession } = useRequiredSession();
  // Grouping variables come from the uploaded metadata, not a fixed list.
  const { groupingColumns } = useMetadataColumns(sessionId);
  const metadataColumns = groupingColumns.map((c) => c.name);

  const handleRunComparison = useCallback(async () => {
    clearResult();
    let response: AnalysisJobResponse;

    if (comparisonType === "pcoa") {
      response = await runAnalysis("multisite-pcoa", sessionId, {
        distance_metric: comparisonDistance === "Bray-Curtis" ? "braycurtis" : comparisonDistance.toLowerCase(),
        site_column: siteColumn,
        group_column: comparisonShapeBy,
        subject_column: subjectColumn,
        connect_subjects: false,
      });
    } else if (comparisonType === "permanova") {
      response = await runAnalysis("multisite-permanova", sessionId, {
        distance_metric: comparisonDistance === "Bray-Curtis" ? "braycurtis" : comparisonDistance.toLowerCase(),
        site_column: siteColumn,
        group_column: comparisonShapeBy,
        permutations: 999,
      });
    } else {
      // pairwise beta-diversity - use pcoa for visualization
      response = await runAnalysis("multisite-pcoa", sessionId, {
        distance_metric: comparisonDistance === "Bray-Curtis" ? "braycurtis" : comparisonDistance.toLowerCase(),
        site_column: siteColumn,
        group_column: comparisonShapeBy,
        subject_column: subjectColumn,
        connect_subjects: false,
      });
    }

    sessionStore.addAnalysisHistoryItem({
      id: response.job_id,
      type: "Cross-Site Comparison",
      label: `${comparisonType} (${comparisonDistance})`,
      timestamp: new Date().toISOString(),
      status: "success",
      plotData: response.plot_data,
      statistics: response.statistics,
      tableData: response.data,
      params: {
        comparisonType,
        distanceMethod: comparisonDistance,
        siteColumn,
        shapeBy: comparisonShapeBy,
      },
    });
  }, [comparisonType, comparisonDistance, comparisonShapeBy, siteColumn, subjectColumn, runAnalysis, sessionId, clearResult, sessionStore]);

  const handleRunMarkers = useCallback(async () => {
    clearResult();
    const response = await runAnalysis("multisite-markers", sessionId, {
      site_column: siteColumn,
      reference_site: referenceSite,
      subject_column: subjectColumn,
      pvalue_threshold: markerPvalue,
      fc_threshold: 1.5,
    });

    sessionStore.addAnalysisHistoryItem({
      id: response.job_id,
      type: "Site-Specific Markers",
      label: markerMethod,
      timestamp: new Date().toISOString(),
      status: "success",
      plotData: response.plot_data,
      statistics: response.statistics,
      tableData: response.data,
      params: {
        method: markerMethod,
        siteColumn,
        referenceSite,
        comparisonMode: markerComparison,
        pValueThreshold: markerPvalue,
        correctionMethod: markerCorrection,
      },
    });
  }, [markerMethod, siteColumn, subjectColumn, referenceSite, markerComparison, markerPvalue, markerCorrection, runAnalysis, sessionId, clearResult, sessionStore]);

  const handleRunTemporal = useCallback(async () => {
    clearResult();
    let response: AnalysisJobResponse;

    if (temporalType === "trajectory") {
      response = await runAnalysis("multisite-temporal", sessionId, {
        distance_metric: temporalDistance === "Bray-Curtis" ? "braycurtis" : temporalDistance.toLowerCase(),
        subject_column: subjectColumn,
        time_column: timeColumn,
        site_column: siteColumn,
      });
    } else if (temporalType === "anova") {
      response = await runAnalysis("multisite-permanova", sessionId, {
        distance_metric: temporalDistance === "Bray-Curtis" ? "braycurtis" : temporalDistance.toLowerCase(),
        site_column: siteColumn,
        group_column: timeColumn,
        permutations: 999,
      });
    } else {
      response = await runAnalysis("multisite-temporal", sessionId, {
        distance_metric: temporalDistance === "Bray-Curtis" ? "braycurtis" : temporalDistance.toLowerCase(),
        subject_column: subjectColumn,
        time_column: timeColumn,
        site_column: siteColumn,
      });
    }

    sessionStore.addAnalysisHistoryItem({
      id: response.job_id,
      type: "Temporal Analysis",
      label: temporalType,
      timestamp: new Date().toISOString(),
      status: "success",
      plotData: response.plot_data,
      statistics: response.statistics,
      tableData: response.data,
      params: {
        temporalType,
        distanceMethod: temporalDistance,
        subjectColumn,
        timeColumn,
        siteColumn,
      },
    });
  }, [temporalType, temporalDistance, subjectColumn, timeColumn, siteColumn, runAnalysis, sessionId, clearResult, sessionStore]);

  const handleRunNetwork = useCallback(async () => {
    clearResult();
    let response: AnalysisJobResponse;

    if (networkType === "compare" || networkType === "shared" || networkType === "hubs") {
      response = await runAnalysis("multisite-network-compare", sessionId, {
        site_column: siteColumn,
        threshold: networkThreshold,
      });
    } else {
      response = await runAnalysis("multisite-network-compare", sessionId, {
        site_column: siteColumn,
        threshold: networkThreshold,
      });
    }

    sessionStore.addAnalysisHistoryItem({
      id: response.job_id,
      type: "Cross-Site Network",
      label: networkType,
      timestamp: new Date().toISOString(),
      status: "success",
      plotData: response.plot_data,
      statistics: response.statistics,
      tableData: response.data,
      params: {
        networkType,
        correlationMethod: networkCorrMethod,
        threshold: networkThreshold,
        siteColumn,
      },
    });
  }, [networkType, networkCorrMethod, networkThreshold, siteColumn, runAnalysis, sessionId, clearResult, sessionStore]);

  return (
    <div data-testid="multi-site-page" className={cn("space-y-6")}>
      {!hasSession && <NoSessionBanner />}
      <div>
        <h1 data-testid="multi-site-title" className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Globe className="h-6 w-6" /> Multi-Site Integration
        </h1>
        <p className="text-muted-foreground">
          Analyze microbiome data across multiple study sites, body sites, time points, or disease cohorts
        </p>
      </div>

      {/* Data Configuration Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Database className="h-5 w-5" /> Data Configuration
          </CardTitle>
          <CardDescription>
            Map your metadata columns for multi-site analysis. Upload either multiple tables (one per site) or a single merged table with a Site column.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <ParameterItem label="Site Column" tooltip="Column identifying site/cohort/body site">
              <Select value={siteColumn} onValueChange={setSiteColumn}>
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

            <ParameterItem label="Subject Column" tooltip="Column identifying individual subjects">
              <Select value={subjectColumn} onValueChange={setSubjectColumn}>
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

            <ParameterItem label="Time/Visit Column" tooltip="Column for longitudinal timepoints (optional)">
              <Select value={timeColumn} onValueChange={setTimeColumn}>
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

            <ParameterItem label="Reference Site" tooltip="Reference site for differential comparisons">
              <Select value={referenceSite} onValueChange={setReferenceSite}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {siteOptions.map((site) => (
                    <SelectItem key={site} value={site}>{site}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </ParameterItem>
          </div>

          {/* Upload Area */}
          <div className="mt-6 p-6 border-2 border-dashed border-border rounded-lg bg-muted/30">
            <div className="flex flex-col items-center gap-3 text-center">
              <Upload className="h-8 w-8 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">Upload Multi-Site Data</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Upload multiple microbiome tables (one per site) or a single merged table with a Site column
                </p>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" className="gap-1">
                  <Database className="h-3.5 w-3.5" /> Upload Tables
                </Button>
                <Button variant="outline" size="sm" className="gap-1">
                  <Users className="h-3.5 w-3.5" /> Upload Metadata
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="comparison" className="w-full">
        <TabsList className="grid grid-cols-4 w-full">
          <TabsTrigger data-testid="tab-comparison" value="comparison" className="gap-2">
            <MapPin className="h-4 w-4" /> Cross-Site Comparison
          </TabsTrigger>
          <TabsTrigger data-testid="tab-markers" value="markers" className="gap-2">
            <BarChart3 className="h-4 w-4" /> Site-Specific Markers
          </TabsTrigger>
          <TabsTrigger data-testid="tab-temporal" value="temporal" className="gap-2">
            <Clock className="h-4 w-4" /> Temporal / Progression
          </TabsTrigger>
          <TabsTrigger data-testid="tab-network" value="network" className="gap-2">
            <GitMerge className="h-4 w-4" /> Cross-Site Network
          </TabsTrigger>
        </TabsList>

        {/* Tab 1: Cross-Site Comparison */}
        <TabsContent value="comparison" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-1 space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Comparison Parameters</CardTitle>
                  <CardDescription>Configure cross-site comparison</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <ParameterItem label="Analysis Type">
                    <RadioGroup
                      value={comparisonType}
                      onValueChange={(v) => setComparisonType(v as "pcoa" | "permanova" | "pairwise")}
                      className="grid grid-cols-1 gap-2"
                    >
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="pcoa" id="pcoa" />
                        <Label htmlFor="pcoa" className="cursor-pointer">Multi-Site PCoA</Label>
                      </div>
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="permanova" id="permanova" />
                        <Label htmlFor="permanova" className="cursor-pointer">PERMANOVA (Site Effect)</Label>
                      </div>
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="pairwise" id="pairwise" />
                        <Label htmlFor="pairwise" className="cursor-pointer">Pairwise Beta-Diversity</Label>
                      </div>
                    </RadioGroup>
                  </ParameterItem>

                  <ParameterItem label="Distance Algorithm">
                    <Select value={comparisonDistance} onValueChange={setComparisonDistance}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Bray-Curtis">Bray-Curtis</SelectItem>
                        <SelectItem value="Jaccard">Jaccard</SelectItem>
                        <SelectItem value="Euclidean">Euclidean</SelectItem>
                        <SelectItem value="Aitchison">Aitchison</SelectItem>
                      </SelectContent>
                    </Select>
                  </ParameterItem>

                  <ParameterItem label="Shape By" tooltip="Additional grouping for point shapes">
                    <Select value={comparisonShapeBy} onValueChange={setComparisonShapeBy}>
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
                </CardContent>
              </Card>
            </div>

            <div className="lg:col-span-2">
              <ResultSection
                title={
                  comparisonType === "pcoa"
                    ? "Multi-Site PCoA"
                    : comparisonType === "permanova"
                    ? "PERMANOVA Results"
                    : "Pairwise Beta-Diversity"
                }
                plotData={result?.plot_data}
                tableData={result?.data}
                stats={result?.statistics}
                isLoading={isLoading}
                onRun={handleRunComparison}
              />
            </div>
          </div>
        </TabsContent>

        {/* Tab 2: Site-Specific Markers */}
        <TabsContent value="markers" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-1 space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Marker Discovery Parameters</CardTitle>
                  <CardDescription>Configure site-specific biomarker analysis</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <ParameterItem label="Differential Method">
                    <Select value={markerMethod} onValueChange={setMarkerMethod}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Wilcoxon">Wilcoxon</SelectItem>
                        <SelectItem value="t-test">t-test</SelectItem>
                        <SelectItem value="ANOVA">ANOVA</SelectItem>
                        <SelectItem value="ANCOM-BC">ANCOM-BC</SelectItem>
                        <SelectItem value="lefse">LEfSe</SelectItem>
                      </SelectContent>
                    </Select>
                  </ParameterItem>

                  <ParameterItem label="Comparison Mode">
                    <Select value={markerComparison} onValueChange={setMarkerComparison}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Each vs Reference">Each Site vs Reference</SelectItem>
                        <SelectItem value="All Pairwise">All Pairwise</SelectItem>
                        <SelectItem value="One-vs-Rest">One-vs-Rest</SelectItem>
                      </SelectContent>
                    </Select>
                  </ParameterItem>

                  <ParameterItem label="Reference Site">
                    <Select value={referenceSite} onValueChange={setReferenceSite}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {siteOptions.map((site) => (
                          <SelectItem key={site} value={site}>{site}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </ParameterItem>

                  <ParameterItem label={`P-value Threshold (${markerPvalue.toFixed(3)})`}>
                    <Slider
                      value={[markerPvalue]}
                      onValueChange={(v) => setMarkerPvalue(v[0])}
                      min={0.001}
                      max={0.1}
                      step={0.001}
                    />
                  </ParameterItem>

                  <ParameterItem label="Multiple Testing Correction">
                    <Select value={markerCorrection} onValueChange={setMarkerCorrection}>
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

                  <ParameterItem label="Show Marker Overlap">
                    <div className="flex items-center space-x-2">
                      <Checkbox
                        id="show-venn"
                        checked={showVenn}
                        onCheckedChange={(checked) => setShowVenn(checked === true)}
                      />
                      <Label htmlFor="show-venn" className="cursor-pointer text-sm">Display Venn-style overlap</Label>
                    </div>
                  </ParameterItem>
                </CardContent>
              </Card>
            </div>

            <div className="lg:col-span-2">
              <ResultSection
                title="Site-Specific Markers"
                plotData={result?.plot_data}
                tableData={result?.data}
                stats={result?.statistics}
                isLoading={isLoading}
                onRun={handleRunMarkers}
              />
            </div>
          </div>
        </TabsContent>

        {/* Tab 3: Temporal/Progression Analysis */}
        <TabsContent value="temporal" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-1 space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Temporal Analysis Parameters</CardTitle>
                  <CardDescription>Configure longitudinal or progression analysis</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <ParameterItem label="Analysis Type">
                    <RadioGroup
                      value={temporalType}
                      onValueChange={(v) => setTemporalType(v as "trajectory" | "anova" | "trend")}
                      className="grid grid-cols-1 gap-2"
                    >
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="trajectory" id="trajectory" />
                        <Label htmlFor="trajectory" className="cursor-pointer">Longitudinal Trajectory</Label>
                      </div>
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="anova" id="anova" />
                        <Label htmlFor="anova" className="cursor-pointer">Repeated Measures ANOVA</Label>
                      </div>
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="trend" id="trend" />
                        <Label htmlFor="trend" className="cursor-pointer">Trend Analysis</Label>
                      </div>
                    </RadioGroup>
                  </ParameterItem>

                  {temporalType === "trajectory" && (
                    <ParameterItem label="Distance Algorithm">
                      <Select value={temporalDistance} onValueChange={setTemporalDistance}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="Bray-Curtis">Bray-Curtis</SelectItem>
                          <SelectItem value="Jaccard">Jaccard</SelectItem>
                          <SelectItem value="Euclidean">Euclidean</SelectItem>
                          <SelectItem value="Aitchison">Aitchison</SelectItem>
                        </SelectContent>
                      </Select>
                    </ParameterItem>
                  )}

                  <ParameterItem label="Subject Column">
                    <Select value={subjectColumn} onValueChange={setSubjectColumn}>
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

                  <ParameterItem label="Time/Visit Column">
                    <Select value={timeColumn} onValueChange={setTimeColumn}>
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
                </CardContent>
              </Card>
            </div>

            <div className="lg:col-span-2">
              <ResultSection
                title={
                  temporalType === "trajectory"
                    ? "Longitudinal Trajectory"
                    : temporalType === "anova"
                    ? "Repeated Measures ANOVA"
                    : "Trend Analysis"
                }
                plotData={result?.plot_data}
                tableData={result?.data}
                stats={result?.statistics}
                isLoading={isLoading}
                onRun={handleRunTemporal}
              />
            </div>
          </div>
        </TabsContent>

        {/* Tab 4: Cross-Site Network */}
        <TabsContent value="network" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-1 space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Network Parameters</CardTitle>
                  <CardDescription>Configure cross-site network analysis</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <ParameterItem label="Analysis Type">
                    <RadioGroup
                      value={networkType}
                      onValueChange={(v) => setNetworkType(v as "compare" | "shared" | "hubs")}
                      className="grid grid-cols-1 gap-2"
                    >
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="compare" id="compare" />
                        <Label htmlFor="compare" className="cursor-pointer">Network Comparison</Label>
                      </div>
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="shared" id="shared" />
                        <Label htmlFor="shared" className="cursor-pointer">Shared vs Unique Edges</Label>
                      </div>
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="hubs" id="hubs" />
                        <Label htmlFor="hubs" className="cursor-pointer">Hub Taxa Across Sites</Label>
                      </div>
                    </RadioGroup>
                  </ParameterItem>

                  <ParameterItem label="Correlation Method">
                    <Select value={networkCorrMethod} onValueChange={setNetworkCorrMethod}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Pearson">Pearson</SelectItem>
                        <SelectItem value="Spearman">Spearman</SelectItem>
                        <SelectItem value="SparCC">SparCC (compositional)</SelectItem>
                      </SelectContent>
                    </Select>
                  </ParameterItem>

                  <ParameterItem label={`Correlation Threshold (${networkThreshold.toFixed(2)})`}>
                    <Slider
                      value={[networkThreshold]}
                      onValueChange={(v) => setNetworkThreshold(v[0])}
                      min={0.1}
                      max={0.5}
                      step={0.05}
                    />
                  </ParameterItem>
                </CardContent>
              </Card>
            </div>

            <div className="lg:col-span-2">
              <ResultSection
                title={
                  networkType === "compare"
                    ? "Cross-Site Network Comparison"
                    : networkType === "shared"
                    ? "Shared vs Unique Edges"
                    : "Hub Taxa Across Sites"
                }
                plotData={result?.plot_data}
                tableData={result?.data}
                stats={result?.statistics}
                isLoading={isLoading}
                onRun={handleRunNetwork}
              />
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
