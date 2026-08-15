import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useDropzone } from "react-dropzone";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Upload, FileType, X, CheckCircle, AlertCircle, Loader2, ChevronDown, ChevronUp, FileText, HelpCircle, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSessionStore } from "@/stores/sessionStore";
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
  const { uploadFormat, setUploadFormat, uploadedFiles, addUploadedFile, removeUploadedFile } = useSessionStore();
  const setSessionId = useSessionStore((state) => state.setSessionId);
  const [selectedFormat, setSelectedFormat] = useState<UploadFormat>(uploadFormat || "tsv");
  const [validationStatus, setValidationStatus] = useState<"idle" | "validating" | "success" | "error">("idle");
  const [validationMessage, setValidationMessage] = useState("");
  const [formatOpen, setFormatOpen] = useState(false);
  const [fileMap, setFileMap] = useState<Record<string, File>>({});
  const [isUploading, setIsUploading] = useState(false);

  const currentFormat = formatConfigs[selectedFormat];

  const classifyFile = (name: string): string => {
    const lower = name.toLowerCase();
    if (lower.includes("metadata") || lower.includes("meta") || lower.includes("sample")) return "metadata";
    if (lower.includes("metaphlan") || lower.includes("clade")) return "microbiome";
    if (lower.includes("humann3") || lower.includes("humann") || lower.includes("pathabundance") || lower.includes("genefamilies")) return "metabolome";
    if (lower.includes("microbiome") || lower.includes("microbial") || lower.includes("16s") || lower.includes("otu") || lower.includes("asv") || lower.includes("taxa")) return "microbiome";
    if (lower.includes("metabolome") || lower.includes("metabolite") || lower.includes("lcms") || lower.includes("ms")) return "metabolome";
    return "feature_table";
  };

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      acceptedFiles.forEach((file) => {
        const id = crypto.randomUUID();
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
  };

  const [isLoadingExample, setIsLoadingExample] = useState(false);

  const handleUseExampleData = async () => {
    setIsLoadingExample(true);
    try {
      // Clear previous files so example data is a clean start
      uploadedFiles.forEach((f) => removeUploadedFile(f.id));
      setFileMap({});

      const newFiles: UploadFile[] = [];
      const newFileMap: Record<string, File> = {};

      for (const filename of currentFormat.exampleFiles) {
        const response = await fetch(`/examples/${filename}`);
        if (!response.ok) {
          throw new Error(`Failed to load example file: ${filename}`);
        }
        const blob = await response.blob();
        const file = new File([blob], filename, { type: blob.type || "application/octet-stream" });
        const id = crypto.randomUUID();
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

      for (const uploadFileMeta of uploadedFiles) {
        const file = fileMap[uploadFileMeta.id];
        if (!file) continue;
        const fileType = classifyFile(uploadFileMeta.name);
        await uploadFile(sid, file, fileType);
      }

      setValidationStatus("success");
      setValidationMessage(`Data validation passed and uploaded!Session ID: ${sid}`);
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
                    className="flex items-center justify-between rounded-lg border border-border bg-white p-3"
                  >
                    <div className="flex items-center gap-3">
                      {file.status === "success" ? (
                        <CheckCircle className="h-4 w-4 text-green-500" />
                      ) : file.status === "error" ? (
                        <AlertCircle className="h-4 w-4 text-destructive" />
                      ) : (
                        <Loader2 className="h-4 w-4 animate-spin text-primary" />
                      )}
                      <div>
                        <p className="text-sm font-medium">{file.name}</p>
                        <p className="text-xs text-muted-foreground">{formatSize(file.size)}</p>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRemoveFile(file.id)}
                    >
                      <X className="h-4 w-4 text-muted-foreground" />
                    </Button>
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
            Format Guide
          </span>
          {formatOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </Button>
        {formatOpen && (
          <div className="px-4 pb-4">
            <Card className="bg-muted/30 border-0">
              <CardContent className="p-4 text-sm text-muted-foreground space-y-2">
                <p><strong>Feature table:</strong> First row: sample names; First column: feature names; Values: abundance counts.</p>
                <p><strong>Metadata:</strong> First row: sample names; Subsequent columns: grouping variables, experimental conditions, etc.</p>
                <p><strong>Taxonomy (optional):</strong> Contains mapping between feature names and taxonomic annotations.</p>
                <p><strong>BIOM:</strong> QIIME-generated BIOM format abundance table; JSON format recommended.</p>
                <p><strong>Mothur:</strong> .shared file contains OTU abundance table; .taxonomy file contains taxonomic annotations.</p>
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
