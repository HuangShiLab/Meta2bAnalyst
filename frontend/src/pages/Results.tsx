import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { PlotlyChart } from "@/components/shared/PlotlyChart";
import { useSessionStore } from "@/stores/sessionStore";
import { downloadFigure, downloadCSV } from "@/utils/api";
import api from "@/utils/api";
import type { AnalysisHistoryItem } from "@/types";
import {
  Image as ImageIcon,
  FileSpreadsheet,
  FileText,
  Trash2,
  BarChart3,
  Dna,
  Network,
  BrainCircuit,
  Layers,
  GitBranch,
  CheckCircle,
  XCircle,
  Loader2,
  Clock,
  FileOutput,
} from "lucide-react";
import { cn } from "@/lib/utils";

const typeIcons: Record<string, React.ReactNode> = {
  "Alpha Diversity": <BarChart3 className="h-4 w-4" />,
  "Beta Diversity": <Dna className="h-4 w-4" />,
  "Differential Analysis": <GitBranch className="h-4 w-4" />,
  "Heatmap": <Layers className="h-4 w-4" />,
  "Network": <Network className="h-4 w-4" />,
  "Machine Learning": <BrainCircuit className="h-4 w-4" />,
  "Strain Composition": <Layers className="h-4 w-4" />,
  "Strain Alpha": <BarChart3 className="h-4 w-4" />,
  "Strain Beta": <Dna className="h-4 w-4" />,
  "Strain Differential": <GitBranch className="h-4 w-4" />,
  "Strain Network": <Network className="h-4 w-4" />,
};

const statusIcons = {
  running: <Loader2 className="h-4 w-4 animate-spin text-primary" />,
  success: <CheckCircle className="h-4 w-4 text-green-500" />,
  error: <XCircle className="h-4 w-4 text-red-500" />,
};

function formatTime(isoString: string) {
  const date = new Date(isoString);
  return date.toLocaleString();
}

