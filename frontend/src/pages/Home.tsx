import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dna,
  Activity,
  GitBranch,
  Layers,
  ArrowRight,
  BookOpen,
  Globe,
  Zap,
  FileSpreadsheet,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface ModuleCardProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  features: string[];
  color: string;
  hoverBorder: string;
}

function ModuleCard({ icon, title, description, features, color, hoverBorder }: ModuleCardProps) {
  const navigate = useNavigate();
  return (
    <Card
      className={cn(
        "group relative overflow-hidden rounded-xl border-0 bg-white shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-lg cursor-pointer",
        hoverBorder
      )}
      onClick={() => navigate("/upload")}
    >
      <div className={cn("h-1.5 w-full", color)} />
      <CardHeader className="pb-2 pt-5">
        <div className="flex items-center gap-3">
          <div className={cn("flex h-10 w-10 items-center justify-center rounded-lg text-white", color)}>
            {icon}
          </div>
          <div>
            <CardTitle className="text-lg font-semibold">{title}</CardTitle>
            <CardDescription className="text-sm">{description}</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {features.map((feature, index) => (
            <li key={index} className="flex items-center gap-2 text-sm text-muted-foreground">
              <div className={cn("h-1.5 w-1.5 rounded-full", color)} />
              {feature}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export function Home() {
  const navigate = useNavigate();

  return (
    <div className="space-y-10">
      {/* Hero Section */}
      <div className="text-center">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
          <Dna className="h-8 w-8 text-primary" />
        </div>
        <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
          Meta2bAnalyst
        </h1>
        <p className="mx-auto mt-3 max-w-2xl text-lg text-muted-foreground">
          One-stop Statistical Analysis Platform for 2bRAD Toolkit
        </p>
        <p className="mx-auto mt-1 max-w-2xl text-sm text-muted-foreground">
          Compatible with QIIME, Mothur, 2bRAD-M, Strain2bScan data formats
        </p>
      </div>

      {/* Module Cards */}
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <ModuleCard
          icon={<Dna className="h-5 w-5" />}
          title="Species-Level Analysis"
          description="Taxonomic abundance analysis"
          features={["Community Analysis", "Differential Analysis", "Functional Prediction"]}
          color="bg-[#1e40af]"
          hoverBorder="hover:ring-[#1e40af]/20"
        />
        <ModuleCard
          icon={<Activity className="h-5 w-5" />}
          title="Functional Gene Analysis"
          description="Functional gene analysis"
          features={["Pathway Enrichment", "Functional Differential", "Metabolic Network"]}
          color="bg-[#0f766e]"
          hoverBorder="hover:ring-[#0f766e]/20"
        />
        <ModuleCard
          icon={<GitBranch className="h-5 w-5" />}
          title="Strain-Level Analysis"
          description="Strain-level profiling"
          features={["Strain Composition", "Strain Diversity", "Strain Differential"]}
          color="bg-[#d97706]"
          hoverBorder="hover:ring-[#d97706]/20"
        />
        <ModuleCard
          icon={<Layers className="h-5 w-5" />}
          title="Multi-Omics Integration"
          description="Integrative multi-omics"
          features={["Species-Function-Strain Integration", "Cross-Omics Association", "Joint Visualization"]}
          color="bg-[#7c3aed]"
          hoverBorder="hover:ring-[#7c3aed]/20"
        />
      </div>

      {/* Quick Actions */}
      <div data-testid="home-quick-actions" className="flex flex-wrap items-center justify-center gap-4">
        <Button data-testid="btn-quick-start" size="lg" className="gap-2" onClick={() => navigate("/upload")}>
          <Zap className="h-4 w-4" />
          Quick Start
        </Button>
        <Button data-testid="btn-docs" variant="outline" size="lg" className="gap-2" asChild>
          <a href="https://docs.meta2banalyst.com" target="_blank" rel="noreferrer">
            <BookOpen className="h-4 w-4" />
            Documentation
          </a>
        </Button>
        <Button data-testid="btn-github" variant="outline" size="lg" className="gap-2" asChild>
          <a href="https://github.com/meta2banalyst" target="_blank" rel="noreferrer">
            <Globe className="h-4 w-4" />
            GitHub
          </a>
        </Button>
      </div>

      {/* Supported Formats */}
      <div className="text-center">
        <p className="mb-3 text-sm font-medium text-muted-foreground">Supported Data Formats</p>
        <div className="flex flex-wrap items-center justify-center gap-2">
          <Badge variant="secondary" className="px-3 py-1 text-sm">
            <FileSpreadsheet className="mr-1 h-3 w-3" />
            2bRAD-M
          </Badge>
          <Badge variant="secondary" className="px-3 py-1 text-sm">
            <FileSpreadsheet className="mr-1 h-3 w-3" />
            QIIME/BIOM
          </Badge>
          <Badge variant="secondary" className="px-3 py-1 text-sm">
            <FileSpreadsheet className="mr-1 h-3 w-3" />
            Mothur
          </Badge>
          <Badge variant="secondary" className="px-3 py-1 text-sm">
            <FileSpreadsheet className="mr-1 h-3 w-3" />
            TSV/CSV
          </Badge>
        </div>
      </div>

      {/* Pipeline Overview */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Card className="border-0 shadow-sm">
          <CardContent className="flex flex-col items-center p-6 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
              <ArrowRight className="h-5 w-5 text-primary" />
            </div>
            <h3 className="mt-4 font-semibold">1. Upload Data</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              Supports multiple microbiome data formats with automatic validation and parsing
            </p>
          </CardContent>
        </Card>
        <Card className="border-0 shadow-sm">
          <CardContent className="flex flex-col items-center p-6 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-secondary/10">
              <ArrowRight className="h-5 w-5 text-secondary" />
            </div>
            <h3 className="mt-4 font-semibold">2. QC & Filtering</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              Data inspection, low-count feature filtering, normalization
            </p>
          </CardContent>
        </Card>
        <Card className="border-0 shadow-sm">
          <CardContent className="flex flex-col items-center p-6 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent/10">
              <ArrowRight className="h-5 w-5 text-accent" />
            </div>
            <h3 className="mt-4 font-semibold">3. Analysis & Visualization</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              物种/功能/Strain-Level Analysis，出版级图表导出
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
