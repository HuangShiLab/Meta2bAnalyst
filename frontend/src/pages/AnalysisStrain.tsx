import { useState, useCallback, useEffect } from "react";
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
import { downloadFigure, downloadCSV } from "@/utils/api";
import type { AnalysisJobResponse } from "@/types";
import {
  Layers,
  BarChart3,
  GitBranch,
  Network,
  Play,
  Image as ImageIcon,
  FileSpreadsheet,
  Loader2,
  HelpCircle,
  Microscope,
  Search,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";

const mockSpecies = [
  "All Species",
  "Escherichia coli",
  "Bacteroides fragilis",
  "Lactobacillus rhamnosus",
  "Staphylococcus aureus",
  "Streptococcus pneumoniae",
  "Clostridioides difficile",
  "Helicobacter pylori",
  "Salmonella enterica",
  "Pseudomonas aeruginosa",
  "Vibrio cholerae",
];

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
  plotData?: { data?: unknown[]; layout?: Record<string, unknown> };
  tableData?: Record<string, string | number>[];
  stats?: Record<string, unknown>;
  isLoading: boolean;
  onRun: () => void;
  runLabel?: string;
}) {
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

      <div className="space-y-4">
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
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="h-[400px] w-full">
                <PlotlyChart
                  figure={{
                    data: (plotData.data || []) as never[],
                    layout: plotData.layout || {},
                  }}
                  className="h-full"
                />
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

export function AnalysisStrain() {
  const sessionStore = useSessionStore();
  const setCurrentStep = useSessionStore((state) => state.setCurrentStep);
  const { runAnalysis, isLoading, result, clearResult, error: analysisError } = useAnalysis();

  useEffect(() => {
    setCurrentStep("microbiome");
  }, [setCurrentStep]);

  const [selectedSpecies, setSelectedSpecies] = useState("All Species");
  const [speciesSearch, setSpeciesSearch] = useState("");

  // Composition tab state
  const [compType, setCompType] = useState<"stacked" | "heatmap">("stacked");
  const [compGroup, setCompGroup] = useState("Treatment");

  // Diversity tab state
  const [strainDivType, setStrainDivType] = useState<"alpha" | "beta">("alpha");
  const [strainIndices, setStrainIndices] = useState<string[]>(["Shannon", "Simpson"]);
  const [strainDistance, setStrainDistance] = useState("Bray-Curtis");
  const [strainOrdination, setStrainOrdination] = useState("PCoA");
  const [strainDivGroup, setStrainDivGroup] = useState("Treatment");

  // Differential tab state
  const [diffScope, setDiffScope] = useState<"within-species" | "cross-species">("within-species");
  const [diffMethod, setDiffMethod] = useState("Wilcoxon");
  const [diffGroup, setDiffGroup] = useState("Treatment");

  // Network tab state
  const [networkSpeciesScope, setNetworkSpeciesScope] = useState("current");
  const [networkCorrMethod, setNetworkCorrMethod] = useState("Spearman");
  const [networkCorrThreshold, setNetworkCorrThreshold] = useState(0.3);
  const [networkPvalueThreshold, setNetworkPvalueThreshold] = useState(0.05);

  const { sessionId, hasSession } = useRequiredSession();
  // Grouping variables come from the uploaded metadata, not a fixed list.
  const { groupingColumns } = useMetadataColumns(sessionId);
  const metadataColumns = groupingColumns.map((c) => c.name);

  const filteredSpecies = mockSpecies.filter((s) =>
    s.toLowerCase().includes(speciesSearch.toLowerCase())
  );

  const handleRunComposition = useCallback(async () => {
    clearResult();
    const response = await runAnalysis("strain-composition", sessionId, {
      visualizationType: compType,
      groupColumn: compGroup,
    });

    sessionStore.addAnalysisHistoryItem({
      id: response.job_id,
      type: "Strain Composition",
      label: `${compType} - ${selectedSpecies}`,
      timestamp: new Date().toISOString(),
      status: "success",
      plotData: response.plot_data,
      statistics: response.statistics,
      tableData: response.data,
      params: { visualizationType: compType, groupColumn: compGroup },
    });
  }, [compType, compGroup, runAnalysis, sessionId, clearResult, sessionStore, selectedSpecies]);

  const handleRunDiversity = useCallback(async () => {
    clearResult();
    let response: AnalysisJobResponse;
    if (strainDivType === "alpha") {
      response = await runAnalysis("strain-alpha", sessionId, {
        analysisType: "alpha",
        indices: strainIndices,
        groupColumn: strainDivGroup,
      });
    } else {
      response = await runAnalysis("strain-beta", sessionId, {
        analysisType: "beta",
        distanceMethod: strainDistance,
        ordinationMethod: strainOrdination,
        groupColumn: strainDivGroup,
      });
    }

    sessionStore.addAnalysisHistoryItem({
      id: response.job_id,
      type: strainDivType === "alpha" ? "Strain Alpha" : "Strain Beta",
      label: `${strainDivType} - ${selectedSpecies}`,
      timestamp: new Date().toISOString(),
      status: "success",
      plotData: response.plot_data,
      statistics: response.statistics,
      tableData: response.data,
      params: strainDivType === "alpha"
        ? { indices: strainIndices, groupColumn: strainDivGroup }
        : { distanceMethod: strainDistance, ordinationMethod: strainOrdination, groupColumn: strainDivGroup },
    });
  }, [strainDivType, strainIndices, strainDistance, strainOrdination, strainDivGroup, runAnalysis, sessionId, clearResult, sessionStore, selectedSpecies]);

  const handleRunDifferential = useCallback(async () => {
    clearResult();
    const response = await runAnalysis("strain-differential", sessionId, {
      scope: diffScope,
      method: diffMethod,
      groupColumn: diffGroup,
    });

    sessionStore.addAnalysisHistoryItem({
      id: response.job_id,
      type: "Strain Differential",
      label: `${diffScope} - ${selectedSpecies}`,
      timestamp: new Date().toISOString(),
      status: "success",
      plotData: response.plot_data,
      statistics: response.statistics,
      tableData: response.data,
      params: { scope: diffScope, method: diffMethod, groupColumn: diffGroup },
    });
  }, [diffScope, diffMethod, diffGroup, runAnalysis, sessionId, clearResult, sessionStore, selectedSpecies]);

  const handleRunNetwork = useCallback(async () => {
    clearResult();
    const response = await runAnalysis("strain-replacement", sessionId, {
      speciesScope: networkSpeciesScope,
      correlationMethod: networkCorrMethod,
      correlationThreshold: networkCorrThreshold,
      pValueThreshold: networkPvalueThreshold,
    });

    sessionStore.addAnalysisHistoryItem({
      id: response.job_id,
      type: "Strain Network",
      label: `${networkCorrMethod} r>${networkCorrThreshold} - ${selectedSpecies}`,
      timestamp: new Date().toISOString(),
      status: "success",
      plotData: response.plot_data,
      statistics: response.statistics,
      tableData: response.data,
      params: {
        speciesScope: networkSpeciesScope,
        correlationMethod: networkCorrMethod,
        correlationThreshold: networkCorrThreshold,
        pValueThreshold: networkPvalueThreshold,
      },
    });
  }, [networkSpeciesScope, networkCorrMethod, networkCorrThreshold, networkPvalueThreshold, runAnalysis, sessionId, clearResult, sessionStore, selectedSpecies]);

  return (
    <div className={cn("space-y-6")}>
      {!hasSession && <NoSessionBanner />}
      {analysisError && <StatusAlert status="error" title="Analysis failed" description={analysisError} />}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Strain Analysis ⭐</h1>
        <p className="text-muted-foreground">
          Perform strain-level statistical analysis — core feature of Meta2bAnalyst
        </p>
      </div>

      <Card>
        <CardContent className="p-4">
          <div className="flex items-center gap-4">
            <Microscope className="h-5 w-5 text-primary" />
            <div className="flex-1">
              <Label className="text-sm font-medium">Species Selector</Label>
              <div className="flex items-center gap-2 mt-1">
                <div className="relative flex-1 max-w-md">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search species..."
                    value={speciesSearch}
                    onChange={(e) => setSpeciesSearch(e.target.value)}
                    className="pl-9"
                  />
                  {speciesSearch && filteredSpecies.length > 0 && (
                    <div className="absolute z-10 w-full mt-1 bg-popover border rounded-md shadow-lg max-h-48 overflow-auto">
                      {filteredSpecies.map((s) => (
                        <button
                          key={s}
                          className="w-full text-left px-3 py-2 text-sm hover:bg-accent"
                          onClick={() => {
                            setSelectedSpecies(s);
                            setSpeciesSearch("");
                          }}
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <Select value={selectedSpecies} onValueChange={setSelectedSpecies}>
                  <SelectTrigger className="w-[220px]">
                    <SelectValue placeholder="Select species" />
                  </SelectTrigger>
                  <SelectContent>
                    {mockSpecies.map((s) => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="composition" className="w-full">
        <TabsList className="grid grid-cols-4 w-full">
          <TabsTrigger value="composition" className="gap-2">
            <Layers className="h-4 w-4" /> Composition
          </TabsTrigger>
          <TabsTrigger value="diversity" className="gap-2">
            <BarChart3 className="h-4 w-4" /> Diversity
          </TabsTrigger>
          <TabsTrigger value="differential" className="gap-2">
            <GitBranch className="h-4 w-4" /> Differential
          </TabsTrigger>
          <TabsTrigger value="network" className="gap-2">
            <Network className="h-4 w-4" /> Network
          </TabsTrigger>
        </TabsList>

        <TabsContent value="composition" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-1 space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Composition Parameters</CardTitle>
                  <CardDescription>Species: {selectedSpecies}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <ParameterItem label="Visualization Type">
                    <RadioGroup
                      value={compType}
                      onValueChange={(v) => setCompType(v as "stacked" | "heatmap")}
                      className="grid grid-cols-2 gap-2"
                    >
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="stacked" id="stacked" />
                        <Label htmlFor="stacked" className="cursor-pointer">Stacked Bar</Label>
                      </div>
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="heatmap" id="heatmap" />
                        <Label htmlFor="heatmap" className="cursor-pointer">Heatmap</Label>
                      </div>
                    </RadioGroup>
                  </ParameterItem>
                  <ParameterItem label="Group Column (Optional)">
                    <Select value={compGroup} onValueChange={setCompGroup}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="">None</SelectItem>
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
                title={compType === "stacked" ? "Strain Composition (Stacked)" : "Strain Abundance Heatmap"}
                plotData={result?.plot_data}
                tableData={result?.data}
                stats={result?.statistics}
                isLoading={isLoading}
                onRun={handleRunComposition}
              />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="diversity" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-1 space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Diversity Parameters</CardTitle>
                  <CardDescription>Species: {selectedSpecies}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <ParameterItem label="Analysis Type">
                    <RadioGroup
                      value={strainDivType}
                      onValueChange={(v) => setStrainDivType(v as "alpha" | "beta")}
                      className="grid grid-cols-2 gap-2"
                    >
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="alpha" id="alpha" />
                        <Label htmlFor="alpha" className="cursor-pointer">Alpha</Label>
                      </div>
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="beta" id="beta" />
                        <Label htmlFor="beta" className="cursor-pointer">Beta</Label>
                      </div>
                    </RadioGroup>
                  </ParameterItem>

                  {strainDivType === "alpha" && (
                    <ParameterItem label="Diversity Indices">
                      <div className="grid grid-cols-2 gap-2">
                        {["Shannon", "Simpson", "Observed"].map((idx) => (
                          <div key={idx} className="flex items-center space-x-2">
                            <Checkbox
                              id={`strain-${idx}`}
                              checked={strainIndices.includes(idx)}
                              onCheckedChange={(checked) => {
                                if (checked) setStrainIndices([...strainIndices, idx]);
                                else setStrainIndices(strainIndices.filter((i) => i !== idx));
                              }}
                            />
                            <Label htmlFor={`strain-${idx}`} className="cursor-pointer text-sm">{idx}</Label>
                          </div>
                        ))}
                      </div>
                    </ParameterItem>
                  )}

                  {strainDivType === "beta" && (
                    <>
                      <ParameterItem label="Distance Algorithm">
                        <Select value={strainDistance} onValueChange={setStrainDistance}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="Bray-Curtis">Bray-Curtis</SelectItem>
                            <SelectItem value="Jaccard">Jaccard</SelectItem>
                            <SelectItem value="Euclidean">Euclidean</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label="Ordination Method">
                        <Select value={strainOrdination} onValueChange={setStrainOrdination}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="PCoA">PCoA</SelectItem>
                            <SelectItem value="NMDS">NMDS</SelectItem>
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                    </>
                  )}

                  <ParameterItem label="Group Column">
                    <Select value={strainDivGroup} onValueChange={setStrainDivGroup}>
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
                title={strainDivType === "alpha" ? "Strain Alpha Diversity" : `${strainOrdination} Plot`}
                plotData={result?.plot_data}
                tableData={result?.data}
                stats={result?.statistics}
                isLoading={isLoading}
                onRun={handleRunDiversity}
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
                  <CardDescription>Species: {selectedSpecies}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <ParameterItem label="Analysis Scope" tooltip="Within species compares strains of the same species. Cross-species compares all strains.">
                    <RadioGroup
                      value={diffScope}
                      onValueChange={(v) => setDiffScope(v as "within-species" | "cross-species")}
                      className="grid gap-2"
                    >
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="within-species" id="within" />
                        <Label htmlFor="within" className="cursor-pointer">Within Species (same species strains)</Label>
                      </div>
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="cross-species" id="cross" />
                        <Label htmlFor="cross" className="cursor-pointer">Cross Species (all strains)</Label>
                      </div>
                    </RadioGroup>
                  </ParameterItem>
                  <ParameterItem label="Method">
                    <Select value={diffMethod} onValueChange={setDiffMethod}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Wilcoxon">Wilcoxon</SelectItem>
                        <SelectItem value="t-test">t-test</SelectItem>
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
                </CardContent>
              </Card>
            </div>
            <div className="lg:col-span-2">
              <ResultSection
                title="Strain Differential Volcano Plot"
                plotData={result?.plot_data}
                tableData={result?.data}
                stats={result?.statistics}
                isLoading={isLoading}
                onRun={handleRunDifferential}
              />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="network" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-1 space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Network Parameters</CardTitle>
                  <CardDescription>Strain co-occurrence network</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <ParameterItem label="Species Scope">
                    <Select value={networkSpeciesScope} onValueChange={setNetworkSpeciesScope}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="current">Current Species</SelectItem>
                        <SelectItem value="all">All Species</SelectItem>
                      </SelectContent>
                    </Select>
                  </ParameterItem>
                  <ParameterItem label="Correlation Method">
                    <Select value={networkCorrMethod} onValueChange={setNetworkCorrMethod}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Spearman">Spearman</SelectItem>
                        <SelectItem value="Pearson">Pearson</SelectItem>
                      </SelectContent>
                    </Select>
                  </ParameterItem>
                  <ParameterItem label={`Correlation Threshold (r > ${networkCorrThreshold.toFixed(2)})`}>
                    <Slider
                      value={[networkCorrThreshold]}
                      onValueChange={(v) => setNetworkCorrThreshold(v[0])}
                      min={0.1}
                      max={0.5}
                      step={0.05}
                    />
                  </ParameterItem>
                  <ParameterItem label={`P-value Threshold (p < ${networkPvalueThreshold.toFixed(2)})`}>
                    <Slider
                      value={[networkPvalueThreshold]}
                      onValueChange={(v) => setNetworkPvalueThreshold(v[0])}
                      min={0.01}
                      max={0.1}
                      step={0.01}
                    />
                  </ParameterItem>
                </CardContent>
              </Card>
            </div>
            <div className="lg:col-span-2">
              <ResultSection
                title="Strain Co-occurrence Network"
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