function ResultDetail({ item }: { item: AnalysisHistoryItem }) {
  if (!item.plotData && !item.statistics && !item.tableData) {
    return (
      <div className="flex items-center justify-center h-48 text-muted-foreground">
        <p>No detailed result data available for this analysis.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {item.plotData && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg">Chart</CardTitle>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" className="gap-1" onClick={() => downloadFigure(item.plotData!, 'png')}>
                  <ImageIcon className="h-3.5 w-3.5" /> PNG
                </Button>
                <Button variant="outline" size="sm" className="gap-1" onClick={() => downloadFigure(item.plotData!, 'svg')}>
                  <ImageIcon className="h-3.5 w-3.5" /> SVG
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="h-[400px] w-full">
              <PlotlyChart
                figure={{
                  data: (item.plotData?.data || []) as never[],
                  layout: item.plotData?.layout || {},
                }}
                className="h-full"
              />
            </div>
          </CardContent>
        </Card>
      )}

      {item.statistics && Object.keys(item.statistics).length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-lg">Statistics</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-4">
              {Object.entries(item.statistics).map(([key, value]) => (
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

      {item.tableData && item.tableData.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg">Data Table</CardTitle>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" className="gap-1" onClick={() => downloadCSV(item.tableData!, 'data.csv')}>
                  <FileSpreadsheet className="h-3.5 w-3.5" /> CSV
                </Button>
                <Button variant="outline" size="sm" className="gap-1" onClick={() => downloadChunkedCSV(item.tableData!, 'data-large.csv')}>
                  <FileSpreadsheet className="h-3.5 w-3.5" /> Chunked CSV
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <PaginatedTable data={item.tableData} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function PaginatedTable({ data }: { data: Record<string, string | number>[] }) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const totalPages = Math.ceil(data.length / pageSize);
  const start = (page - 1) * pageSize;
  const end = start + pageSize;
  const pageData = data.slice(start, end);
  const columns = Object.keys(data[0]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>
          Showing {start + 1}-{Math.min(end, data.length)} of {data.length} rows
        </span>
        <div className="flex items-center gap-2">
          <span>Rows per page:</span>
          <select
            className="border rounded px-2 py-1 text-xs"
            value={pageSize}
            onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
          >
            <option value={10}>10</option>
            <option value={25}>25</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
          </select>
        </div>
      </div>
      <div className="overflow-auto max-h-96">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b">
              {columns.map((col) => (
                <th key={col} className="text-left px-3 py-2 font-medium text-muted-foreground">{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageData.map((row, i) => (
              <tr key={i} className="border-b last:border-0 hover:bg-muted/50">
                {columns.map((col) => (
                  <td key={col} className="px-3 py-2 font-mono text-xs">{String(row[col] ?? '')}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-center gap-2 pt-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page <= 1}
        >
          Previous
        </Button>
        <span className="text-sm text-muted-foreground">
          Page {page} of {totalPages}
        </span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          disabled={page >= totalPages}
        >
          Next
        </Button>
      </div>
    </div>
  );
}

/** Download large CSV in chunks using Blob streaming */
function downloadChunkedCSV(data: Record<string, string | number>[], filename: string, chunkSize = 1000) {
  if (!data || data.length === 0) return;
  const headers = Object.keys(data[0]);
  const totalRows = data.length;
  let processed = 0;
  let csvContent = headers.join(',') + '\n';

  const processChunk = () => {
    const end = Math.min(processed + chunkSize, totalRows);
    const chunk = data.slice(processed, end);
    const chunkCSV = chunk
      .map((row) => headers.map((h) => {
        const val = row[h];
        const str = String(val ?? '');
        // Escape quotes and wrap in quotes if contains comma or quote
        if (str.includes(',') || str.includes('"') || str.includes('\n')) {
          return '"' + str.replace(/"/g, '""') + '"';
        }
        return str;
      }).join(','))
      .join('\n');
    csvContent += chunkCSV + '\n';
    processed = end;

    if (processed < totalRows) {
      // Yield to UI thread
      setTimeout(processChunk, 0);
    } else {
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  };

  processChunk();
}

export function Results() {
  const sessionStore = useSessionStore();
  const history = sessionStore.analysisHistory || [];
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const selectedItem = history.find((item) => item.id === selectedId) || (history.length > 0 ? history[0] : null);
  const displayItem = selectedItem || null;

  const handleExportReport = () => {
    setExporting(true);
    setTimeout(() => {
      setExporting(false);
      const blob = new Blob(
        [`Meta2bAnalyst Analysis Report\nGenerated: ${new Date().toLocaleString()}\n\n${history.length} analyses performed.\n\n` + history.map((h, i) => `${i + 1}. ${h.type} - ${h.label} (${h.status})`).join('\n')],
        { type: 'text/plain' }
      );
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'meta2banalyst-report.txt';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }, 1500);
  };

  const handleRemoveItem = (id: string) => {
    sessionStore.removeAnalysisHistoryItem(id);
    if (selectedId === id) {
      setSelectedId(null);
    }
  };

  return (
    <div className={cn("space-y-6")}>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Results</h1>
          <p className="text-muted-foreground">
            View and export all analysis results
          </p>
        </div>
        <Button
          onClick={handleExportReport}
          disabled={exporting || history.length === 0}
          className="gap-2"
        >
          {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileOutput className="h-4 w-4" />}
          {exporting ? "Generating..." : "Download Report"}
        </Button>
        <Button 
          className="gap-2"
          onClick={async () => {
            try {
              const response = await api.post(`/sessions/${sessionStore.analysisResults?.summary ? 'mock-session' : 'mock-session'}/export/report`, {
                format: 'pdf',
              }, {
                responseType: 'blob',
              });
              const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
              const link = document.createElement('a');
              link.href = url;
              link.download = `Meta2bAnalyst_Report_${sessionStore.analysisResults?.summary ? 'mock-session' : 'mock-session'}.pdf`;
              document.body.appendChild(link);
              link.click();
              document.body.removeChild(link);
              window.URL.revokeObjectURL(url);
            } catch (error) {
              console.error('PDF report download failed:', error);
            }
          }}
          disabled={history.length === 0}
        >
          <FileText className="w-4 h-4" />
          Download Comprehensive Report (PDF)
        </Button>
      </div>

      {exporting && (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">Generating PDF report...</p>
          <Progress value={75} className="h-2" />
        </div>
      )}

      {history.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <FileText className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-lg font-medium text-muted-foreground">No analysis results yet</p>
            <p className="text-sm text-muted-foreground mt-1">
              Run analyses from the Species or Strain Analysis pages to see results here.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1">
            <Card className="h-[calc(100vh-280px)] min-h-[400px]">
              <CardHeader>
                <CardTitle className="text-lg">Analysis History</CardTitle>
                <CardDescription>{history.length} analyses performed</CardDescription>
              </CardHeader>
              <CardContent className="p-0">
                <ScrollArea className="h-[calc(100vh-360px)] min-h-[320px]">
                  <div className="space-y-1 px-4 pb-4">
                    {history.map((item) => {
                      const isSelected = displayItem?.id === item.id;
                      return (
                        <button
                          key={item.id}
                          onClick={() => setSelectedId(item.id)}
                          className={cn(
                            "w-full text-left rounded-lg p-3 transition-colors group",
                            isSelected
                              ? "bg-primary/10 border border-primary/20"
                              : "hover:bg-muted border border-transparent"
                          )}
                        >
                          <div className="flex items-start gap-3">
                            <div className="mt-0.5">
                              {typeIcons[item.type] || <BarChart3 className="h-4 w-4" />}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center justify-between">
                                <p className="text-sm font-medium truncate">{item.type}</p>
                                {statusIcons[item.status]}
                              </div>
                              <p className="text-xs text-muted-foreground truncate">{item.label}</p>
                              <div className="flex items-center gap-2 mt-1">
                                <Clock className="h-3 w-3 text-muted-foreground" />
                                <p className="text-xs text-muted-foreground">{formatTime(item.timestamp)}</p>
                              </div>
                            </div>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 opacity-0 group-hover:opacity-100"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleRemoveItem(item.id);
                              }}
                            >
                              <Trash2 className="h-3 w-3 text-muted-foreground" />
                            </Button>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>
          </div>

          <div className="lg:col-span-2">
            {displayItem ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-semibold">{displayItem.type}</h2>
                    <p className="text-sm text-muted-foreground">{displayItem.label}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {statusIcons[displayItem.status]}
                    <span className={cn(
                      "text-sm font-medium",
                      displayItem.status === "success" && "text-green-600",
                      displayItem.status === "error" && "text-red-600",
                      displayItem.status === "running" && "text-primary"
                    )}>
                      {displayItem.status.charAt(0).toUpperCase() + displayItem.status.slice(1)}
                    </span>
                  </div>
                </div>
                <ResultDetail item={displayItem} />
              </div>
            ) : (
              <Card className="h-full flex items-center justify-center">
                <CardContent className="py-16 text-center">
                  <BarChart3 className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                  <p className="text-muted-foreground">Select an analysis from the history to view details</p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
