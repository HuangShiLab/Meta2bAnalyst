import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ArrowRight, ArrowLeft, CheckCircle, XCircle, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { DataCard } from "@/components/shared/DataCard";
import { PlotlyChart } from "@/components/shared/PlotlyChart";
import { NoSessionBanner } from "@/components/shared/NoSessionBanner";
import { StatusAlert } from "@/components/shared/StatusAlert";
import type { PlotlyFigure } from "@/types";
import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry } from "ag-grid-community";
import { useSessionStore } from "@/stores/sessionStore";
import { getInspection, type InspectionResponse } from "@/utils/api";

ModuleRegistry.registerModules([AllCommunityModule]);

export function Inspection() {
  const navigate = useNavigate();
  const sessionId = useSessionStore((s) => s.sessionId);

  const [data, setData] = useState<InspectionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    getInspection(sessionId)
      .then(setData)
      .catch((e) => {
        const detail = e?.response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load inspection data");
      })
      .finally(() => setLoading(false));
  }, [sessionId]);

  const librarySizeFigure: PlotlyFigure | null = useMemo(() => {
    if (!data?.library_sizes) return null;
    const entries = Object.entries(data.library_sizes);
    return {
      data: [
        {
          x: entries.map(([k]) => k),
          y: entries.map(([, v]) => v),
          type: "bar",
          marker: { color: "#1e40af" },
          name: "Library Size",
        },
      ],
      layout: {
        title: { text: "Library Size Distribution", font: { size: 16 } },
        xaxis: { title: "Sample", tickangle: -45, automargin: true },
        yaxis: { title: "Total Abundance / Reads" },
        height: 400,
      },
    };
  }, [data]);

  const previewColumns = useMemo(() => {
    if (!data?.preview?.length) return [];
    return Object.keys(data.preview[0]).map((k) => ({
      field: k,
      headerName: k,
      width: 130,
    }));
  }, [data]);

  const meta = data?.metadata;
  const sampleMatched = meta ? (meta.matched_samples ?? 0) > 0 && meta.match_ratio === 1 : null;

  return (
    <div className={cn("mx-auto max-w-5xl space-y-6")}>
      {!sessionId && <NoSessionBanner />}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Data Integrity Check</h1>
        <p className="text-muted-foreground">Review data quality and sample matching before filtering</p>
      </div>

      {error && <StatusAlert status="error" title="Inspection failed" description={error} />}
      {loading && <p className="text-sm text-muted-foreground">Loading inspection data…</p>}

      {data && (
        <>
          {/* Data Overview Stats — all from the real uploaded feature table */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <DataCard title="Data Type" value={data.file_type} badge="Feature Table" badgeVariant="default" />
            <DataCard title="Samples" value={data.sample_count} description="Samples" />
            <DataCard title="Features" value={data.feature_count.toLocaleString()} description="Features (OTUs/ASVs/genera)" />
            <DataCard title="Total Reads" value={Math.round(data.summary.total_reads).toLocaleString()} description="Sum over all samples" />
            <DataCard title="Avg Reads/Sample" value={Math.round(data.summary.mean_reads_per_sample).toLocaleString()} description={`Median ${Math.round(data.summary.median_reads_per_sample).toLocaleString()}`} />
            <DataCard
              title="Sparsity"
              value={`${(data.summary.sparsity * 100).toFixed(1)}%`}
              description="Zero fraction of the matrix"
            />
            <DataCard
              title="Sample Name Matching"
              value={
                meta == null
                  ? "No metadata"
                  : meta.error
                    ? "Parse error"
                    : `${meta.matched_samples}/${meta.table_samples} matched`
              }
              badge={meta == null ? "—" : sampleMatched ? "✓ 100%" : `✗ ${((meta.match_ratio ?? 0) * 100).toFixed(0)}%`}
              badgeVariant={meta != null && !meta.error && sampleMatched ? "default" : "destructive"}
              icon={
                meta != null && !meta.error && sampleMatched ? (
                  <CheckCircle className="h-4 w-4 text-green-500" />
                ) : (
                  <XCircle className="h-4 w-4 text-destructive" />
                )
              }
            />
            <DataCard
              title="Metadata Columns"
              value={meta?.n_metadata_columns ?? "—"}
              description="Variables in metadata"
            />
          </div>

          {meta && !meta.error && !sampleMatched && (
            <StatusAlert
              status="warning"
              title="Sample IDs do not fully match between feature table and metadata"
              description={`${meta.matched_samples} of ${meta.table_samples} feature-table samples were found in the metadata. Unmatched in table: ${(meta.unmatched_table_samples ?? []).slice(0, 5).join(", ") || "none"}${(meta.unmatched_table_samples?.length ?? 0) > 5 ? " …" : ""}. Unmatched in metadata: ${(meta.unmatched_metadata_samples ?? []).slice(0, 5).join(", ") || "none"}${(meta.unmatched_metadata_samples?.length ?? 0) > 5 ? " …" : ""}. Please fix the IDs and re-upload, or downstream analyses will only use the matched subset.`}
            />
          )}

          {/* Library Size Chart */}
          {librarySizeFigure && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Library Size Distribution</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-80">
                  <PlotlyChart figure={librarySizeFigure} className="h-full" />
                </div>
              </CardContent>
            </Card>
          )}

          {/* Real feature table preview */}
          {data.preview && data.preview.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Feature Table Preview (first 5 × 5)</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="ag-theme-quartz" style={{ height: 220 }}>
                  <AgGridReact
                    rowData={data.preview}
                    columnDefs={previewColumns}
                    defaultColDef={{ sortable: true, resizable: true }}
                    pagination={false}
                    domLayout="autoHeight"
                  />
                </div>
              </CardContent>
            </Card>
          )}

          {/* Top features */}
          {data.summary.top_features && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Top 10 Features by Mean Abundance</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1 text-sm">
                  {Object.entries(data.summary.top_features).map(([name, v]) => (
                    <li key={name} className="flex justify-between border-b border-muted pb-1">
                      <span className="font-mono">{name}</span>
                      <span className="text-muted-foreground">{v.toFixed(4)}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {!data && !loading && !error && sessionId && (
        <StatusAlert status="info" title="No data" description="Nothing to inspect yet." />
      )}

      {/* Bottom Navigation */}
      <div className="flex items-center justify-between pt-4">
        <Button variant="outline" onClick={() => navigate("/upload")}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Previous: Upload
        </Button>
        <Button onClick={() => navigate("/filter")} disabled={!data}>
          Proceed to Filter
          <ArrowRight className="ml-2 h-4 w-4" />
        </Button>
      </div>

      {!data && !loading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <AlertTriangle className="h-4 w-4" />
          Upload a feature table first — this page shows real statistics of your uploaded data.
        </div>
      )}
    </div>
  );
}
