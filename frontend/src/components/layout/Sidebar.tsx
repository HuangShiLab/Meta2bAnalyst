import { Link, useLocation } from "react-router-dom";
import {
  Upload,
  CheckCircle,
  Home,
  Layers,
  Bot,
  Dna,
  Globe, Workflow,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { AnalysisStep } from "@/types";

const steps: { id: AnalysisStep; label: string; icon: React.ReactNode; path: string }[] = [
  { id: "home", label: "Home", icon: <Home className="h-4 w-4" />, path: "/" },
  { id: "upload", label: "Upload", icon: <Upload className="h-4 w-4" />, path: "/upload" },
  { id: "microbiome", label: "Microbiome", icon: <Dna className="h-4 w-4" />, path: "/microbiome" },
  { id: "multi-omics", label: "Multi-omics", icon: <Layers className="h-4 w-4" />, path: "/multi-omics" },
  { id: "multi-site", label: "Multi-site", icon: <Globe className="h-4 w-4" />, path: "/multi-site" },
  { id: "agent", label: "Agent", icon: <Bot className="h-4 w-4" />, path: "/agent" },
  { id: "workflow-builder", label: "Workflow Builder", icon: <Workflow className="h-4 w-4" />, path: "/workflow-builder" },
  { id: "results", label: "Results", icon: <CheckCircle className="h-4 w-4" />, path: "/results" },
];

interface SidebarProps {
  className?: string;
}

export function Sidebar({ className }: SidebarProps) {
  const location = useLocation();
  const currentPath = location.pathname;

  return (
    <aside
      className={cn(
        "fixed left-0 top-16 z-40 h-[calc(100vh-4rem)] w-64 border-r border-border bg-sidebar text-sidebar-foreground",
        className
      )}
    >
      <div className="flex h-full flex-col">
        <div className="flex-1 overflow-auto py-4">
          <nav className="space-y-1 px-3">
            {steps.map((step) => {
              const isActive = currentPath === step.path;
              return (
                <Link
                  key={step.id}
                  to={step.path}
                  className={cn(
                    "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-white/10 text-white"
                      : "text-slate-300 hover:bg-white/5 hover:text-white"
                  )}
                >
                  {step.icon}
                  {step.label}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="border-t border-white/10 p-4">
          <div className="rounded-md bg-white/5 px-3 py-2">
            <p className="text-xs font-medium text-slate-300">Analysis Pipeline</p>
            <p className="mt-1 text-xs text-slate-400">
              {steps.find((s) => s.path === currentPath)?.label || "Select a step"}
            </p>
          </div>
        </div>
      </div>
    </aside>
  );
}
