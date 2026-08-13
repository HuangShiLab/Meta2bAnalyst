import { lazy, Suspense } from "react";
import { cn } from "@/lib/utils";
import type { PlotlyFigure } from "@/types";

const Plot = lazy(() => import("react-plotly.js"));

interface PlotlyChartProps {
  figure: PlotlyFigure;
  className?: string;
  style?: React.CSSProperties;
}

export function PlotlyChart({ figure, className, style }: PlotlyChartProps) {
  return (
    <div className={cn("w-full", className)} style={style}>
      <Suspense
        fallback={
          <div className="flex h-64 items-center justify-center rounded-lg border border-border bg-muted">
            <div className="text-sm text-muted-foreground">Loading chart...</div>
          </div>
        }
      >
        <Plot
          data={figure.data as never[]}
          layout={{
            ...figure.layout,
            autosize: true,
            margin: { t: 40, r: 20, b: 40, l: 60 },
          }}
          useResizeHandler
          style={{ width: "100%", height: "100%", ...style }}
          config={{
            responsive: true,
            displayModeBar: true,
            displaylogo: false,
          }}
        />
      </Suspense>
    </div>
  );
}
