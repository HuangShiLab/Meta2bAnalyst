/**
 * DataSourceSelector — shared data-entry component for analysis modules.
 *
 * One implementation of the data chain (type selection → upload → session),
 * embedded per module instead of every page wiring its own upload flow
 * (docs/data-source-selector-design.md). Four sources:
 *
 *   current session | upload now | example data | my library (phase 2)
 *
 * The upload tab asks "what kind of data is this?" FIRST — the answer is the
 * file_type sent to the backend, so metabolome/strain tables no longer ride
 * the generic TSV/CSV path with a guessed label. Filename heuristics only
 * pre-select the per-file badge, which the user can correct.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Loader2, UploadCloud, Database, FlaskConical, FolderOpen, X } from "lucide-react";
import { api, createSession, uploadFile } from "@/utils/api";
import { DEMO_DATASETS, loadDemoDataset, type DemoDataset } from "@/lib/demoDatasets";
import { useSessionStore } from "@/stores/sessionStore";
import { cn } from "@/lib/utils";

export type DataType = "microbiome" | "metabolome" | "strain" | "function" | "metadata" | "taxonomy";

export interface FileRequirement {
  type: DataType;
  label: string;
  required: boolean;
  formats?: string[];
}

export interface DataSourceSelectorProps {
  /** What this module needs; drives defaults and the readiness check. */
  requires: FileRequirement[];
  sessionId: string | null;
  /** Fired when a session with satisfactory data exists (new or confirmed). */
  onSessionReady: (sessionId: string, files: { name: string; type: string }[]) => void;
  /** inline: borderless embed inside a module page (default panel). */
  variant?: "panel" | "inline";
}

interface StagedFile {
  id: string;
  file: File;
  type: DataType;
}

interface SessionFile {
  file_id: number;
  file_type: string;
  original_name: string;
  file_size: number;
  row_count: number | null;
}

const DATA_TYPES: Record<DataType, { label: string; hint: string; formats: string[] }> = {
  microbiome: {
    label: "微生物组丰度表",
    hint: "属/种水平丰度表（各流程输出或通用表）",
    formats: [".csv", ".tsv", ".txt", ".biom", ".shared"],
  },
  metabolome: { label: "代谢组丰度表", hint: "代谢物 × 样本丰度矩阵", formats: [".csv", ".tsv", ".txt"] },
  strain: { label: "菌株丰度表", hint: "Strain2bScan 输出 / Tag2bMap 映射", formats: [".csv", ".tsv"] },
  function: { label: "功能基因表", hint: "功能基因丰度表", formats: [".csv", ".tsv"] },
  metadata: { label: "分组元数据", hint: "样本 ID + 分组/表型变量", formats: [".csv", ".tsv", ".txt"] },
  taxonomy: { label: "物种注释表", hint: "特征 → 分类层级注释", formats: [".csv", ".tsv"] },
};

const TYPE_BADGE: Record<DataType, string> = {
  microbiome: "bg-teal-100 text-teal-800",
  metabolome: "bg-violet-100 text-violet-800",
  strain: "bg-amber-100 text-amber-800",
  function: "bg-sky-100 text-sky-800",
  metadata: "bg-slate-200 text-slate-800",
  taxonomy: "bg-rose-100 text-rose-800",
};

/** Filename heuristic — ONLY a badge default, never a silent decision. */
function guessType(name: string): DataType | null {
  const lower = name.toLowerCase();
  if (lower.includes("metadata") || lower.includes("sample")) return "metadata";
  if (lower.includes("taxonomy")) return "taxonomy";
  if (lower.includes("strain") || lower.includes("2bscan") || lower.includes("tag2bmap")) return "strain";
  if (lower.includes("metabol") || lower.includes("lcms")) return "metabolome";
  if (lower.includes("humann") || lower.includes("pathabundance")) return "function";
  if (lower.includes("metaphlan") || lower.includes("otu") || lower.includes("asv")) return "microbiome";
  return null;
}

const MICROBIOME_PIPELINES = [
  { id: "generic", label: "通用 TSV/CSV" },
  { id: "2brad-m", label: "2bRAD-M" },
  { id: "qiime", label: "QIIME 2 / BIOM" },
  { id: "mothur", label: "Mothur" },
  { id: "metaphlan", label: "MetaPhlAn" },
  { id: "humann3", label: "HUMAnN3" },
];

