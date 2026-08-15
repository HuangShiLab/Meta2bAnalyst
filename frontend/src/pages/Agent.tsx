import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Switch } from "@/components/ui/switch";
import { useSessionStore } from "@/stores/sessionStore";
import { PlotlyChart } from "@/components/shared/PlotlyChart";
import { AgentChat } from "@/components/shared/AgentChat";
import {
  Bot,
  User,
  Send,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Sparkles,
  Dna,
  MessageSquare,
  Zap,
  ChevronRight,
  Upload,
  FileText,
  BarChart3,
  Download,
  Table,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { PlotlyFigure } from "@/types";

// ───────────────────────────────────────────────────────────────
// TYPES
// ───────────────────────────────────────────────────────────────

interface ChatMessage {
  id: string;
  role: "user" | "agent" | "system";
  content: string;
  timestamp: Date;
  plan?: ExecutionPlan;
  events?: ExecutionEvent[];
  plotData?: PlotlyFigure;
  stats?: Record<string, unknown>;
  /** Plan is shown but not executed until the user confirms. */
  pendingConfirmation?: boolean;
  /** Analyses found in an uploaded paper that have no platform module. */
  unmatchedAnalyses?: string[];
}

interface PlanExplanationStep {
  order: number;
  id: string;
  module: string;
  what: string;
  parameters: string;
  inputs: string;
}

interface PlanExplanation {
  overview: string;
  n_steps: number;
  clarification_needed: boolean;
  steps: PlanExplanationStep[];
}

interface ExecutionPlan {
  n_steps: number;
  steps: { id: string; module: string; description: string; params?: Record<string, any> }[];
  estimated_time: string;
  notes: string[];
  clarification_needed?: boolean;
  explanation?: PlanExplanation | null;
}

interface ExecutionEvent {
  event_type: string;
  step_id?: string;
  timestamp: number;
  payload: Record<string, any>;
}

// ───────────────────────────────────────────────────────────────
// TEMPLATES
// ───────────────────────────────────────────────────────────────

const QUICK_TEMPLATES = [
  {
    id: "auto_analyze",
    label: "Analyze My Data",
    icon: <BarChart3 className="h-4 w-4" />,
    query: "Please analyze my uploaded data. Detect the data format and recommend the most appropriate analysis pipeline. Start with data validation, then run profiling, differential analysis, and network analysis as appropriate for this data type.",
    highlight: true,
  },
  {
    id: "full_pipeline",
    label: "Full Multi-omics Pipeline",
    icon: <Sparkles className="h-4 w-4" />,
    query: "Run the complete multi-omics pipeline: individual profiling, PERMANOVA, marker discovery for both microbiome and metabolome, Procrustes alignment, Mantel test, and generate a report.",
  },
  {
    id: "markers_only",
    label: "Marker Discovery",
    icon: <Zap className="h-4 w-4" />,
    query: "Find differential markers for both microbiome (CLR+Wilcoxon) and metabolome (log1p+Welch) comparing each visit to Day 0 (T4).",
  },
  {
    id: "integration",
    label: "Integration Analysis",
    icon: <Dna className="h-4 w-4" />,
    query: "Run Procrustes alignment and Mantel test to integrate microbiome and metabolome data.",
  },
  {
    id: "profiling",
    label: "Individual Omics Profiling",
    icon: <FileText className="h-4 w-4" />,
    query: "Profile microbiome with PCoA and metabolome with PCA, then run PERMANOVA for metadata effects.",
  },
];

// ───────────────────────────────────────────────────────────────
// MODULE BADGE COLORS
// ───────────────────────────────────────────────────────────────

const MODULE_COLORS: Record<string, string> = {
  data_validator: "bg-gray-500",
  microbiome_pcoa: "bg-blue-500",
  metabolome_pca: "bg-emerald-500",
  permanova: "bg-purple-500",
  microbiome_marker: "bg-amber-500",
  metabolome_marker: "bg-orange-500",
  procrustes: "bg-rose-500",
  mantel_test: "bg-pink-500",
  sparse_cca: "bg-indigo-500",
  rda: "bg-cyan-500",
  o2pls: "bg-teal-500",
  cross_correlation: "bg-violet-500",
  network_sparcc: "bg-lime-500",
  report_generator: "bg-slate-500",
};

// ───────────────────────────────────────────────────────────────
// SSE PARSER
// ───────────────────────────────────────────────────────────────

function parseSSE(buffer: string): { events: ExecutionEvent[]; remainder: string } {
  const parts = buffer.split("\n\n");
  const remainder = parts.pop() || "";
  const events: ExecutionEvent[] = [];

  for (const part of parts) {
    const dataMatch = part.match(/^data: (.+)$/m);
    if (dataMatch) {
      try {
        events.push(JSON.parse(dataMatch[1]));
      } catch {
        // ignore parse errors
      }
    }
  }

  return { events, remainder };
}

function extractBestPlot(events: ExecutionEvent[]): PlotlyFigure | undefined {
  for (let i = events.length - 1; i >= 0; i--) {
    const payload = events[i].payload || {};
    if (payload.plot_data) return payload.plot_data as PlotlyFigure;
    if (payload.has_plot && payload.plot_data) return payload.plot_data as PlotlyFigure;
  }
  return undefined;
}

function extractBestStats(events: ExecutionEvent[]): Record<string, unknown> | undefined {
  for (let i = events.length - 1; i >= 0; i--) {
    const payload = events[i].payload || {};
    if (payload.statistics) return payload.statistics as Record<string, unknown>;
    if (payload.result_summary) return payload.result_summary as Record<string, unknown>;
  }
  return undefined;
}

// ───────────────────────────────────────────────────────────────
// COMPONENT
// ───────────────────────────────────────────────────────────────

export function Agent() {
  const navigate = useNavigate();
  const setCurrentStep = useSessionStore((state) => state.setCurrentStep);
  const sessionId = useSessionStore((state) => state.sessionId);

  useEffect(() => {
    setCurrentStep("agent");
  }, [setCurrentStep]);

  const [mode, setMode] = useState<"execute" | "interpret">("execute");

  // Build results dict from analysis history for interpretation
  const analysisHistory = useSessionStore((state) => state.analysisHistory);
  const interpretedResults = useMemo(() => {
    const results: Record<string, { result_data?: Record<string, unknown> }> = {};
    for (const item of analysisHistory) {
      if (item.status === "success" && item.statistics) {
        results[item.type] = { result_data: item.statistics as Record<string, unknown> };
      }
    }
    return results;
  }, [analysisHistory]);

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "agent",
      content:
        "Hello! I'm your Meta2bAnalyst Agent. I can help you run complex multi-omics analyses automatically.\n\n" +
        "Just tell me what you want to analyze — for example:\n" +
        "• \"Run the full multi-omics pipeline\"\n" +
        "• \"Find differential markers between Day 0 and Day 21\"\n" +
        "• \"Compare microbiome and metabolome with Procrustes and Mantel test\"\n\n" +
        "Or select a quick template below to get started.",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [useLlm, setUseLlm] = useState(true);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const paperInputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Cleanup SSE on unmount
  useEffect(() => {
    return () => {
      if (abortRef.current) {
        abortRef.current.abort();
      }
    };
  }, []);

  const executePlan = useCallback(
    async (planData: ExecutionPlan, agentMsgId: string) => {
      abortRef.current = new AbortController();
      try {
        // Execute with POST-based SSE
        const execRes = await fetch("/api/v1/agent/execute", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, plan: planData }),
          signal: abortRef.current.signal,
        });

        if (!execRes.ok) {
          const err = await execRes.json();
          throw new Error(err.detail || "Execution failed");
        }

        if (!execRes.body) {
          throw new Error("No response stream available");
        }

        const reader = execRes.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        const allEvents: ExecutionEvent[] = [];

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const { events, remainder } = parseSSE(buffer);
          buffer = remainder;

          if (events.length > 0) {
            allEvents.push(...events);
            setMessages((prev) =>
              prev.map((m) =>
                m.id === agentMsgId ? { ...m, events: [...(m.events || []), ...events] } : m
              )
            );
          }
        }

        // Finalize message
        const completed = allEvents.filter((e) => e.event_type === "step_complete").length;
        const failed = allEvents.filter((e) => e.event_type === "step_error").length;
        const plotData = extractBestPlot(allEvents);
        const stats = extractBestStats(allEvents);

        setMessages((prev) =>
          prev.map((m) =>
            m.id === agentMsgId
              ? {
                  ...m,
                  content:
                    m.content +
                    `\n\n---\n✅ **Completed**: ${completed} steps | ❌ **Failed**: ${failed} steps`,
                  plotData,
                  stats,
                }
              : m
          )
        );
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") return;
        const errorMsg = err instanceof Error ? err.message : "Analysis failed";
        setMessages((prev) => [
          ...prev,
          {
            id: `error-${Date.now()}`,
            role: "system",
            content: `❌ Error: ${errorMsg}`,
            timestamp: new Date(),
          },
        ]);
      } finally {
        setIsRunning(false);
        abortRef.current = null;
      }
    },
    [sessionId]
  );

  /** Attach a proposed plan to the chat and wait for explicit confirmation. */
  const proposePlan = useCallback((planData: ExecutionPlan, extra?: Partial<ChatMessage>) => {
    const agentMsg: ChatMessage = {
      id: `agent-${Date.now()}`,
      role: "agent",
      content:
        planData.clarification_needed
          ? `⚠️ ${planData.notes[0] || "I could not determine which analysis you want."}\n\n` +
            (planData.notes[1] || "Please rephrase with a specific goal.")
          : `Proposed plan: **${planData.n_steps} steps** (${planData.estimated_time}). ` +
            `Review the steps below, then confirm to run:`,
      timestamp: new Date(),
      plan: planData.clarification_needed ? undefined : planData,
      pendingConfirmation: !planData.clarification_needed,
      events: [],
      ...extra,
    };
    setMessages((prev) => [...prev, agentMsg]);
    setIsRunning(false);
  }, []);

  const confirmPlan = useCallback(
    (msgId: string) => {
      const msg = messages.find((m) => m.id === msgId);
      if (!msg?.plan || isRunning) return;
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId
            ? { ...m, pendingConfirmation: false, content: m.content.replace("Review the steps below, then confirm to run:", "Executing:") }
            : m
        )
      );
      setIsRunning(true);
      executePlan(msg.plan, msgId);
    },
    [messages, isRunning, executePlan]
  );

  const cancelPlan = useCallback((msgId: string) => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === msgId
          ? { ...m, pendingConfirmation: false, plan: undefined, content: m.content + "\n\n🚫 Cancelled — plan was not executed." }
          : m
      )
    );
  }, []);

  const sendMessage = useCallback(
    async (query: string) => {
      if (!query.trim() || isRunning || !sessionId) return;

      const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        content: query,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setInput("");
      setIsRunning(true);

      abortRef.current = new AbortController();

      try {
        // Step 1: Get plan (with explanation so the user can review it)
        const planRes = await fetch("/api/v1/agent/plan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query, session_id: sessionId, use_llm: useLlm, explain: true }),
          signal: abortRef.current.signal,
        });

        if (!planRes.ok) {
          const err = await planRes.json();
          throw new Error(err.detail || "Planning failed");
        }

        const planData: ExecutionPlan = await planRes.json();

        // Step 2: propose and wait for the user to confirm before executing
        proposePlan(planData);
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") return;
        const errorMsg = err instanceof Error ? err.message : "Planning failed";
        setMessages((prev) => [
          ...prev,
          {
            id: `error-${Date.now()}`,
            role: "system",
            content: `❌ Error: ${errorMsg}`,
            timestamp: new Date(),
          },
        ]);
        setIsRunning(false);
      }
    },
    [isRunning, sessionId, useLlm, proposePlan]
  );

  /** Upload a paper PDF; the backend reconstructs its analysis workflow as a
   *  proposed plan the user can confirm. */
  const handlePaperUpload = useCallback(
    async (file: File) => {
      if (isRunning || !sessionId) return;
      setMessages((prev) => [
        ...prev,
        { id: `user-${Date.now()}`, role: "user", content: `📄 Reproduce analysis from paper: ${file.name}`, timestamp: new Date() },
      ]);
      setIsRunning(true);
      try {
        const form = new FormData();
        form.append("file", file);
        const res = await fetch("/api/v1/agent/plan-from-paper", { method: "POST", body: form });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "Paper analysis failed");
        }
        const data = await res.json();
        const planData: ExecutionPlan = {
          ...data.plan,
          explanation: data.explanation,
        };
        proposePlan(planData, { unmatchedAnalyses: data.unmatched_analyses || [] });
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : "Paper analysis failed";
        setMessages((prev) => [
          ...prev,
          { id: `error-${Date.now()}`, role: "system", content: `❌ Error: ${errorMsg}`, timestamp: new Date() },
        ]);
        setIsRunning(false);
      }
    },
    [isRunning, sessionId, proposePlan]
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  const handleTemplateClick = (query: string) => {
    sendMessage(query);
  };

  // Progress calculation
  const getProgress = (msg: ChatMessage) => {
    if (!msg.plan || !msg.events) return 0;
    const completed = msg.events.filter((e) => e.event_type === "step_complete").length;
    const failed = msg.events.filter((e) => e.event_type === "step_error").length;
    const total = msg.plan.n_steps;
    return total > 0 ? Math.round(((completed + failed) / total) * 100) : 0;
  };

  const isNoSession = !sessionId;

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      {/* Header */}
      <div className="border-b bg-card px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Bot className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-lg font-semibold">Meta2bAnalyst Agent</h1>
            <p className="text-xs text-muted-foreground">
              Intelligent multi-omics analysis orchestration
            </p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
              <Switch checked={useLlm} onCheckedChange={setUseLlm} />
              LLM assist
            </label>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              disabled={isNoSession || isRunning}
              onClick={() => paperInputRef.current?.click()}
              title="Upload a paper PDF; its analysis workflow is reconstructed as a plan you can confirm"
            >
              <Upload className="h-3.5 w-3.5" />
              Plan from paper
            </Button>
            <input
              ref={paperInputRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handlePaperUpload(f);
                e.target.value = "";
              }}
            />
            <Button
              variant={mode === "execute" ? "default" : "outline"}
              size="sm"
              onClick={() => setMode("execute")}
              className="gap-1.5"
            >
              <Sparkles className="h-3.5 w-3.5" />
              Execute
            </Button>
            <Button
              variant={mode === "interpret" ? "default" : "outline"}
              size="sm"
              onClick={() => setMode("interpret")}
              className="gap-1.5"
            >
              <MessageSquare className="h-3.5 w-3.5" />
              Interpret
            </Button>
          </div>
        </div>
      </div>

      {mode === "interpret" ? (
        <AgentChat results={interpretedResults} sessionId={sessionId} />
      ) : (
      <>

      {/* Chat Area */}
      <ScrollArea className="flex-1 px-6 py-4" ref={scrollRef}>
        <div className="mx-auto max-w-4xl space-y-6">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={cn("flex gap-3", msg.role === "user" ? "justify-end" : "justify-start")}
            >
              {/* Avatar */}
              {msg.role !== "user" && (
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10">
                  {msg.role === "agent" ? (
                    <Bot className="h-4 w-4 text-primary" />
                  ) : (
                    <AlertCircle className="h-4 w-4 text-destructive" />
                  )}
                </div>
              )}

              {/* Message Bubble */}
              <div
                className={cn(
                  "max-w-[80%] rounded-2xl px-4 py-3",
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : msg.role === "system"
                    ? "bg-destructive/10 text-destructive"
                    : "bg-muted"
                )}
              >
                <div className="whitespace-pre-wrap text-sm leading-relaxed">{msg.content}</div>

                {/* Execution Progress */}
                {msg.plan && (
                  <div className="mt-3 space-y-2">
                    {msg.pendingConfirmation ? (
                      <div className="space-y-2">
                        {msg.plan.explanation && (
                          <p className="text-xs text-muted-foreground italic">
                            {msg.plan.explanation.overview}
                          </p>
                        )}
                        <div className="space-y-1.5">
                          {(msg.plan.explanation?.steps ||
                            msg.plan.steps.map((s, i) => ({
                              order: i + 1,
                              id: s.id,
                              module: s.module,
                              what: s.description || "",
                              parameters: s.params ? JSON.stringify(s.params) : "default parameters",
                              inputs: "",
                            } as PlanExplanationStep))
                          ).map((step) => (
                            <div key={step.id} className="rounded-md border border-border bg-white/60 px-2.5 py-1.5">
                              <div className="flex items-center gap-2">
                                <Badge variant="outline" className="text-[10px] shrink-0">
                                  {step.order}
                                </Badge>
                                <span className="text-xs font-semibold">{step.module}</span>
                                <Badge variant="secondary" className="text-[10px] ml-auto">
                                  {step.parameters}
                                </Badge>
                              </div>
                              {step.what && (
                                <p className="mt-1 text-[11px] text-slate-600 leading-snug">{step.what}</p>
                              )}
                            </div>
                          ))}
                        </div>
                        {msg.unmatchedAnalyses && msg.unmatchedAnalyses.length > 0 && (
                          <div className="rounded-md border border-amber-200 bg-amber-50 p-2">
                            <p className="text-[11px] font-semibold text-amber-800">
                              In the paper but not available on this platform:
                            </p>
                            <ul className="mt-0.5 list-disc pl-4 text-[11px] text-amber-700">
                              {msg.unmatchedAnalyses.map((a, i) => <li key={i}>{a}</li>)}
                            </ul>
                          </div>
                        )}
                        <div className="flex gap-2 pt-1">
                          <Button size="sm" className="gap-1.5" onClick={() => confirmPlan(msg.id)}>
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            Confirm & Run
                          </Button>
                          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => cancelPlan(msg.id)}>
                            <XCircle className="h-3.5 w-3.5" />
                            Cancel
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <Progress value={getProgress(msg)} className="h-2" />
                        <div className="flex flex-wrap gap-1.5">
                          {msg.plan.steps.map((step) => {
                            const event = msg.events?.find((e) => e.step_id === step.id);
                            const isComplete = event?.event_type === "step_complete";
                            const isError = event?.event_type === "step_error";
                            return (
                              <Badge
                                key={step.id}
                                variant={isComplete ? "default" : isError ? "destructive" : "outline"}
                                className={cn(
                                  "text-xs",
                                  isComplete && MODULE_COLORS[step.module]
                                    ? `${MODULE_COLORS[step.module]} text-white border-0`
                                    : ""
                                )}
                              >
                                {isComplete && <CheckCircle2 className="mr-1 h-3 w-3" />}
                                {isError && <XCircle className="mr-1 h-3 w-3" />}
                                {step.module}
                              </Badge>
                            );
                          })}
                        </div>
                      </>
                    )}
                  </div>
                )}

                {/* Results */}
                {msg.plotData && (
                  <div className="mt-4 space-y-3">
                    {/* Plot Card */}
                    <div className="rounded-lg border border-border bg-white shadow-sm">
                      <div className="flex items-center justify-between border-b border-border px-3 py-2">
                        <div className="flex items-center gap-2">
                          <BarChart3 className="h-4 w-4 text-primary" />
                          <span className="text-xs font-medium">Analysis Result</span>
                        </div>
                        <div className="flex gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0"
                            onClick={() => {
                              if (msg.plotData) {
                                const dataStr = JSON.stringify(msg.plotData, null, 2);
                                const blob = new Blob([dataStr], { type: "application/json" });
                                const url = URL.createObjectURL(blob);
                                const a = document.createElement("a");
                                a.href = url;
                                a.download = `plot-${msg.id}.json`;
                                a.click();
                              }
                            }}
                          >
                            <Download className="h-3 w-3" />
                          </Button>
                        </div>
                      </div>
                      <div className="h-80 p-2">
                        <PlotlyChart figure={msg.plotData} className="h-full" />
                      </div>
                    </div>
                  </div>
                )}

                {/* Statistics Summary */}
                {msg.stats && (
                  <div className="mt-3 rounded-lg border border-border bg-white shadow-sm">
                    <div className="flex items-center gap-2 border-b border-border px-3 py-2">
                      <Table className="h-4 w-4 text-primary" />
                      <span className="text-xs font-medium">Statistics Summary</span>
                    </div>
                    <div className="p-3">
                      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                        {Object.entries(msg.stats).map(([key, value]) => {
                          // Format the display value
                          let displayValue: string;
                          if (typeof value === "number") {
                            displayValue = Math.abs(value) < 0.001 ? value.toExponential(2) : value.toFixed(4);
                          } else if (typeof value === "object" && value !== null) {
                            displayValue = JSON.stringify(value).slice(0, 30) + "...";
                          } else {
                            displayValue = String(value);
                          }
                          
                          // Highlight significant p-values
                          const isSignificant = key.toLowerCase().includes("p") && typeof value === "number" && value < 0.05;
                          
                          return (
                            <div
                              key={key}
                              className={cn(
                                "rounded-lg p-2",
                                isSignificant ? "bg-green-50 border border-green-200" : "bg-background/50"
                              )}
                            >
                              <p className="text-[10px] uppercase text-muted-foreground truncate">
                                {key.replace(/_/g, " ")}
                              </p>
                              <p className={cn(
                                "text-sm font-semibold",
                                isSignificant && "text-green-700"
                              )}>
                                {displayValue}
                                {isSignificant && " ✓"}
                              </p>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                )}

                {/* Timestamp */}
                <div className="mt-1 text-right">
                  <span className="text-[10px] opacity-50">
                    {msg.timestamp.toLocaleTimeString()}
                  </span>
                </div>
              </div>

              {/* User Avatar */}
              {msg.role === "user" && (
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary">
                  <User className="h-4 w-4 text-primary-foreground" />
                </div>
              )}
            </div>
          ))}

          {isRunning && (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="text-sm">Executing analysis workflow...</span>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Input Area */}
      <div className="border-t bg-card px-6 py-4">
        <div className="mx-auto max-w-4xl space-y-4">
          {/* No session warning */}
          {isNoSession && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm text-amber-800">
                  <AlertCircle className="h-4 w-4" />
                  <span>No analysis session found. Upload data first to enable the Agent.</span>
                </div>
                <Button size="sm" onClick={() => navigate("/upload")} className="gap-1">
                  <Upload className="h-3 w-3" />
                  Upload Data
                </Button>
              </div>
            </div>
          )}

          {/* Quick Templates */}
          {messages.length <= 1 && !isNoSession && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {QUICK_TEMPLATES.map((t) => (
                <Button
                  key={t.id}
                  variant="outline"
                  size="sm"
                  className="h-auto justify-start gap-2 py-2 text-xs"
                  onClick={() => handleTemplateClick(t.query)}
                  disabled={isRunning}
                >
                  {t.icon}
                  <span className="truncate">{t.label}</span>
                  <ChevronRight className="ml-auto h-3 w-3 opacity-50" />
                </Button>
              ))}
            </div>
          )}

          {/* Input Form */}
          <form onSubmit={handleSubmit} className="flex gap-2">
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Describe your analysis goal... (e.g., 'Find differential markers between Day 0 and Day 21')"
              className="flex-1"
              disabled={isRunning || isNoSession}
            />
            <Button type="submit" disabled={isRunning || !input.trim() || isNoSession} className="gap-2">
              {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              {isRunning ? "Running..." : "Send"}
            </Button>
          </form>

          <p className="text-center text-[10px] text-muted-foreground">
            Agent uses rule-based planning (no API key required). Supports 20+ analysis modules with
            automatic parameter injection.
          </p>
        </div>
      </div>
      </>
      )}
    </div>
  );
}
