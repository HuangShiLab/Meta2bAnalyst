/**
 * Data Upload — a thin shell around the shared DataSourceSelector.
 *
 * The page used to own its own upload chain (six pipeline formats, filename
 * classification, session creation), which drifted from every other page's
 * wiring. The old six-format selection now lives inside the selector as the
 * microbiome pipeline level, and per-pipeline example files are staged from
 * the selector's "载入该流程的示例文件" button. See
 * docs/data-source-selector-design.md step "Upload 页换壳".
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AlertCircle, ArrowRight, CheckCircle } from "lucide-react";
import { DataSourceSelector, type DataType } from "@/components/data/DataSourceSelector";
import { useAuthStore } from "@/stores/authStore";
import { useSessionStore } from "@/stores/sessionStore";
import { cn } from "@/lib/utils";

const TYPE_LABELS: Record<DataType, string> = {
  microbiome: "微生物组表",
  metabolome: "代谢组表",
  strain: "菌株表",
  function: "功能基因表",
  metadata: "元数据",
  taxonomy: "物种注释",
};

/** Nothing is forced here — the shell accepts any combination. The two most
 *  common types are pre-selected so a bare drop works out of the box. */
const OPEN_REQUIREMENTS = [
  { type: "microbiome" as DataType, label: "微生物组丰度表", required: false },
  { type: "metadata" as DataType, label: "分组元数据", required: false },
];

export function UploadPage() {
  const isAuthenticated = !!useAuthStore((s) => s.token);
  const sessionId = useSessionStore((s) => s.sessionId);
  const [ready, setReady] = useState<{ sid: string; files: { name: string; type: string }[] } | null>(null);

  return (
    <div className={cn("mx-auto max-w-3xl space-y-6")}>
      <div>
        <h1 data-testid="upload-title" className="text-2xl font-bold tracking-tight">Data Upload</h1>
        <p data-testid="upload-desc" className="text-muted-foreground">
          先选择数据类型，再上传文件——每个文件都会明确标注用途
        </p>
      </div>

      {!isAuthenticated && (
        <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            You are browsing as a <strong>guest</strong>. Demo datasets stay
            available on the analysis pages, but uploading your own data
            requires an account —{" "}
            <Link to="/login" className="font-medium text-primary underline">
              sign in
            </Link>{" "}
            first.
          </p>
        </div>
      )}

      <DataSourceSelector
        requires={OPEN_REQUIREMENTS}
        sessionId={sessionId}
        onSessionReady={(sid, files) => setReady({ sid, files })}
      />

      {ready && (
        <Card className="border-green-200 bg-green-50/40">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-lg">
              <CheckCircle className="h-5 w-5 text-green-600" />
              数据已就绪
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <ul className="space-y-1">
              {ready.files.map((f) => (
                <li key={f.name} className="flex items-center gap-2 text-sm">
                  <Badge variant="secondary">
                    {TYPE_LABELS[f.type as DataType] ?? f.type}
                  </Badge>
                  <span className="flex-1 truncate">{f.name}</span>
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted-foreground">会话 ID：{ready.sid}</p>
            <div className="flex flex-wrap gap-2">
              <Button asChild size="sm">
                <Link to="/microbiome">
                  微生物组分析 <ArrowRight className="ml-1 h-3.5 w-3.5" />
                </Link>
              </Button>
              <Button asChild size="sm" variant="outline">
                <Link to="/strain">菌株分析</Link>
              </Button>
              <Button asChild size="sm" variant="outline">
                <Link to="/inspect">数据检查</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
