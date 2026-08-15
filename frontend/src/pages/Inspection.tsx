import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { ArrowRight, ArrowLeft, CheckCircle, XCircle, AlertTriangle, FileBarChart } from "lucide-react";
import { cn } from "@/lib/utils";
import { DataCard } from "@/components/shared/DataCard";
import { PlotlyChart } from "@/components/shared/PlotlyChart";
import type { PlotlyFigure } from "@/types";
import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry } from "ag-grid-community";

ModuleRegistry.registerModules([AllCommunityModule]);

export function Inspection() {
  const navigate = useNavigate();

  const [removeConstant, setRemoveConstant] = useState(false);
  const [removeSingleton, setRemoveSingleton] = useState<"none" | "one-sample" | "one-total">("none");
  const [stats, setStats] = useState({
    dataType: "Species Abundance Table",
    samples: 34,
    features: 2920,
    totalReads: 180573,
    avgReads: 5310,
    sampleMatch: true,
    normalized: false,
    factors: 7,
  });

  const handleUpdateOverview = () => {
    // Simulate update based on filter params
    const newFeatures = removeConstant ? stats.features - 120 : stats.features;
    setStats((prev) => ({ ...prev, features: removeSingleton !== "none" ? newFeatures - 45 : newFeatures }));
  };

  const librarySizeFigure: PlotlyFigure = useMemo(() => {
    const sampleNames = Array.from({ length: 34 }, (_, i) => `Sample_${String(i + 1).padStart(2, "0")}`);
    const sizes = sampleNames.map(() => Math.floor(Math.random() * 8000) + 2000);
    return {
      data: [
        {
          x: sampleNames,
          y: sizes,
          type: "bar",
          marker: { color: "#1e40af" },
          name: "Library Size",
        },
      ],
      layout: {
        title: { text: "Library Size Distribution", font: { size: 16 } },
        xaxis: { title: "Sample", tickangle: -45 },
        yaxis: { title: "Reads" },
        height: 400,
      },
    };
  }, []);

  const metadataColumns = useMemo(
    () => [
      { field: "sample" as const, headerName: "Sample", width: 120 },
      { field: "group" as const, headerName: "Group", width: 100 },
      { field: "treatment" as const, headerName: "Treatment", width: 120 },
      { field: "age" as const, headerName: "Age", width: 80 },
      { field: "gender" as const, headerName: "Gender", width: 100 },
      { field: "bmi" as const, headerName: "BMI", width: 90 },
      { field: "location" as const, headerName: "Location", width: 130 },
    ],
    []
  );

  const metadataRows = useMemo(
    () => [
      { sample: "Sample_01", group: "Control", treatment: "A", age: 24, gender: "M", bmi: 22.5, location: "Beijing" },
      { sample: "Sample_02", group: "Treatment", treatment: "B", age: 30, gender: "F", bmi: 24.1, location: "Shanghai" },
      { sample: "Sample_03", group: "Control", treatment: "A", age: 28, gender: "M", bmi: 21.8, location: "Beijing" },
      { sample: "Sample_04", group: "Treatment", treatment: "B", age: 35, gender: "F", bmi: 26.3, location: "Guangzhou" },
      { sample: "Sample_05", group: "Treatment", treatment: "C", age: 29, gender: "M", bmi: 23.7, location: "Shanghai" },
    ],
    []
  );

  return (
    <div className={cn("mx-auto max-w-5xl space-y-6")}>
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Data Integrity Check</h1>
        <p className="text-muted-foreground">Review data quality and sample matching before filtering</p>
      </div>

      {/* Quick Filter Params */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Quick Filter</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-6">
            <div className="flex items-center gap-2">
              <Checkbox
                id="remove-constant"
                checked={removeConstant}
                onCheckedChange={(checked) => setRemoveConstant(checked === true)}
              />
              <Label htmlFor="remove-constant" className="cursor-pointer">
                Remove constant features (same value across all samples)
              </Label>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">Remove Singletons:</span>
              <RadioGroup
                value={removeSingleton}
                onValueChange={(v) => setRemoveSingleton(v as typeof removeSingleton)}
                className="flex items-center gap-4"
              >
                <div className="flex items-center gap-1.5">
                  <RadioGroupItem value="none" id="singleton-none" />
                  <Label htmlFor="singleton-none" className="cursor-pointer text-sm">None</Label>
                </div>
                <div className="flex items-center gap-1.5">
                  <RadioGroupItem value="one-sample" id="singleton-one-sample" />
                  <Label htmlFor="singleton-one-sample" className="cursor-pointer text-sm">One sample</Label>
                </div>
                <div className="flex items-center gap-1.5">
                  <RadioGroupItem value="one-total" id="singleton-one-total" />
                  <Label htmlFor="singleton-one-total" className="cursor-pointer text-sm">One total count</Label>
                </div>
              </RadioGroup>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={handleUpdateOverview}>
            <FileBarChart className="mr-2 h-4 w-4" />
            Update Overview
          </Button>
        </CardContent>
      </Card>

      {/* Data Overview Stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <DataCard title="Data Type" value={stats.dataType} badge="Species Abundance" badgeVariant="default" />
        <DataCard title="Samples" value={stats.samples} description="Samples" />
        <DataCard title="Features" value={stats.features.toLocaleString()} description="Features (OTUs/ASVs)" />
        <DataCard title="Total Reads" value={stats.totalReads.toLocaleString()} description="Total reads" />
        <DataCard title="Avg Reads/Sample" value={stats.avgReads.toLocaleString()} description="Reads per sample" />
        <DataCard
          title="Sample Name Matching"
          value={stats.sampleMatch ? "Matched" : "Not Matched"}
          badge={stats.sampleMatch ? "✓ Yes" : "✗ No"}
          badgeVariant={stats.sampleMatch ? "default" : "destructive"}
          icon={stats.sampleMatch ? <CheckCircle className="h-4 w-4 text-green-500" /> : <XCircle className="h-4 w-4 text-destructive" />}
        />
        <DataCard
          title="Normalization Check"
          value={stats.normalized ? "Normalized" : "Raw Counts"}
          badge={stats.normalized ? "✓ Yes" : "⚠ No"}
          badgeVariant={stats.normalized ? "default" : "secondary"}
          icon={stats.normalized ? <CheckCircle className="h-4 w-4 text-green-500" /> : <AlertTriangle className="h-4 w-4 text-accent" />}
        />
        <DataCard title="Experimental Factors" value={stats.factors} description="Factors in metadata" />
      </div>

      {/* Library Size Chart */}
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

      {/* Metadata Preview */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Metadata Overview (First 5 Rows)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="ag-theme-quartz" style={{ height: 220 }}>
            <AgGridReact
              rowData={metadataRows}
              columnDefs={metadataColumns}
              defaultColDef={{ sortable: true, resizable: true }}
              pagination={false}
              domLayout="autoHeight"
            />
          </div>
        </CardContent>
      </Card>

      {/* Bottom Navigation */}
      <div className="flex items-center justify-between pt-4">
        <Button variant="outline" onClick={() => navigate("/upload")}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Previous: Upload
        </Button>
        <Button onClick={() => navigate("/filter")}>
          Proceed to Filter
          <ArrowRight className="ml-2 h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
