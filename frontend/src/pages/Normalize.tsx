import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { ArrowRight, ArrowLeft, Loader2, HelpCircle, Scale, AlertTriangle } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useSessionStore } from "@/stores/sessionStore";
import { StatusAlert } from "@/components/shared/StatusAlert";

export function Normalize() {
  const navigate = useNavigate();
  const { setNormalizationParams } = useSessionStore();

  const [rarefaction, setRarefaction] = useState<"none" | "rarefy">("none");
  const [rarefactionReads, setRarefactionReads] = useState(5000);
  const [scaling, setScaling] = useState<"none" | "tss" | "css" | "uq">("tss");
  const [transformation, setTransformation] = useState<"none" | "clr" | "rle" | "tmm">("none");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showResult, setShowResult] = useState(false);

  const scalingSelected = scaling !== "none";

  const handleSubmit = async () => {
    setIsSubmitting(true);
    setShowResult(false);

    await new Promise((resolve) => setTimeout(resolve, 1000));

    setNormalizationParams({
      rarefaction,
      rarefactionReads: rarefaction === "rarefy" ? rarefactionReads : 0,
      scaling,
      transformation: scalingSelected ? "none" : transformation,
    });

    setShowResult(true);
    setIsSubmitting(false);
  };

  return (
    <div className={cn("mx-auto max-w-3xl space-y-6")}>
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Data Normalization</h1>
        <p className="text-muted-foreground">Normalize data to eliminate sequencing depth bias</p>
      </div>

      {/* Warning */}
      <StatusAlert
        status="info"
        title="Normalization Guide"
        description="All methods require raw count data as input. Scaling and Transformation are mutually exclusive; selecting Scaling will disable Transformation."
      />

      {/* Rarefaction */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Scale className="h-5 w-5 text-primary" />
            Rarefying
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <RadioGroup
            value={rarefaction}
            onValueChange={(v) => setRarefaction(v as typeof rarefaction)}
            className="space-y-3"
          >
            <div className="flex items-center gap-2">
              <RadioGroupItem value="none" id="rarefy-none" />
              <Label htmlFor="rarefy-none" className="cursor-pointer text-sm">
                No Rarefying
              </Label>
            </div>
            <div className="flex items-center gap-2">
              <RadioGroupItem value="rarefy" id="rarefy-yes" />
              <div className="flex items-center gap-3">
                <Label htmlFor="rarefy-yes" className="cursor-pointer text-sm">
                  Rarefy to
                </Label>
                <Input
                  type="number"
                  min={100}
                  max={100000}
                  value={rarefactionReads}
                  onChange={(e) => setRarefactionReads(Number(e.target.value))}
                  className="w-24 text-center"
                  disabled={rarefaction !== "rarefy"}
                />
                <span className="text-sm text-muted-foreground">reads</span>
              </div>
            </div>
          </RadioGroup>
          <p className="text-xs text-muted-foreground">
            Rarefying randomly subsamples each sample to the same read count. Not recommended for differential analysis (information loss).
          </p>
        </CardContent>
      </Card>

      {/* Scaling */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Scale className="h-5 w-5 text-secondary" />
            Scaling
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <HelpCircle className="h-4 w-4 text-muted-foreground cursor-help" />
                </TooltipTrigger>
                <TooltipContent className="max-w-xs">
                  <p>缩放将样本总读数归一化，使样本间可比。TSS 最简单，CSS 和 UQ 更稳健。</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <RadioGroup
            value={scaling}
            onValueChange={(v) => setScaling(v as typeof scaling)}
            className="space-y-3"
          >
            <div className="flex items-center gap-2">
              <RadioGroupItem value="none" id="scaling-none" />
              <Label htmlFor="scaling-none" className="cursor-pointer text-sm">
                No Scaling
              </Label>
            </div>
            <div className="flex items-center gap-2">
              <RadioGroupItem value="tss" id="scaling-tss" />
              <Label htmlFor="scaling-tss" className="cursor-pointer text-sm">
                Total sum scaling (TSS)
                <span className="ml-2 text-xs text-muted-foreground">— Divide by total sample reads (Recommended)</span>
              </Label>
            </div>
            <div className="flex items-center gap-2">
              <RadioGroupItem value="css" id="scaling-css" />
              <Label htmlFor="scaling-css" className="cursor-pointer text-sm">
                Cumulative sum scaling (CSS)
                <span className="ml-2 text-xs text-muted-foreground">— Median scaling based on quantiles</span>
              </Label>
            </div>
            <div className="flex items-center gap-2">
              <RadioGroupItem value="uq" id="scaling-uq" />
              <Label htmlFor="scaling-uq" className="cursor-pointer text-sm">
                Upper quantile scaling (UQ)
                <span className="ml-2 text-xs text-muted-foreground">— Use upper quartile</span>
              </Label>
            </div>
          </RadioGroup>
        </CardContent>
      </Card>

      {/* Transformation */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Scale className="h-5 w-5 text-accent" />
            Transformation
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <HelpCircle className="h-4 w-4 text-muted-foreground cursor-help" />
                </TooltipTrigger>
                <TooltipContent className="max-w-xs">
                  <p>变换用于使数据分布更接近正态，适合某些统计检验和距离计算。</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {scalingSelected && (
            <div className="mb-3 flex items-center gap-2 rounded-md bg-accent/10 px-3 py-2 text-sm text-accent">
              <AlertTriangle className="h-4 w-4" />
              Scaling selected, Transformation disabled (mutually exclusive)
            </div>
          )}
          <RadioGroup
            value={scalingSelected ? "none" : transformation}
            onValueChange={(v) => !scalingSelected && setTransformation(v as typeof transformation)}
            className="space-y-3"
            disabled={scalingSelected}
          >
            <div className="flex items-center gap-2">
              <RadioGroupItem value="none" id="trans-none" disabled={scalingSelected} />
              <Label htmlFor="trans-none" className={cn("cursor-pointer text-sm", scalingSelected && "text-muted-foreground")}>
                No Transformation
              </Label>
            </div>
            <div className="flex items-center gap-2">
              <RadioGroupItem value="clr" id="trans-clr" disabled={scalingSelected} />
              <Label htmlFor="trans-clr" className={cn("cursor-pointer text-sm", scalingSelected && "text-muted-foreground")}>
                Centered log-ratio (CLR)
                <span className="ml-2 text-xs text-muted-foreground">— Suitable for compositional data</span>
              </Label>
            </div>
            <div className="flex items-center gap-2">
              <RadioGroupItem value="rle" id="trans-rle" disabled={scalingSelected} />
              <Label htmlFor="trans-rle" className={cn("cursor-pointer text-sm", scalingSelected && "text-muted-foreground")}>
                Relative log expression (RLE)
                <span className="ml-2 text-xs text-muted-foreground">— DESeq2 normalization method</span>
              </Label>
            </div>
            <div className="flex items-center gap-2">
              <RadioGroupItem value="tmm" id="trans-tmm" disabled={scalingSelected} />
              <Label htmlFor="trans-tmm" className={cn("cursor-pointer text-sm", scalingSelected && "text-muted-foreground")}>
                TMM
                <span className="ml-2 text-xs text-muted-foreground">— edgeR normalization method</span>
              </Label>
            </div>
          </RadioGroup>
        </CardContent>
      </Card>

      {/* Submit */}
      <div className="flex items-center gap-3">
        <Button onClick={handleSubmit} disabled={isSubmitting}>
          {isSubmitting ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Scale className="mr-2 h-4 w-4" />
          )}
          Apply Normalization
        </Button>
      </div>

      {showResult && (
        <StatusAlert
          status="success"
          title="Normalization Complete"
          description={`Configuration saved: ${rarefaction !== "none" ? "稀疏化" : "无稀疏化"} → ${scaling !== "none" ? scaling.toUpperCase() : "无缩放"} → ${!scalingSelected && transformation !== "none" ? transformation.toUpperCase() : "无变换"}`}
        />
      )}

      {/* Bottom Navigation */}
      <div className="flex items-center justify-between pt-4">
        <Button variant="outline" onClick={() => navigate("/filter")}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Previous: Filter
        </Button>
        <Button onClick={() => navigate("/analysis-species")}>
          Proceed to Analysis
          <ArrowRight className="ml-2 h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
