/**
 * Data Upload — a thin shell around the shared DataSourceSelector.
 *
 * The page used to own its own upload chain (six pipeline formats, filename
 * classification, session creation), which drifted from every other page's
 * wiring. The old six-format selection now lives inside the selector as the
 * microbiome pipeline level, and per-pipeline example files are staged from
 * the selector's "Load example files for this pipeline" button. See
 * docs/data-source-selector-design.md step "Upload page shell".
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
  microbiome: "Microbiome table",
  metabolome: "Metabolome table",
  strain: "Strain table",
  function: "Functional gene table",
  metadata: "Metadata",
  taxonomy: "Taxonomy",
};

/** Nothing is forced here — the shell accepts any combination. The two most
 *  common types are pre-selected so a bare drop works out of the box. */
const OPEN_REQUIREMENTS = [
  { type: "microbiome" as DataType, label: "Microbiome abundance table", required: false },
  { type: "metadata" as DataType, label: "Grouping metadata", required: false },
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
          Pick the data type first, then upload — every file gets an explicit type label
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
              Data Ready
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
            <p className="text-xs text-muted-foreground">Session ID: {ready.sid}</p>
            <div className="flex flex-wrap gap-2">
              <Button asChild size="sm">
                <Link to="/microbiome">
                  Microbiome Analysis <ArrowRight className="ml-1 h-3.5 w-3.5" />
                </Link>
              </Button>
              <Button asChild size="sm" variant="outline">
                <Link to="/strain">Strain Analysis</Link>
              </Button>
              <Button asChild size="sm" variant="outline">
                <Link to="/inspect">Data Inspection</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
