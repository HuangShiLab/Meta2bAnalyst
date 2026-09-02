import { useState, useCallback, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useDropzone } from "react-dropzone";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Upload, FileType, X, CheckCircle, AlertCircle, Loader2, ChevronDown, ChevronUp, FileText, HelpCircle, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSessionStore } from "@/stores/sessionStore";
import { useAuthStore } from "@/stores/authStore";
import { StatusAlert } from "@/components/shared/StatusAlert";
import { createSession, uploadFile } from "@/utils/api";
import type { UploadFormat, UploadFile } from "@/types";

const formatConfigs: Record<UploadFormat, { label: string; description: string; required: string[]; optional: string[]; extensions: string[]; exampleFiles: string[] }> = {
  "2brad-m": {
    label: "2bRAD-M",
    description: "2bRAD-M pipeline output",
    required: ["species_abundance.csv", "metadata.csv"],
    optional: ["functional_genes.csv"],
    extensions: [".csv"],
    exampleFiles: ["2brad_m_species.csv", "metadata_gut.csv", "2brad_m_function.csv"],
  },
  qiime: {
    label: "QIIME/BIOM",
    description: "QIIME2 BIOM format",
    required: [".biom file", "metadata.csv"],
    optional: [],
    extensions: [".biom", ".csv"],
    exampleFiles: ["qiime_feature_table.biom", "qiime_metadata.csv"],
  },
  mothur: {
    label: "Mothur",
    description: "Mothur pipeline output",
    required: [".shared file", ".taxonomy file", "metadata.csv"],
    optional: [],
    extensions: [".shared", ".taxonomy", ".csv"],
    exampleFiles: ["mothur_otu_table.shared", "mothur_otu_taxonomy.taxonomy", "mothur_metadata.csv"],
  },
  tsv: {
    label: "TSV/CSV",
    description: "Generic feature table",
    required: ["feature_table.csv", "metadata.csv"],
    optional: ["taxonomy.csv"],
    extensions: [".csv", ".tsv"],
    exampleFiles: ["qiime_feature_table.tsv", "qiime_metadata.csv", "taxonomy.csv"],
  },
  metaphlan: {
    label: "MetaPhlAn",
    description: "MetaPhlAn taxonomic abundance table",
    required: ["metaphlan_abundance.tsv", "metadata.tsv"],
    optional: [],
    extensions: [".tsv"],
    exampleFiles: ["metaphlan_abundance.tsv", "metaphlan_metadata.tsv"],
  },
  humann3: {
    label: "HUMAnN3",
    description: "HUMAnN3 pathway or gene-family abundance",
    required: ["humann3_pathabundance.tsv", "metadata.tsv"],
    optional: ["humann3_genefamilies.tsv"],
    extensions: [".tsv"],
    exampleFiles: ["humann3_pathabundance.tsv", "humann3_metadata.tsv", "humann3_genefamilies.tsv"],
  },
};

