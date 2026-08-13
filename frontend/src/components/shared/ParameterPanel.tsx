import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { cn } from "@/lib/utils";

interface ParameterPanelProps {
  className?: string;
}

export function ParameterPanel({ className }: ParameterPanelProps) {
  return (
    <Card className={cn("", className)}>
      <CardHeader>
        <CardTitle>Analysis Parameters</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="pvalue">P-value Threshold</Label>
          <div className="flex items-center gap-4">
            <Slider defaultValue={[0.05]} max={0.1} step={0.001} className="flex-1" />
            <span className="w-16 text-sm">0.05</span>
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor="logfc">Log Fold Change</Label>
          <Input id="logfc" type="number" defaultValue={1} step={0.1} />
        </div>
      </CardContent>
    </Card>
  );
}