function requirementsMet(types: string[], requires: FileRequirement[]): boolean {
  return requires.filter((r) => r.required).every((r) => types.includes(r.type));
}

export function DataSourceSelector({ requires, sessionId, onSessionReady, variant = "panel" }: DataSourceSelectorProps) {
  const setStoreSessionId = useSessionStore((s) => s.setSessionId);
  const [source, setSource] = useState<"current" | "upload" | "demo">(sessionId ? "current" : "upload");

  // ── current-session listing ─────────────────────────────────────────────
  const [sessionFiles, setSessionFiles] = useState<SessionFile[] | null>(null);
  const [filesLoading, setFilesLoading] = useState(false);

  useEffect(() => {
    if (source !== "current" || !sessionId) return;
    let cancelled = false;
    setFilesLoading(true);
    api
      .get(`/sessions/${sessionId}/files`)
      .then((r) => { if (!cancelled) setSessionFiles(r.data?.files ?? []); })
      .catch(() => { if (!cancelled) setSessionFiles([]); })
      .finally(() => { if (!cancelled) setFilesLoading(false); });
    return () => { cancelled = true; };
  }, [source, sessionId]);

  // ── upload tab state ────────────────────────────────────────────────────
  const defaultTypes = useMemo(
    () => Array.from(new Set(requires.map((r) => r.type))),
    [requires]
  );
  const [selectedTypes, setSelectedTypes] = useState<DataType[]>(defaultTypes);
  const [pipeline, setPipeline] = useState("generic");
  const [staged, setStaged] = useState<StagedFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState<{ done: number; total: number } | null>(null);

  const acceptExtensions = useMemo(() => {
    const exts = new Set<string>();
    selectedTypes.forEach((t) => DATA_TYPES[t].formats.forEach((f) => exts.add(f)));
    return { "application/octet-stream": Array.from(exts), "text/csv": [".csv"], "text/tab-separated-values": [".tsv", ".txt"] };
  }, [selectedTypes]);

  const onDrop = useCallback(
    (accepted: File[]) => {
      const primary = selectedTypes[0] ?? "microbiome";
      setStaged((prev) => [
        ...prev,
        ...accepted.map((file) => {
          const guessed = guessType(file.name);
          // Only honour the guess when it is one of the types the user said
          // these files are; otherwise the explicit selection wins.
          const type = guessed && selectedTypes.includes(guessed) ? guessed : primary;
          return { id: `${file.name}-${file.size}-${Math.random().toString(36).slice(2, 8)}`, file, type };
        }),
      ]);
      setUploadError(null);
    },
    [selectedTypes]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, accept: acceptExtensions });

  const stagedTypes = staged.map((s) => s.type as string);
  const stagedReady = staged.length > 0 && requirementsMet(stagedTypes, requires);
  const missingTypes = requires.filter((r) => r.required && !stagedTypes.includes(r.type)).map((r) => DATA_TYPES[r.type].label);

  const handleUpload = async () => {
    setUploading(true);
    setUploadError(null);
    setUploadProgress({ done: 0, total: staged.length });
    try {
      const session = await createSession({
        name: `Data ${new Date().toLocaleString()}`,
        data_format: pipeline === "generic" ? "tsv" : pipeline,
      });
      const uploaded: { name: string; type: string }[] = [];
      for (let i = 0; i < staged.length; i++) {
        setUploadProgress({ done: i, total: staged.length });
        // .biom/.shared keep their backend-native types
        const lower = staged[i].file.name.toLowerCase();
        let fileType: string = staged[i].type;
        if (lower.endsWith(".biom")) fileType = "biom";
        if (lower.endsWith(".shared")) fileType = "shared";
        await uploadFile(session.id, staged[i].file, fileType);
        uploaded.push({ name: staged[i].file.name, type: fileType });
      }
      setUploadProgress({ done: staged.length, total: staged.length });
      setStaged([]);
      setStoreSessionId(session.id);
      setSource("current");
      onSessionReady(session.id, uploaded);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setUploadError(`上传失败：${message}`);
    } finally {
      setUploading(false);
      setUploadProgress(null);
    }
  };

  // ── demo tab state ──────────────────────────────────────────────────────
  const [demoLoading, setDemoLoading] = useState<string | null>(null);
  const [demoProgress, setDemoProgress] = useState<{ done: number; total: number; current: string } | null>(null);

  const handleDemo = async (dataset: DemoDataset) => {
    setDemoLoading(dataset.id);
    setDemoProgress({ done: 0, total: dataset.files.length, current: "" });
    try {
      const sid = await loadDemoDataset(dataset, (done, total, currentFile) =>
        setDemoProgress({ done, total, current: currentFile })
      );
      setStoreSessionId(sid);
      setSource("current");
      onSessionReady(sid, dataset.files.map((f) => ({ name: f.name, type: f.fileType })));
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setUploadError(`示例数据载入失败：${message}`);
    } finally {
      setDemoLoading(null);
      setDemoProgress(null);
    }
  };

  const currentTypes = (sessionFiles ?? []).map((f) => f.file_type);
  const currentReady = requirementsMet(currentTypes, requires);

  const body = (
    <Tabs value={source} onValueChange={(v) => setSource(v as typeof source)}>
      <TabsList className="grid w-full grid-cols-4">
        <TabsTrigger value="current" disabled={!sessionId}><FolderOpen className="mr-1 h-3.5 w-3.5" />当前会话</TabsTrigger>
        <TabsTrigger value="upload"><UploadCloud className="mr-1 h-3.5 w-3.5" />现在上传</TabsTrigger>
        <TabsTrigger value="demo"><FlaskConical className="mr-1 h-3.5 w-3.5" />示例数据</TabsTrigger>
        <TabsTrigger value="library" disabled title="二期上线"><Database className="mr-1 h-3.5 w-3.5" />我的数据</TabsTrigger>
      </TabsList>

      {/* ── current session ── */}
      <TabsContent value="current" className="mt-3 space-y-3">
        {filesLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />读取会话文件…</div>
        ) : (sessionFiles ?? []).length === 0 ? (
          <p className="text-sm text-muted-foreground">当前会话还没有文件，请切换到"现在上传"或"示例数据"。</p>
        ) : (
          <>
            <ul className="space-y-1.5">
              {(sessionFiles ?? []).map((f) => {
                const t = (f.file_type in DATA_TYPES ? f.file_type : "microbiome") as DataType;
                return (
                  <li key={f.file_id} className="flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm">
                    <Badge className={cn("border-0", TYPE_BADGE[t] ?? "bg-slate-200")}>{DATA_TYPES[t]?.label ?? f.file_type}</Badge>
                    <span className="flex-1 truncate">{f.original_name}</span>
                    {f.row_count != null && <span className="text-xs text-muted-foreground">{f.row_count} 行</span>}
                  </li>
                );
              })}
            </ul>
            <div className="flex items-center gap-3">
              <Button
                size="sm"
                disabled={!currentReady}
                onClick={() => sessionId && onSessionReady(sessionId, (sessionFiles ?? []).map((f) => ({ name: f.original_name, type: f.file_type })))}
              >
                使用当前数据
              </Button>
              {!currentReady && (
                <p className="text-xs text-amber-700">
                  缺少：{requires.filter((r) => r.required && !currentTypes.includes(r.type)).map((r) => DATA_TYPES[r.type].label).join("、")}
                </p>
              )}
            </div>
          </>
        )}
      </TabsContent>

      {/* ── upload now: two-level selection ── */}
      <TabsContent value="upload" className="mt-3 space-y-4">
        <div>
          <p className="mb-2 text-sm font-medium">① 这是什么数据？（决定文件标注，不再靠文件名猜）</p>
          <div className="flex flex-wrap gap-3">
            {(Object.keys(DATA_TYPES) as DataType[]).map((t) => (
              <label key={t} className="flex items-start gap-1.5 rounded-md border px-2.5 py-1.5 text-sm">
                <Checkbox
                  checked={selectedTypes.includes(t)}
                  onCheckedChange={(checked) =>
                    setSelectedTypes((prev) => (checked ? [...new Set([...prev, t])] : prev.filter((x) => x !== t)))
                  }
                />
                <span>
                  {DATA_TYPES[t].label}
                  <span className="block text-xs text-muted-foreground">{DATA_TYPES[t].hint}</span>
                </span>
              </label>
            ))}
          </div>
        </div>

        {selectedTypes.includes("microbiome") && (
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium">② 微生物组表来自哪个流程？</p>
            <Select value={pipeline} onValueChange={setPipeline}>
              <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
              <SelectContent>
                {MICROBIOME_PIPELINES.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        <div
          {...getRootProps()}
          className={cn(
            "flex cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed p-6 text-center",
            isDragActive ? "border-primary bg-primary/5" : "border-border"
          )}
        >
          <input {...getInputProps()} />
          <UploadCloud className="h-6 w-6 text-muted-foreground" />
          <p className="text-sm">拖入文件，或点击选择</p>
          <p className="text-xs text-muted-foreground">
            接受：{selectedTypes.map((t) => DATA_TYPES[t].label).join(" + ")}
          </p>
        </div>

        {staged.length > 0 && (
          <ul className="space-y-1.5">
            {staged.map((s) => (
              <li key={s.id} className="flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm">
                <Select
                  value={s.type}
                  onValueChange={(v) => setStaged((prev) => prev.map((x) => (x.id === s.id ? { ...x, type: v as DataType } : x)))}
                >
                  <SelectTrigger className="h-7 w-36 border-0 shadow-none">
                    <Badge className={cn("border-0", TYPE_BADGE[s.type])}>{DATA_TYPES[s.type].label}</Badge>
                  </SelectTrigger>
                  <SelectContent>
                    {(Object.keys(DATA_TYPES) as DataType[]).map((t) => (
                      <SelectItem key={t} value={t}>{DATA_TYPES[t].label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <span className="flex-1 truncate">{s.file.name}</span>
                <span className="text-xs text-muted-foreground">{(s.file.size / 1024).toFixed(0)} KB</span>
                <button onClick={() => setStaged((prev) => prev.filter((x) => x.id !== s.id))} className="text-muted-foreground hover:text-destructive">
                  <X className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}

        {uploadError && <p className="text-sm text-destructive">{uploadError}</p>}
        {uploadProgress && (
          <div className="space-y-1">
            <Progress value={(uploadProgress.done / Math.max(uploadProgress.total, 1)) * 100} />
            <p className="text-xs text-muted-foreground">上传中 {uploadProgress.done}/{uploadProgress.total}…</p>
          </div>
        )}

        <div className="flex items-center gap-3">
          <Button size="sm" disabled={!stagedReady || uploading} onClick={handleUpload}>
            {uploading && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
            上传并使用
          </Button>
          {staged.length > 0 && !stagedReady && missingTypes.length > 0 && (
            <p className="text-xs text-amber-700">还需要：{missingTypes.join("、")}</p>
          )}
        </div>
      </TabsContent>

      {/* ── example data ── */}
      <TabsContent value="demo" className="mt-3 space-y-3">
        <div className="grid gap-2 sm:grid-cols-2">
          {DEMO_DATASETS.map((d) => (
            <button
              key={d.id}
              onClick={() => handleDemo(d)}
              disabled={demoLoading !== null}
              className={cn(
                "rounded-lg border p-3 text-left transition-colors hover:border-primary/50",
                demoLoading === d.id && "border-primary"
              )}
            >
              <p className="text-sm font-medium">{d.label}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">{d.description}</p>
              <p className="mt-1 text-xs text-muted-foreground">{d.files.length} 个文件 · 一键载入</p>
              {demoLoading === d.id && demoProgress && (
                <div className="mt-2 space-y-1">
                  <Progress value={(demoProgress.done / Math.max(demoProgress.total, 1)) * 100} />
                  <p className="text-xs text-muted-foreground">载入 {demoProgress.done}/{demoProgress.total}…</p>
                </div>
              )}
            </button>
          ))}
        </div>
      </TabsContent>
    </Tabs>
  );

  if (variant === "inline") return body;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">数据来源</CardTitle>
      </CardHeader>
      <CardContent>{body}</CardContent>
    </Card>
  );
}
