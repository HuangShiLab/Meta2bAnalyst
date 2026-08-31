import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { ArrowRight, ArrowLeft, Loader2, HelpCircle, Filter, Trash2 } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useSessionStore } from "@/stores/sessionStore";
import { StatusAlert } from "@/components/shared/StatusAlert";
import { NoSessionBanner } from "@/components/shared/NoSessionBanner";
import { filterData, getInspection } from "@/utils/api";

export function FilterPage() {
  const navigate = useNavigate();
  const sessionId = useSessionStore((s) => s.sessionId);
  const { setFilterParams } = useSessionStore();

  const [minCount, setMinCount] = useState(4);
  const [countMethod, setCountMethod] = useState<"prevalence" | "mean" | "median">("prevalence");
  const [prevalence, setPrevalence] = useState(20);
  const [varianceRemove, setVarianceRemove] = useState(10);
  const [varianceBased, setVarianceBased] = useState<"iqr" | "sd" | "cv">("iqr");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [nSamples, setNSamples] = useState<number | null>(null);
  const [result, setResult] = useState<{ before: number; after: number; samplesRemoved: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    getInspection(sessionId)
      .then((d) => setNSamples(d.sample_count))
      .catch(() => setNSamples(null));
  }, [sessionId]);

  const handleSubmit = async () => {
    if (!sessionId) return;
    setIsSubmitting(true);
    setError(null);
    setResult(null);

    const filterParams = {
      removeConstantFeatures: false,
      removeSingleton: "none" as const,
      lowCountMinCount: minCount,
      lowCountMethod: countMethod,
      lowCountPrevalence: prevalence,
      lowVarianceRemoveRatio: varianceRemove,
      lowVarianceBasedOn: varianceBased,
    };

    try {
      const minSamples =
        countMethod === "prevalence" && nSamples
          ? Math.max(1, Math.round((prevalence / 100) * nSamples))
          : 1;
      const resp = await filterData(sessionId, {
        min_samples: minSamples,
        min_abundance: minCount,
        abundance_method: countMethod,
        variance_remove_ratio: varianceRemove / 100,
        variance_based: varianceBased,
      });
      setFilterParams(filterParams);
      setResult({
        before: resp.row_count_before,
        after: resp.row_count_after,
        samplesRemoved: resp.samples_removed,
      });
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Filtering failed");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReset = () => {
    setMinCount(4);
    setCountMethod("prevalence");
    setPrevalence(20);
    setVarianceRemove(10);
    setVarianceBased("iqr");
    setResult(null);
    setError(null);
  };

  return (
    <div className={cn("mx-auto max-w-3xl space-y-6")}>
      {!sessionId && <NoSessionBanner />}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Data Filtering</h1>
        <p className="text-muted-foreground">Remove low-count and low-variance features to improve analysis quality</p>
      </div>

      {error && <StatusAlert status="error" title="Filtering failed" description={error} />}
      {nSamples != null && (
        <p className="text-sm text-muted-foreground">
          Current table: {nSamples} samples. Prevalence {prevalence}% ≈ at least {Math.max(1, Math.round((prevalence / 100) * nSamples))} samples.
        </p>
      )}

      {/* Low Count Filter */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Filter className="h-5 w-5 text-primary" />
            Low-Count Filtering
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <HelpCircle className="h-4 w-4 text-muted-foreground cursor-help" />
                </TooltipTrigger>
                <TooltipContent className="max-w-xs">
                  <p>Remove features with counts below the threshold in most samples to reduce noise.</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Min Count */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-sm font-medium">Minimum Count</Label>
              <div className="flex items-center gap-2">
                <Slider
                  value={[minCount]}
                  onValueChange={(v) => setMinCount(v[0])}
                  min={1}
                  max={50}
                  step={1}
                  className="w-48"
                />
                <Input
                  type="number"
                  min={1}
                  max={50}
                  value={minCount}
                  onChange={(e) => setMinCount(Math.min(50, Math.max(1, Number(e.target.value))))}
                  className="w-16 text-center"
                />
              </div>
            </div>
          </div>

          {/* Filter Method */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">Filter Method</Label>
            <RadioGroup
              value={countMethod}
              onValueChange={(v) => setCountMethod(v as typeof countMethod)}
              className="space-y-2"
            >
              <div className="flex items-center gap-2">
                <RadioGroupItem value="prevalence" id="prevalence" />
                <Label htmlFor="prevalence" className="cursor-pointer text-sm">
                  Prevalence in samples (%)
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <RadioGroupItem value="mean" id="mean" />
                <Label htmlFor="mean" className="cursor-pointer text-sm">
                  Mean abundance value
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <RadioGroupItem value="median" id="median" />
                <Label htmlFor="median" className="cursor-pointer text-sm">
                  Median abundance value
                </Label>
              </div>
            </RadioGroup>
          </div>

          {/* Prevalence Slider (conditional) */}
          {countMethod === "prevalence" && (
            <div className="space-y-3 rounded-lg bg-muted/30 p-4">
              <div className="flex items-center justify-between">
                <Label className="text-sm font-medium">Prevalence Threshold (%)</Label>
                <div className="flex items-center gap-2">
                  <Slider
                    value={[prevalence]}
                    onValueChange={(v) => setPrevalence(v[0])}
                    min={0}
                    max={100}
                    step={1}
                    className="w-48"
                  />
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    value={prevalence}
                    onChange={(e) => setPrevalence(Math.min(100, Math.max(0, Number(e.target.value))))}
                    className="w-16 text-center"
                  />
                  <span className="text-sm text-muted-foreground">%</span>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                Features must exceed the minimum count threshold in at least {prevalence}% of samples with counts above the Minimum Count threshold to be retained.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Low Variance Filter */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Trash2 className="h-5 w-5 text-accent" />
            Low-Variance Filtering
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <HelpCircle className="h-4 w-4 text-muted-foreground cursor-help" />
                </TooltipTrigger>
                <TooltipContent className="max-w-xs">
                  <p>Remove features with the lowest variance, which typically do not provide discriminative information.</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Remove Ratio */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-sm font-medium">Removal Ratio</Label>
              <div className="flex items-center gap-2">
                <Slider
                  value={[varianceRemove]}
                  onValueChange={(v) => setVarianceRemove(v[0])}
                  min={0}
                  max={50}
                  step={1}
                  className="w-48"
                />
                <Input
                  type="number"
                  min={0}
                  max={50}
                  value={varianceRemove}
                  onChange={(e) => setVarianceRemove(Math.min(50, Math.max(0, Number(e.target.value))))}
                  className="w-16 text-center"
                />
                <span className="text-sm text-muted-foreground">%</span>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Will remove the lowest  {varianceRemove}% variance features.
            </p>
          </div>

          {/* Based On */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">Based On</Label>
            <RadioGroup
              value={varianceBased}
              onValueChange={(v) => setVarianceBased(v as typeof varianceBased)}
              className="space-y-2"
            >
              <div className="flex items-center gap-2">
                <RadioGroupItem value="iqr" id="iqr" />
                <Label htmlFor="iqr" className="cursor-pointer text-sm">
                  Inter-quantile range (IQR)
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <RadioGroupItem value="sd" id="sd" />
                <Label htmlFor="sd" className="cursor-pointer text-sm">
                  Standard deviation (SD)
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <RadioGroupItem value="cv" id="cv" />
                <Label htmlFor="cv" className="cursor-pointer text-sm">
                  Coefficient of variation (CV)
                </Label>
              </div>
            </RadioGroup>
          </div>
        </CardContent>
      </Card>

      {/* Submit & Reset */}
      <div className="flex items-center gap-3">
        <Button onClick={handleSubmit} disabled={isSubmitting}>
          {isSubmitting ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Filter className="mr-2 h-4 w-4" />
          )}
          Apply Filter
        </Button>
        <Button variant="outline" onClick={handleReset}>
          Reset
        </Button>
      </div>

      {/* Result Preview */}
      {result && (
        <StatusAlert
          status="success"
          title="Filtering Complete"
          description={`Feature count changed: ${result.before.toLocaleString()} → ${result.after.toLocaleString()} (removed ${result.before - result.after} features${result.samplesRemoved ? `, ${result.samplesRemoved} samples` : ""}). Downstream analyses will use the filtered table.`}
        />
      )}

      {/* Bottom Navigation */}
      <div className="flex items-center justify-between pt-4">
        <Button variant="outline" onClick={() => navigate("/inspection")}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Previous: Inspection
        </Button>
        <Button onClick={() => navigate("/normalize")} disabled={!result}>
          Proceed to Normalize
          <ArrowRight className="ml-2 h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