export function UploadPage() {
  const navigate = useNavigate();
  const isAuthenticated = !!useAuthStore((s) => s.token);
  const { uploadFormat, setUploadFormat, uploadedFiles, addUploadedFile, removeUploadedFile } = useSessionStore();
  const setSessionId = useSessionStore((state) => state.setSessionId);
  const [selectedFormat, setSelectedFormat] = useState<UploadFormat>(uploadFormat || "tsv");
  const [validationStatus, setValidationStatus] = useState<"idle" | "validating" | "success" | "error">("idle");
  const [validationMessage, setValidationMessage] = useState("");
  const [formatOpen, setFormatOpen] = useState(false);
  const [fileMap, setFileMap] = useState<Record<string, File>>({});
  const [isUploading, setIsUploading] = useState(false);
  // Per-file omics layer chosen by the user; falls back to filename
  // classification when untouched.
  const [fileTypeOverrides, setFileTypeOverrides] = useState<Record<string, string>>({});

  const currentFormat = formatConfigs[selectedFormat];

  const FILE_TYPE_OPTIONS = [
    { value: "microbiome", label: "Microbiome" },
    { value: "metabolome", label: "Metabolome" },
    { value: "metadata", label: "Metadata" },
    { value: "feature_table", label: "Feature table (generic)" },
  ];

  // uploadedFiles is persisted (zustand) across page reloads, but the actual
  // File objects in fileMap are component state and die on reload. Stale
  // entries would upload nothing while reporting success — purge them on
  // mount; the user must re-select files after a refresh.
  useEffect(() => {
    uploadedFiles.forEach((f) => removeUploadedFile(f.id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // crypto.randomUUID() is only available in secure contexts (https or
  // localhost). Students browsing the LAN URL (http://<ip>:8080) get an
  // insecure context where it is undefined — without this fallback the drop
  // handler throws and the page appears to do nothing.
  const makeId = () =>
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `f-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

  const classifyFile = (name: string): string => {
    const lower = name.toLowerCase();
    // Check metabolome BEFORE metadata: "metabolome" contains "meta".
    if (lower.includes("metabolome") || lower.includes("metabolite") || lower.includes("lcms")) return "metabolome";
    if (lower.includes("metadata") || lower.includes("sample") || (lower.includes("meta") && !lower.includes("metabol"))) return "metadata";
    if (lower.includes("metaphlan") || lower.includes("clade")) return "microbiome";
    if (lower.includes("humann3") || lower.includes("humann") || lower.includes("pathabundance") || lower.includes("genefamilies")) return "metabolome";
    if (lower.includes("microbiome") || lower.includes("microbial") || lower.includes("16s") || lower.includes("otu") || lower.includes("asv") || lower.includes("taxa")) return "microbiome";
    if (lower.includes("ms")) return "metabolome";
    return "feature_table";
  };

  /** User-chosen omics layer wins; otherwise the filename classification. */
  const effectiveType = (f: UploadFile) => fileTypeOverrides[f.id] || classifyFile(f.name);

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      try {
        acceptedFiles.forEach((file) => {
          const id = makeId();
          const uploadFile: UploadFile = {
            id,
            name: file.name,
            size: file.size,
            type: file.type || "application/octet-stream",
            progress: 100,
            status: "success",
          };
          addUploadedFile(uploadFile);
          setFileMap((prev) => ({ ...prev, [id]: file }));
        });
        if (acceptedFiles.length > 0) {
          setValidationStatus("idle");
          setValidationMessage("");
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setValidationStatus("error");
        setValidationMessage(`Failed to add files: ${message}`);
      }
    },
    [addUploadedFile]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "text/csv": [".csv"],
      "text/tab-separated-values": [".tsv"],
      "application/octet-stream": [".biom", ".shared", ".taxonomy"],
    },
  });

  const handleFormatChange = (value: string) => {
    setSelectedFormat(value as UploadFormat);
    setUploadFormat(value as UploadFormat);
  };

  const handleRemoveFile = (fileId: string) => {
    removeUploadedFile(fileId);
    setFileMap((prev) => {
      const next = { ...prev };
      delete next[fileId];
      return next;
    });
    setFileTypeOverrides((prev) => {
      const next = { ...prev };
      delete next[fileId];
      return next;
    });
  };

  const [isLoadingExample, setIsLoadingExample] = useState(false);

  const handleUseExampleData = async () => {
    setIsLoadingExample(true);
    try {
      // Clear previous files so example data is a clean start
      uploadedFiles.forEach((f) => removeUploadedFile(f.id));
      setFileMap({});
      setFileTypeOverrides({});

      const newFiles: UploadFile[] = [];
      const newFileMap: Record<string, File> = {};

      for (const filename of currentFormat.exampleFiles) {
        const response = await fetch(`/examples/${filename}`);
        if (!response.ok) {
          throw new Error(`Failed to load example file: ${filename}`);
        }
        const blob = await response.blob();
        const file = new File([blob], filename, { type: blob.type || "application/octet-stream" });
        const id = makeId();
        const uploadFile: UploadFile = {
          id,
          name: filename,
          size: file.size,
          type: file.type,
          progress: 100,
          status: "success",
        };
        newFiles.push(uploadFile);
        newFileMap[id] = file;
      }

      newFiles.forEach((f) => addUploadedFile(f));
      setFileMap(newFileMap);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setValidationStatus("error");
      setValidationMessage(`Failed to load example data: ${message}`);
    } finally {
      setIsLoadingExample(false);
    }
  };

  const handleValidate = async () => {
    setValidationStatus("validating");
    setValidationMessage("Validating data format and completeness...");

    if (uploadedFiles.length < 1) {
      setValidationStatus("error");
      setValidationMessage("Validation failed: Please upload at least one data file.");
      return;
    }

    const missing = uploadedFiles.filter((f) => !fileMap[f.id]);
    if (missing.length > 0) {
      setValidationStatus("error");
      setValidationMessage(
        `These files were added before a page reload and must be selected again: ${missing
          .map((f) => f.name)
          .join(", ")}`
      );
      return;
    }

    setIsUploading(true);

    try {
      const session = await createSession({
        name: `Meta2bAnalyst session ${new Date().toLocaleString()}`,
        data_format: selectedFormat,
        analysis_level: "multiomics",
        description: "Uploaded via Meta2bAnalyst web UI",
      });
      const sid = session.id;
      setSessionId(sid);

      const detectedTypes: string[] = [];
      for (const uploadFileMeta of uploadedFiles) {
        const file = fileMap[uploadFileMeta.id];
        if (!file) continue;
        const fileType = effectiveType(uploadFileMeta);
        await uploadFile(sid, file, fileType);
        detectedTypes.push(`${uploadFileMeta.name} → ${fileType}`);
      }

      setValidationStatus("success");
      setValidationMessage(
        `Uploaded ${detectedTypes.length} file(s). Session ID: ${sid}\n` +
        detectedTypes.join("\n")
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setValidationStatus("error");
      setValidationMessage(`Upload failed: ${message}`);
    } finally {
      setIsUploading(false);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  };

  return (
    <div className={cn("mx-auto max-w-3xl space-y-6")}>
      <div>
        <h1 data-testid="upload-title" className="text-2xl font-bold tracking-tight">Data Upload</h1>
        <p data-testid="upload-desc" className="text-muted-foreground">Select data format and upload files required for analysis</p>
      </div>

      {!isAuthenticated && (
        <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            You are browsing as a <strong>guest</strong>. Demo datasets stay
            available on the Agent and analysis pages, but uploading your own
            data requires an account —{" "}
            <Link to="/login" className="font-medium text-primary underline">
              sign in
            </Link>{" "}
            first.
          </p>
        </div>
      )}

      {/* Format Selection */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Data Format</CardTitle>
        </CardHeader>
        <CardContent>
          <RadioGroup
            value={selectedFormat}
            onValueChange={handleFormatChange}
            className="grid grid-cols-2 gap-4 sm:grid-cols-3"
          >
            {(Object.keys(formatConfigs) as UploadFormat[]).map((format) => (
              <div key={format}>
                <RadioGroupItem value={format} id={format} className="peer sr-only" />
                <Label
                  htmlFor={format}
                  className={cn(
                    "flex flex-col items-center justify-center rounded-lg border-2 border-muted bg-white p-4 text-sm font-medium transition-all hover:bg-muted/50 hover:border-primary/50 cursor-pointer",
                    "peer-data-[state=checked]:border-primary peer-data-[state=checked]:bg-primary/5"
                  )}
                >
                  <FileType className="mb-2 h-5 w-5 text-muted-foreground" />
                  <span className="text-sm font-semibold">{formatConfigs[format].label}</span>
                  <span className="mt-1 text-xs text-muted-foreground">{formatConfigs[format].description}</span>
                </Label>
              </div>
            ))}
          </RadioGroup>
        </CardContent>
      </Card>

      {/* Upload Zone */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">File Upload</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div
            data-testid="upload-dropzone"
            {...getRootProps()}
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-border p-10 transition-colors hover:bg-muted/50",
              isDragActive && "border-primary bg-primary/5"
            )}
          >
            <input data-testid="upload-input" {...getInputProps()} />
            <Upload className="h-10 w-10 text-muted-foreground" />
            <p className="mt-3 text-sm font-medium">
              {isDragActive ? "Drop files here" : "Drag files here"}
            </p>
            <p className="text-xs text-muted-foreground">or click to select files</p>
            <div className="mt-3 flex flex-wrap items-center justify-center gap-1 text-xs text-muted-foreground">
              {currentFormat.extensions.map((ext) => (
                <span key={ext} className="rounded bg-muted px-2 py-0.5">{ext}</span>
              ))}
            </div>
          </div>

          {/* File Requirements */}
          <div className="rounded-lg bg-muted/50 p-4">
            <p className="text-sm font-medium">Required Files:</p>
            <ul className="mt-1 space-y-1">
              {currentFormat.required.map((req) => (
                <li key={req} className="flex items-center gap-2 text-sm text-muted-foreground">
                  <span className="text-destructive">*</span> {req}
                </li>
              ))}
            </ul>
            {currentFormat.optional.length > 0 && (
              <>
                <p className="mt-2 text-sm font-medium">Optional Files:</p>
                <ul className="mt-1 space-y-1">
                  {currentFormat.optional.map((opt) => (
                    <li key={opt} className="flex items-center gap-2 text-sm text-muted-foreground">
                      <span className="text-muted-foreground">○</span> {opt}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>

          {/* Uploaded Files List */}
          {uploadedFiles.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium">Uploaded Files:</p>
              <div className="space-y-2">
                {uploadedFiles.map((file) => (
                  <div
                    key={file.id}
                    className="flex items-center justify-between gap-3 rounded-lg border border-border bg-white p-3"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      {file.status === "success" ? (
                        <CheckCircle className="h-4 w-4 shrink-0 text-green-500" />
                      ) : file.status === "error" ? (
                        <AlertCircle className="h-4 w-4 shrink-0 text-destructive" />
                      ) : (
                        <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
                      )}
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">{file.name}</p>
                        <p className="text-xs text-muted-foreground">{formatSize(file.size)}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Select
                        value={effectiveType(file)}
                        onValueChange={(v) =>
                          setFileTypeOverrides((prev) => ({ ...prev, [file.id]: v }))
                        }
                      >
                        <SelectTrigger className="h-8 w-44 text-xs" title="Specify the omics type of this file">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {FILE_TYPE_OPTIONS.map((o) => (
                            <SelectItem key={o.value} value={o.value}>
                              {o.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemoveFile(file.id)}
                      >
                        <X className="h-4 w-4 text-muted-foreground" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex flex-wrap gap-3">
            <Button data-testid="btn-use-example" variant="outline" onClick={handleUseExampleData} disabled={isLoadingExample}>
              {isLoadingExample ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileText className="mr-2 h-4 w-4" />}
              {isLoadingExample ? "Loading..." : "Use Example Data"}
            </Button>
            <Button data-testid="btn-validate" onClick={handleValidate} disabled={isUploading || uploadedFiles.length === 0}>
              {isUploading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <CheckCircle className="mr-2 h-4 w-4" />
              )}
              {isUploading ? "Uploading..." : "Validate & Upload"}
            </Button>
          </div>

          {/* Validation Status */}
          {validationStatus !== "idle" && validationStatus !== "validating" && (
            <StatusAlert
              status={validationStatus}
              title={validationStatus === "success" ? "Validation Success" : "Validation Failed"}
              description={validationMessage}
            />
          )}
        </CardContent>
      </Card>

      {/* Format Description */}
      <div className="border rounded-lg">
        <Button
          variant="ghost"
          className="w-full justify-between gap-2 text-sm px-4"
          onClick={() => setFormatOpen((prev) => !prev)}
        >
          <span className="flex items-center gap-2">
            <HelpCircle className="h-4 w-4" />
            Data Requirements &amp; Format Guide
          </span>
          {formatOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </Button>
        {formatOpen && (
          <div className="px-4 pb-4">
            <Card className="bg-muted/30 border-0">
              <CardContent className="p-4 text-sm text-muted-foreground space-y-4">
                <div className="space-y-2">
                  <p className="font-medium text-foreground">1. File formats</p>
                  <p><strong>Feature table:</strong> first row: sample names; first column: feature names (genera, metabolites, etc.); values: abundance.</p>
                  <p><strong>Metadata:</strong> first column: sample names; other columns: grouping variables, experimental conditions, etc.</p>
                  <p><strong>Taxonomy (optional):</strong> mapping between feature names and taxonomic annotations.</p>
                  <p><strong>BIOM:</strong> QIIME-generated BIOM abundance table; JSON format recommended. <strong>Mothur:</strong> .shared (OTU abundance) and .taxonomy (annotations) files.</p>
                </div>
                <div className="space-y-2">
                  <p className="font-medium text-foreground">2. Single-omics data</p>
                  <p>Each omics layer requires at least <strong>2 files</strong>: one feature table + one metadata. Before analysis the system checks whether the <strong>sample IDs match exactly</strong> between the two files:</p>
                  <ul className="list-disc pl-5 space-y-1">
                    <li>If there is no overlap at all, an error is reported asking you to fix the sample names;</li>
                    <li>If they partially match, the system automatically finds the shared sample IDs and reports the counts (N shared, M table-only, K metadata-only); downstream analyses use only the shared samples.</li>
                  </ul>
                </div>
                <div className="space-y-2">
                  <p className="font-medium text-foreground">3. Multi-omics data</p>
                  <p>Generally <strong>n × 2 files</strong> are needed (n omics layers; one feature table + one metadata each). Sample-name consistency requirements:</p>
                  <ul className="list-disc pl-5 space-y-1">
                    <li>Within each omics layer: metadata and feature table sample names must match;</li>
                    <li>Across omics layers: sample names must also match, otherwise integrative analyses (Procrustes, O2PLS, etc.) cannot run;</li>
                    <li>If you upload <strong>a single unified metadata</strong> + n feature tables, the system checks that the metadata matches the sample names of every feature table.</li>
                  </ul>
                </div>
                <div className="space-y-2">
                  <p className="font-medium text-foreground">4. Multiple metabolome tables (e.g. neg / pos)</p>
                  <p>Metabolomics may produce several feature tables (e.g. negative- and positive-ion modes); mark all of them as the metabolome type when uploading. They can be analyzed <strong>separately</strong> or <strong>merged into one feature table</strong>:</p>
                  <ul className="list-disc pl-5 space-y-1">
                    <li>Merging happens only when all tables share the exact same sample set; before merging, each table is <strong>normalized within samples</strong> (total-sum scaling per sample), then features are stacked;</li>
                    <li>Tables with different sample sets (e.g. different sampling sites) are not merged; the most recently uploaded table is used and a warning is logged.</li>
                  </ul>
                </div>
                <div className="space-y-2">
                  <p className="font-medium text-foreground">5. Multi-site multi-omics</p>
                  <p>For different sampling sites (e.g. saliva, urine), provide files <strong>paired per site</strong> (each site's own feature table + metadata). Sample names do not need to match across sites, but must be consistent within each table before cross-site comparison.</p>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>

      {/* Bottom Navigation */}
      <div className="flex items-center justify-between pt-4">
        <Button variant="outline" onClick={() => navigate("/")}>
          Previous: Home
        </Button>
        <Button
          data-testid="btn-proceed-inspection"
          onClick={() => {
            setUploadFormat(selectedFormat);
            navigate("/inspection");
          }}
          disabled={uploadedFiles.length === 0}
        >
          Proceed to Inspection
          <ArrowRight className="ml-2 h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
