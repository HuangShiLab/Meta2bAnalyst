import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Download, FileSpreadsheet, Image } from "lucide-react";
import { cn } from "@/lib/utils";

interface ResultPanelProps {
  className?: string;
}

export function ResultPanel({ className }: ResultPanelProps) {
  return (
    <Card className={cn("", className)}>
      <CardHeader>
        <CardTitle>Analysis Results</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" className="gap-2">
            <FileSpreadsheet className="h-4 w-4" />
            Download CSV
          </Button>
          <Button variant="outline" size="sm" className="gap-2">
            <Image className="h-4 w-4" />
            Download Figures
          </Button>
          <Button variant="outline" size="sm" className="gap-2">
            <Download className="h-4 w-4" />
            Download Report
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
