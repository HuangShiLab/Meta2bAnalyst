import { useState, useCallback, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { UploadZone } from "@/components/shared/UploadZone";
import { PlotlyChart } from "@/components/shared/PlotlyChart";
import { useSessionStore } from "@/stores/sessionStore";
import { useSectionAnalysis } from "@/hooks/useAnalysis";
import { downloadFigure, downloadCSV, downloadPDF, createSession, uploadFile } from "@/utils/api";
import type { PlotlyFigure } from "@/types";
import {
  Layers,
  Upload,
  Play,
  Image as ImageIcon,
  FileSpreadsheet,
  FileText,
  Loader2,
  Dna,
  FlaskConical,
  Link2,
  BarChart3,
  ArrowLeftRight,
  GitMerge,
} from "lucide-react";
import { cn } from "@/lib/utils";

function ResultSection({
  title,
  plotData,
  tableData,
  stats,
  isLoading,
  error,
  onRun,
  runLabel = "Run Analysis",
}: {
  title: string;
  plotData?: PlotlyFigure;
  tableData?: Record<string, string | number>[];
  stats?: Record<string, unknown>;
  isLoading: boolean;
  error?: string;
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

      {error && (
        <div className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
          Error: {error}
        </div>
      )}

      {isLoading && (
        <div className="flex items-center justify-center h-64 rounded-lg border border-border bg-muted/50">
          <div className="flex flex-col items-center gap-2">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-sm text-muted-foreground">Analysis in progress...</p>
          </div>
        </div>
      )}

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
  );
}

function ParameterItem({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Label className="text-sm font-medium">{label}</Label>
      </div>
      {children}
    </div>
  );
}

export function MultiOmics() {
  const sessionStore = useSessionStore();
  const setCurrentStep = useSessionStore((state) => state.setCurrentStep);
  const sessionId = useSessionStore((state) => state.sessionId);
  const { results, loading, errors, run, clear } = useSectionAnalysis();

  useEffect(() => {
    setCurrentStep("multi-omics");
  }, [setCurrentStep]);

  // Upload state
  const [microbiomeFile, setMicrobiomeFile] = useState<File | null>(null);
  const [metabolomeFile, setMetabolomeFile] = useState<File | null>(null);
  const [metadataFile, setMetadataFile] = useState<File | null>(null);
  const [uploaded, setUploaded] = useState(false);

  // Tab state
  const [activeTab, setActiveTab] = useState("individual");

  // Individual Omics parameters
  const [groupColumn, setGroupColumn] = useState("Visit");
  const [referenceGroup, setReferenceGroup] = useState("T4");
  const [pvalueThreshold, setPvalueThreshold] = useState(0.05);
  const [fcThreshold, setFcThreshold] = useState(1.5);

  // Integration parameters
  const [nComponents, setNComponents] = useState(2);
  const [sparsityX, setSparsityX] = useState(0.3);
  const [sparsityY, setSparsityY] = useState(0.3);
  const [nJoint, setNJoint] = useState(2);
  const [nOrthoX, setNOrthoX] = useState(1);
  const [nOrthoY, setNOrthoY] = useState(1);

  // MOFA+
  const [mofaFactors, setMofaFactors] = useState(5);
  const [mofaGroup, setMofaGroup] = useState("Visit");
  // DIABLO
  const [diabloComponents, setDiabloComponents] = useState(2);
  const [diabloGroup, setDiabloGroup] = useState("Visit");

  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const handleUpload = useCallback(async () => {
    // Metadata is required: grouping, ordination coloring and every
    // group-wise statistic downstream depend on it.
    if (!microbiomeFile || !metabolomeFile || !metadataFile) return;
    setIsUploading(true);
    setUploadError(null);
    try {
      const session = await createSession({
        name: "Multi-omics analysis",
        data_format: "tsv",
        description: "Created from MultiOmics page",
      });
      const sid = session.id;
      await uploadFile(sid, microbiomeFile, "microbiome");
      await uploadFile(sid, metabolomeFile, "metabolome");
      await uploadFile(sid, metadataFile, "metadata");
      sessionStore.setSessionId(sid);
      setUploaded(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Upload failed";
      setUploadError(message);
    } finally {
      setIsUploading(false);
    }
  }, [microbiomeFile, metabolomeFile, metadataFile, sessionStore]);

  const [isLoadingExample, setIsLoadingExample] = useState(false);

  const loadExampleData = useCallback(async () => {
    setIsLoadingExample(true);
    setUploadError(null);
    try {
      const fetchFile = async (name: string, type: string) => {
        const response = await fetch(`/examples/demo/multi-omics/${name}`);
        if (!response.ok) throw new Error(`Failed to load ${name}`);
        const blob = await response.blob();
        return new File([blob], name, { type });
      };
      // Huang mBio 2021 demo set: sample IDs verified consistent across all
      // three files (261 samples).
      setMicrobiomeFile(await fetchFile("Matched_microbes_abd_261.tsv", "text/tab-separated-values"));
      setMetabolomeFile(await fetchFile("Matched_metabolites_abd_261.txt", "text/tab-separated-values"));
      setMetadataFile(await fetchFile("Matched_metadata_261.tsv", "text/tab-separated-values"));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load example data";
      setUploadError(message);
    } finally {
      setIsLoadingExample(false);
    }
  }, []);

  const runWithHistory = useCallback(async (
    key: string,
    type: Parameters<typeof run>[1],
    params: Record<string, unknown>,
    historyType: string,
    historyLabel: string
  ) => {
    clear(key);
    try {
      // run() records NO_SESSION_MESSAGE / backend errors into errors[key],
      // which the section card renders; rethrowing would be unhandled.
      const response = await run(key, type, sessionId ?? "", params);
      sessionStore.addAnalysisHistoryItem({
        id: response.job_id,
        type: historyType,
        label: historyLabel,
        timestamp: new Date().toISOString(),
        status: "success",
        plotData: response.plot_data,
        statistics: response.statistics,
        tableData: response.data,
      });
    } catch {
      // error state already set by useSectionAnalysis
    }
  }, [clear, run, sessionId, sessionStore]);

  // Individual Omics handlers
  const handleRunMicrobiomePCoA = useCallback(async () => {
    // AnalysisRequest contract: analysis-specific knobs go under `parameters`,
    // grouping is the top-level `group_column`. Flat camelCase keys are
    // silently dropped by the backend (no group coloring, default metric).
    await runWithHistory("mb_pcoa", "pcoa", {
      parameters: { metric: "braycurtis", n_components: 3 },
      group_column: groupColumn,
    }, "Microbiome PCoA", "Bray-Curtis PCoA");
  }, [runWithHistory, groupColumn]);

  const handleRunMetabolomePCA = useCallback(async () => {
    await runWithHistory("met_pca", "metabolomics", {
      analysis_type: "pca",
      group_column: groupColumn,
      n_components: 5,
      transformation: "zscore",
    }, "Metabolome PCA", "z-score PCA");
  }, [runWithHistory, groupColumn]);

  const handleRunPERMANOVA = useCallback(async () => {
    await runWithHistory("permanova", "permanova", {
      parameters: { metric: "braycurtis", n_permutations: 999 },
      group_column: groupColumn,
    }, "PERMANOVA", `PERMANOVA (${groupColumn})`);
  }, [runWithHistory, groupColumn]);

  const handleRunMetabolomeMarkerDiscovery = useCallback(async () => {
    await runWithHistory("met_marker", "metabolomics", {
      analysis_type: "marker_discovery",
      group_column: groupColumn,
      reference_group: referenceGroup,
      test_method: "welch",
      pvalue_threshold: pvalueThreshold,
      fc_threshold: fcThreshold,
      transformation: "log1p",
    }, "Metabolome Marker Discovery", `vs ${referenceGroup}`);
  }, [runWithHistory, groupColumn, referenceGroup, pvalueThreshold, fcThreshold]);

  const handleRunMicrobiomeMarkerDiscovery = useCallback(async () => {
    await runWithHistory("mb_marker", "metabolomics", {
      analysis_type: "marker_discovery",
      data_source: "microbiome",
      group_column: groupColumn,
      reference_group: referenceGroup,
      test_method: "mannwhitney",
      pvalue_threshold: pvalueThreshold,
      fc_threshold: fcThreshold,
      transformation: "clr",
    }, "Microbiome Marker Discovery", `vs ${referenceGroup}`);
  }, [runWithHistory, groupColumn, referenceGroup, pvalueThreshold, fcThreshold]);

  // Integration handlers
  const handleRunProcrustes = useCallback(async () => {
    await runWithHistory("procrustes", "cross-omics", {
      analysis_type: "procrustes",
      group_column: groupColumn,
    }, "Procrustes", "Microbiome-Metabolome Alignment");
  }, [runWithHistory, groupColumn]);

  const handleRunMantel = useCallback(async () => {
    await runWithHistory("mantel", "cross-omics", {
      analysis_type: "mantel",
    }, "Mantel Test", "Distance Matrix Correlation");
  }, [runWithHistory]);

  const handleRunSparseCCA = useCallback(async () => {
    await runWithHistory("scca", "sparse-cca", {
      n_components: nComponents,
      sparsity_x: sparsityX,
      sparsity_y: sparsityY,
      group_column: groupColumn,
    }, "Sparse CCA", `CC${nComponents}`);
  }, [runWithHistory, nComponents, sparsityX, sparsityY, groupColumn]);

  const handleRunRDA = useCallback(async () => {
    await runWithHistory("rda", "rda", {
      n_components: nComponents,
      group_column: groupColumn,
    }, "RDA", "Redundancy Analysis");
  }, [runWithHistory, nComponents, groupColumn]);

  const handleRunO2PLS = useCallback(async () => {
    await runWithHistory("o2pls", "o2pls", {
      n_joint: nJoint,
      n_ortho_x: nOrthoX,
      n_ortho_y: nOrthoY,
      group_column: groupColumn,
    }, "O2PLS", "Two-way Orthogonal PLS");
  }, [runWithHistory, nJoint, nOrthoX, nOrthoY, groupColumn]);

  const handleRunMOFA = useCallback(async () => {
    await runWithHistory("mofa", "mofa", {
      n_factors: mofaFactors,
      group_column: mofaGroup,
    }, "MOFA+", `${mofaFactors} Factors`);
  }, [runWithHistory, mofaFactors, mofaGroup]);

  const handleRunDIABLO = useCallback(async () => {
    await runWithHistory("diablo", "diablo", {
      n_components: diabloComponents,
      group_column: diabloGroup,
    }, "DIABLO", `${diabloComponents} Components`);
  }, [runWithHistory, diabloComponents, diabloGroup]);

  const metadataColumns = ["Visit", "Plaque", "Subject", "Bleeding"];
  const referenceGroups = ["T1", "T4", "T5", "T6", "T7", "T8", "T9"];
  const acceptTypes = { "text/tab-separated-values": [".tsv"], "text/csv": [".csv"], "text/plain": [".txt"] };

  const sectionProps = (key: string) => ({
    plotData: results[key]?.plot_data,
    tableData: results[key]?.data,
    stats: results[key]?.statistics,
    isLoading: !!loading[key],
    error: errors[key],
  });

  return (
    <div data-testid="multiomics-page" className={cn("space-y-6")}>
      <div>
        <h1 data-testid="multiomics-title" className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Layers className="h-6 w-6" />
          Multi-omics Analysis
        </h1>
        <p className="text-muted-foreground">
          Integrate microbiome and metabolome data with advanced multi-omics methods
        </p>
      </div>

      {/* Upload Section */}
      {!uploaded ? (
        <Card>
          <CardHeader>
            <CardTitle>Upload Multi-omics Data</CardTitle>
            <CardDescription>
              Upload paired microbiome (species/genus table), metabolome (intensity matrix), and metadata files — all three are required
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Dna className="h-4 w-4 text-primary" />
                  <Label className="font-medium">Microbiome Data</Label>
                </div>
                <UploadZone
                  accept={acceptTypes}
                  file={microbiomeFile}
                  onUpload={(files: File[]) => setMicrobiomeFile(files[0] || null)}
                />
                <p className="text-xs text-muted-foreground">Samples × features (TSV/CSV)</p>
              </div>
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <FlaskConical className="h-4 w-4 text-primary" />
                  <Label className="font-medium">Metabolome Data</Label>
                </div>
                <UploadZone
                  accept={acceptTypes}
                  file={metabolomeFile}
                  onUpload={(files: File[]) => setMetabolomeFile(files[0] || null)}
                />
                <p className="text-xs text-muted-foreground">Samples × metabolites (TSV/CSV)</p>
              </div>
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-primary" />
                  <Label className="font-medium">Metadata</Label>
                  <span className="text-xs text-destructive">*required</span>
                </div>
                <UploadZone
                  accept={acceptTypes}
                  file={metadataFile}
                  onUpload={(files: File[]) => setMetadataFile(files[0] || null)}
                />
                <p className="text-xs text-muted-foreground">Sample × variables (TSV/CSV)</p>
              </div>
            </div>
            {uploadError && (
              <div className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
                Upload error: {uploadError}
              </div>
            )}
            <div className="flex gap-3">
              <Button
                variant="outline"
                onClick={loadExampleData}
                disabled={isUploading || isLoadingExample}
                className="flex-1 gap-2"
              >
                {isLoadingExample ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
                {isLoadingExample ? "Loading..." : "Load Example Data"}
              </Button>
              <Button
                onClick={handleUpload}
                disabled={!microbiomeFile || !metabolomeFile || !metadataFile || isUploading}
                className="flex-[2] gap-2"
              >
                {isUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                {isUploading ? "Uploading..." : "Start Multi-omics Analysis"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="flex items-center gap-4 p-3 bg-green-50 rounded-lg">
            <Dna className="h-5 w-5 text-green-600" />
            <span className="text-sm text-green-700">
              <strong>Microbiome:</strong> {microbiomeFile?.name} ({microbiomeFile ? (microbiomeFile.size / 1024).toFixed(1) : 0} KB)
            </span>
            <span className="text-green-400">|</span>
            <FlaskConical className="h-5 w-5 text-green-600" />
            <span className="text-sm text-green-700">
              <strong>Metabolome:</strong> {metabolomeFile?.name} ({metabolomeFile ? (metabolomeFile.size / 1024).toFixed(1) : 0} KB)
            </span>
            {metadataFile && (
              <>
                <span className="text-green-400">|</span>
                <FileText className="h-5 w-5 text-green-600" />
                <span className="text-sm text-green-700">
                  <strong>Metadata:</strong> {metadataFile.name}
                </span>
              </>
            )}
            <Button variant="ghost" size="sm" onClick={() => setUploaded(false)} className="ml-auto">
              Re-upload
            </Button>
          </div>

          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <TabsList className="grid grid-cols-3 w-full">
              <TabsTrigger value="individual" className="gap-2">
                <BarChart3 className="h-4 w-4" /> Individual Omics
              </TabsTrigger>
              <TabsTrigger value="integration" className="gap-2">
                <Link2 className="h-4 w-4" /> Integration
              </TabsTrigger>
              <TabsTrigger value="feature" className="gap-2">
                <GitMerge className="h-4 w-4" /> Feature-level
              </TabsTrigger>
            </TabsList>

            {/* Individual Omics Tab */}
            <TabsContent value="individual" className="space-y-4 mt-4">
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-1 space-y-4">
                  <Card>
                    <CardHeader>
                      <CardTitle>Analysis Parameters</CardTitle>
                      <CardDescription>Configure individual omics analysis</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-6">
                      <ParameterItem label="Group Column">
                        <Select value={groupColumn} onValueChange={setGroupColumn}>
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
                      <ParameterItem label="Reference Group (Day 0)">
                        <Select value={referenceGroup} onValueChange={setReferenceGroup}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {referenceGroups.map((grp) => (
                              <SelectItem key={grp} value={grp}>{grp}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </ParameterItem>
                      <ParameterItem label={`P-value Threshold (${pvalueThreshold.toFixed(3)})`}>
                        <Slider
                          value={[pvalueThreshold]}
                          onValueChange={(v) => setPvalueThreshold(v[0])}
                          min={0.001}
                          max={0.1}
                          step={0.001}
                        />
                      </ParameterItem>
                      <ParameterItem label={`Fold Change Threshold (${fcThreshold.toFixed(1)})`}>
                        <Slider
                          value={[fcThreshold]}
                          onValueChange={(v) => setFcThreshold(v[0])}
                          min={1.0}
                          max={5.0}
                          step={0.1}
                        />
                      </ParameterItem>
                    </CardContent>
                  </Card>
                </div>

                <div className="lg:col-span-2 space-y-4">
                  <ResultSection
                    title="Microbiome PCoA (Bray-Curtis)"
                    onRun={handleRunMicrobiomePCoA}
                    runLabel="Run PCoA"
                    {...sectionProps("mb_pcoa")}
                  />
                  <ResultSection
                    title="Metabolome PCA (z-score)"
                    onRun={handleRunMetabolomePCA}
                    runLabel="Run PCA"
                    {...sectionProps("met_pca")}
                  />
                  <ResultSection
                    title="PERMANOVA"
                    onRun={handleRunPERMANOVA}
                    runLabel="Run PERMANOVA"
                    {...sectionProps("permanova")}
                  />
                  <ResultSection
                    title="Marker Discovery (Metabolome: log1p + Welch t-test)"
                    onRun={handleRunMetabolomeMarkerDiscovery}
                    runLabel="Run Metabolome Markers"
                    {...sectionProps("met_marker")}
                  />
                  <ResultSection
                    title="Marker Discovery (Microbiome: CLR + Wilcoxon rank-sum)"
                    onRun={handleRunMicrobiomeMarkerDiscovery}
                    runLabel="Run Microbiome Markers"
                    {...sectionProps("mb_marker")}
                  />
                </div>
              </div>
            </TabsContent>

            {/* Integration Tab */}
            <TabsContent value="integration" className="space-y-4 mt-4">
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-1 space-y-4">
                  <Card>
                    <CardHeader>
                      <CardTitle>Integration Parameters</CardTitle>
                      <CardDescription>Configure multi-omics integration</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-6">
                      <ParameterItem label="Group Column">
                        <Select value={groupColumn} onValueChange={setGroupColumn}>
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
                      <ParameterItem label={`Components (${nComponents})`}>
                        <Slider
                          value={[nComponents]}
                          onValueChange={(v) => setNComponents(v[0])}
                          min={1}
                          max={5}
                          step={1}
                        />
                      </ParameterItem>
                      <ParameterItem label={`Sparse CCA X Sparsity (${sparsityX.toFixed(2)})`}>
                        <Slider
                          value={[sparsityX]}
                          onValueChange={(v) => setSparsityX(v[0])}
                          min={0.1}
                          max={0.9}
                          step={0.05}
                        />
                      </ParameterItem>
                      <ParameterItem label={`Sparse CCA Y Sparsity (${sparsityY.toFixed(2)})`}>
                        <Slider
                          value={[sparsityY]}
                          onValueChange={(v) => setSparsityY(v[0])}
                          min={0.1}
                          max={0.9}
                          step={0.05}
                        />
                      </ParameterItem>
                      <ParameterItem label={`O2PLS Joint Components (${nJoint})`}>
                        <Slider
                          value={[nJoint]}
                          onValueChange={(v) => setNJoint(v[0])}
                          min={1}
                          max={5}
                          step={1}
                        />
                      </ParameterItem>
                      <ParameterItem label={`O2PLS X Orthogonal (${nOrthoX})`}>
                        <Slider
                          value={[nOrthoX]}
                          onValueChange={(v) => setNOrthoX(v[0])}
                          min={0}
                          max={3}
                          step={1}
                        />
                      </ParameterItem>
                      <ParameterItem label={`O2PLS Y Orthogonal (${nOrthoY})`}>
                        <Slider
                          value={[nOrthoY]}
                          onValueChange={(v) => setNOrthoY(v[0])}
                          min={0}
                          max={3}
                          step={1}
                        />
                      </ParameterItem>
                      <div className="border-t pt-4 mt-4 space-y-4">
                        <p className="text-sm font-medium text-muted-foreground">MOFA+ Parameters</p>
                        <ParameterItem label={`Number of Factors (${mofaFactors})`}>
                          <Slider
                            value={[mofaFactors]}
                            onValueChange={(v) => setMofaFactors(v[0])}
                            min={2}
                            max={10}
                            step={1}
                          />
                        </ParameterItem>
                        <ParameterItem label="MOFA+ Group Column">
                          <Select value={mofaGroup} onValueChange={setMofaGroup}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              {metadataColumns.map((col) => (
                                <SelectItem key={col} value={col}>{col}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </ParameterItem>
                      </div>
                      <div className="border-t pt-4 mt-4 space-y-4">
                        <p className="text-sm font-medium text-muted-foreground">DIABLO Parameters</p>
                        <ParameterItem label={`Components (${diabloComponents})`}>
                          <Slider
                            value={[diabloComponents]}
                            onValueChange={(v) => setDiabloComponents(v[0])}
                            min={1}
                            max={5}
                            step={1}
                          />
                        </ParameterItem>
                        <ParameterItem label="DIABLO Group Column">
                          <Select value={diabloGroup} onValueChange={setDiabloGroup}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              {metadataColumns.map((col) => (
                                <SelectItem key={col} value={col}>{col}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </ParameterItem>
                      </div>
                    </CardContent>
                  </Card>
                </div>

                <div className="lg:col-span-2 space-y-4">
                  <ResultSection
                    title="Procrustes Analysis"
                    onRun={handleRunProcrustes}
                    runLabel="Run Procrustes"
                    {...sectionProps("procrustes")}
                  />
                  <ResultSection
                    title="Mantel Test"
                    onRun={handleRunMantel}
                    runLabel="Run Mantel"
                    {...sectionProps("mantel")}
                  />
                  <ResultSection
                    title="Sparse CCA"
                    onRun={handleRunSparseCCA}
                    runLabel="Run Sparse CCA"
                    {...sectionProps("scca")}
                  />
                  <ResultSection
                    title="RDA (Redundancy Analysis)"
                    onRun={handleRunRDA}
                    runLabel="Run RDA"
                    {...sectionProps("rda")}
                  />
                  <ResultSection
                    title="O2PLS"
                    onRun={handleRunO2PLS}
                    runLabel="Run O2PLS"
                    {...sectionProps("o2pls")}
                  />
                  <ResultSection
                    title="MOFA+ Multi-omics Factor Analysis"
                    onRun={handleRunMOFA}
                    runLabel="Run MOFA+"
                    {...sectionProps("mofa")}
                  />
                  <ResultSection
                    title="DIABLO (sPLS-DA Integration)"
                    onRun={handleRunDIABLO}
                    runLabel="Run DIABLO"
                    {...sectionProps("diablo")}
                  />
                </div>
              </div>
            </TabsContent>

            {/* Feature-level Tab */}
            <TabsContent value="feature" className="space-y-4 mt-4">
              <Card>
                <CardHeader>
                  <CardTitle>Feature-level Cross-omics Analysis</CardTitle>
                  <CardDescription>
                    Spearman rank correlations between bacterial genera and metabolites.
                    Significant associations (p&lt;0.05) are identified for exploratory analysis.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-4">
                    <Button onClick={handleRunMantel} disabled={!!loading["mantel"]} className="gap-2">
                      {loading["mantel"] ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowLeftRight className="h-4 w-4" />}
                      Run Cross-correlation Analysis
                    </Button>
                    <p className="text-sm text-muted-foreground">
                      This will compute 44 × 1,125 = 49,500 pairwise correlations and identify significant associations.
                    </p>
                  </div>
                </CardContent>
              </Card>
              <ResultSection
                title="Cross-omics Correlation Heatmap"
                onRun={handleRunMantel}
                runLabel="Run Heatmap"
                {...sectionProps("mantel")}
              />
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  );
}
