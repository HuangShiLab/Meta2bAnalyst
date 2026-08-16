import { useState, useRef, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  User,
  Send,
  Loader2,
  BookOpen,
  AlertTriangle,
  Lightbulb,
  Stethoscope,
  ChevronDown,
  ChevronUp,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAgentInterpretation, type InterpretFullResponse } from "@/hooks/useAgentInterpretation";

// ───────────────────────────────────────────────────────────────
// TYPES
// ───────────────────────────────────────────────────────────────

interface ChatMessage {
  id: string;
  role: "user" | "agent";
  content: string;
  timestamp: Date;
  type?: "text" | "bio_context" | "disease" | "caveat" | "suggestion" | "contradiction";
  payload?: unknown;
}

// ───────────────────────────────────────────────────────────────
// QUESTION CLASSIFIER (client-side, rule-based)
// ───────────────────────────────────────────────────────────────

function classifyQuestion(text: string): "full_interpretation" | "specific_contradiction" | "taxon_query" | "disease_query" | "method_query" | "general" {
  const lower = text.toLowerCase();
  if (lower.includes("why") || lower.includes("what happened") || lower.includes("explain") || lower.includes("contradiction") || lower.includes("contradict")) {
    return "specific_contradiction";
  }
  if (lower.includes("species") || lower.includes("taxon") || lower.includes("bacteria") || lower.includes("genus")) {
    return "taxon_query";
  }
  if (lower.includes("disease") || lower.includes("disorder") || lower.includes("syndrome") || lower.includes("related")) {
    return "disease_query";
  }
  if (lower.includes("method") || lower.includes("parameter") || lower.includes("why use") || lower.includes("assumption")) {
    return "method_query";
  }
  if (lower.includes("comprehensive analysis") || lower.includes("overview") || lower.includes("summary") || lower.includes("interpret")) {
    return "full_interpretation";
  }
  return "general";
}

// ───────────────────────────────────────────────────────────────
// ANSWER GENERATOR
// ───────────────────────────────────────────────────────────────

function generateAnswer(
  question: string,
  interp: InterpretFullResponse | null,
  hasBeenInterpreted: boolean
): { messages: Omit<ChatMessage, "id" | "timestamp">[]; needsInterpretation: boolean } {
  const category = classifyQuestion(question);
  const messages: Omit<ChatMessage, "id" | "timestamp">[] = [];

  if (!hasBeenInterpreted && !interp) {
    messages.push({
      role: "agent",
      content: "Let me analyze all your results first to give you an informed answer...",
      type: "text",
    });
    return { messages, needsInterpretation: true };
  }

  if (!interp) {
    messages.push({
      role: "agent",
      content: "I need to run the integrated interpretation first. Please wait a moment while I analyze all results...",
      type: "text",
    });
    return { messages, needsInterpretation: true };
  }

  switch (category) {
    case "full_interpretation":
      messages.push({
        role: "agent",
        content: interp.integrated_narrative || "No integrated narrative available.",
        type: "text",
      });
      if (interp.biological_context.length > 0) {
        messages.push({
          role: "agent",
          content: "Here is the biological context for key taxa in your data:",
          type: "bio_context",
          payload: interp.biological_context,
        });
      }
      break;

    case "specific_contradiction":
      if (interp.contradictions.length > 0) {
        messages.push({
          role: "agent",
          content: "I detected the following cross-analysis patterns that may seem contradictory:",
          type: "contradiction",
          payload: interp.contradictions,
        });
        messages.push({
          role: "agent",
          content:
            "**Why this happens**: Alpha diversity measures 'how many species and how evenly' within each sample. " +
            "LEfSe detects specific species that changed in abundance. It's entirely possible for the *overall* diversity " +
            "to stay stable while *individual* species shift — this is called **taxonomic substitution with functional redundancy**. " +
            "The ecosystem maintains its complexity (alpha stable) and structure (beta stable) while swapping out specific players.",
          type: "text",
        });
      } else {
        messages.push({
          role: "agent",
          content:
            "I didn't detect any obvious contradictions across your analyses. " +
            "The results appear consistent: " + interp.integrated_narrative.slice(0, 200) + "...",
          type: "text",
        });
      }
      break;

    case "taxon_query": {
      const matches = interp.biological_context.filter((ctx) =>
        question.split(/\s+/).some((word) => word.length > 2 && ctx.toLowerCase().includes(word.toLowerCase()))
      );
      if (matches.length > 0) {
        messages.push({
          role: "agent",
          content: `I found biological information related to your query:`,
          type: "bio_context",
          payload: matches,
        });
      } else {
        messages.push({
          role: "agent",
          content:
            "Based on your data, here are the key taxa with biological annotations:\n\n" +
            interp.biological_context.slice(0, 3).join("\n\n"),
          type: "text",
        });
      }
      break;
    }

    case "disease_query":
      if (interp.disease_relevance.length > 0) {
        messages.push({
          role: "agent",
          content: "Your data shows potential relevance to the following disease signatures:",
          type: "disease",
          payload: interp.disease_relevance,
        });
      } else {
        messages.push({
          role: "agent",
          content: "No strong disease associations were detected from the significant taxa in your data.",
          type: "text",
        });
      }
      break;

    case "method_query":
      messages.push({
        role: "agent",
        content:
          "**Method considerations for your analysis:**\n\n" +
          interp.caveats.map((c) => `• ${c}`).join("\n") +
          "\n\n**Recommended follow-up:**\n\n" +
          interp.follow_up_suggestions.map((s) => `• ${s}`).join("\n"),
        type: "text",
      });
      break;

    case "general":
    default:
      messages.push({
        role: "agent",
        content: interp.integrated_narrative || "Here is my analysis of your data.",
        type: "text",
      });
      if (interp.follow_up_suggestions.length > 0) {
        messages.push({
          role: "agent",
          content: "Suggestions for next steps:",
          type: "suggestion",
          payload: interp.follow_up_suggestions,
        });
      }
      break;
  }

  return { messages, needsInterpretation: false };
}

// ───────────────────────────────────────────────────────────────
// COLLAPSIBLE CARD
// ───────────────────────────────────────────────────────────────

function CollapsibleCard({
  title,
  icon,
  children,
  defaultOpen = false,
  variant = "default",
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
  variant?: "default" | "warning" | "info";
}) {
  const [open, setOpen] = useState(defaultOpen);
  const variantStyles = {
    default: "border-border",
    warning: "border-amber-200 bg-amber-50/50",
    info: "border-blue-200 bg-blue-50/50",
  };
  return (
    <Card className={cn("mb-2", variantStyles[variant])}>
      <CardHeader className="py-2 px-3 cursor-pointer" onClick={() => setOpen(!open)}>
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-semibold flex items-center gap-2">
            {icon}
            {title}
          </CardTitle>
          {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        </div>
      </CardHeader>
      {open && <CardContent className="pt-0 pb-3 px-3">{children}</CardContent>}
    </Card>
  );
}

// ───────────────────────────────────────────────────────────────
// MESSAGE RENDERER
// ───────────────────────────────────────────────────────────────

function AgentMessageContent({ msg }: { msg: ChatMessage }) {
  if (msg.type === "bio_context" && Array.isArray(msg.payload)) {
    return (
      <div className="space-y-2">
        <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
        {msg.payload.map((ctx: string, i: number) => (
          <CollapsibleCard
            key={i}
            title={ctx.split("**")[1] || `Taxon ${i + 1}`}
            icon={<BookOpen className="h-3 w-3 text-emerald-600" />}
            defaultOpen={i === 0}
            variant="info"
          >
            <p className="text-xs text-slate-700 whitespace-pre-wrap leading-relaxed">{ctx}</p>
          </CollapsibleCard>
        ))}
      </div>
    );
  }

  if (msg.type === "disease" && Array.isArray(msg.payload)) {
    return (
      <div className="space-y-2">
        <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
        {msg.payload.map((d: InterpretFullResponse["disease_relevance"][0], i: number) => (
          <CollapsibleCard
            key={i}
            title={d.disease.replace(/_/g, " ").toUpperCase()}
            icon={<Stethoscope className="h-3 w-3 text-rose-600" />}
            variant="warning"
          >
            <div className="space-y-2">
              <p className="text-xs text-slate-600">{d.description}</p>
              <div>
                <p className="text-[10px] font-semibold text-slate-500 uppercase">Matched Taxa</p>
                <div className="flex flex-wrap gap-1 mt-1">
                  {d.matched_taxa.map((t) => (
                    <Badge key={t} variant="outline" className="text-[10px]">
                      {t}
                    </Badge>
                  ))}
                </div>
              </div>
              <div>
                <p className="text-[10px] font-semibold text-slate-500 uppercase">Key Indicators</p>
                <div className="flex flex-wrap gap-1 mt-1">
                  {d.indicators.slice(0, 5).map((ind) => (
                    <Badge key={ind} variant="secondary" className="text-[10px]">
                      {ind.replace(/_/g, " ")}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>
          </CollapsibleCard>
        ))}
      </div>
    );
  }

  if (msg.type === "contradiction" && Array.isArray(msg.payload)) {
    return (
      <div className="space-y-2">
        <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
        {msg.payload.map((c: string, i: number) => (
          <div key={i} className="rounded-md border border-amber-200 bg-amber-50 p-2">
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
              <p className="text-xs text-amber-800 whitespace-pre-wrap">{c}</p>
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (msg.type === "suggestion" && Array.isArray(msg.payload)) {
    return (
      <div className="space-y-2">
        <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
        <div className="space-y-1">
          {msg.payload.map((s: string, i: number) => (
            <div key={i} className="flex items-start gap-2 rounded-md bg-slate-50 p-2">
              <Lightbulb className="h-3 w-3 text-indigo-500 shrink-0 mt-0.5" />
              <p className="text-xs text-slate-700">{s}</p>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return <div className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</div>;
}

// ───────────────────────────────────────────────────────────────
// MAIN COMPONENT
// ───────────────────────────────────────────────────────────────

interface AgentChatProps {
  results?: Record<string, { result_data?: Record<string, unknown> }>;
  sessionId: string | null;
}

export function AgentChat({ results: externalResults, sessionId }: AgentChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "agent",
      content:
        "👋 I'm your **Knowledge-Augmented Analyst**.\n\n" +
        "Ask me anything about your microbiome data — for example:\n" +
        "• \"Comprehensive analysis of my data\"\n" +
        "• \"why is Alpha diversity not significant but LEfSe found differential species?\"\n" +
        "• \"What diseases are these species related to?\"\n" +
        "• \"What analysis should I do next?\"\n\n" +
        "I'll use the structured knowledge base to give you evidence-based answers.",
      timestamp: new Date(),
      type: "text",
    },
  ]);
  const [input, setInput] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  const [hasInterpreted, setHasInterpreted] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { result: interpResult, interpretFull } = useAgentInterpretation();

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isThinking]);

  const addMessage = useCallback((msg: Omit<ChatMessage, "id" | "timestamp">) => {
    const fullMsg: ChatMessage = {
      ...msg,
      id: `${msg.role}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, fullMsg]);
    return fullMsg.id;
  }, []);

  const handleSend = useCallback(
    async (text: string) => {
      if (!text.trim() || isThinking) return;

      addMessage({ role: "user", content: text, type: "text" });
      setInput("");
      setIsThinking(true);

      try {
        const availableResults = externalResults;
        if (!availableResults || Object.keys(availableResults).length === 0) {
          addMessage({
            role: "agent",
            content:
              "I don't see any analysis results yet. Please run analyses in the **Microbiome** tab first " +
              "(e.g., Alpha Diversity, Beta Diversity, PERMANOVA), then come back here to ask questions about your data.",
            type: "text",
          });
          setIsThinking(false);
          return;
        }

        const { messages: answerMsgs, needsInterpretation } = generateAnswer(
          text,
          interpResult,
          hasInterpreted
        );

        if (needsInterpretation) {
          addMessage(answerMsgs[0]);

          const fresh = await interpretFull(availableResults as Record<string, unknown>, { n_samples: 20, data_type: "metagenomics" });
          setHasInterpreted(true);

          // Use the freshly returned interpretation - `interpResult` in this
          // closure is still the pre-await value (null on the first question).
          const { messages: finalMsgs } = generateAnswer(text, fresh ?? interpResult, true);
          for (const m of finalMsgs) {
            addMessage(m);
          }
        } else {
          for (const m of answerMsgs) {
            addMessage(m);
          }
        }
      } catch (err) {
        addMessage({
          role: "agent",
          content: `❌ Sorry, I encountered an error: ${err instanceof Error ? err.message : "Unknown error"}`,
          type: "text",
        });
      } finally {
        setIsThinking(false);
      }
    },
    [isThinking, externalResults, interpResult, hasInterpreted, interpretFull, addMessage]
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSend(input);
  };

  const quickQuestions = [
    "Comprehensive analysis of my data",
    "Why is alpha not significant but LEfSe found differences?",
    "What diseases are these species related to?",
    "What should I do next?",
  ];

  const isNoSession = !sessionId;
  const hasNoResults = !externalResults || Object.keys(externalResults).length === 0;

  return (
    <div className="flex h-full flex-col">
      <ScrollArea className="flex-1 px-4 py-3" ref={scrollRef}>
        <div className="mx-auto max-w-3xl space-y-4">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={cn("flex gap-3", msg.role === "user" ? "justify-end" : "justify-start")}
            >
              {msg.role === "agent" && (
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10">
                  <Sparkles className="h-4 w-4 text-primary" />
                </div>
              )}

              <div
                className={cn(
                  "max-w-[85%] rounded-2xl px-4 py-3",
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted border border-border"
                )}
              >
                <AgentMessageContent msg={msg} />
                <div className="mt-1 text-right">
                  <span className="text-[10px] opacity-50">
                    {msg.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>
              </div>

              {msg.role === "user" && (
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary">
                  <User className="h-4 w-4 text-primary-foreground" />
                </div>
              )}
            </div>
          ))}

          {isThinking && (
            <div className="flex items-center gap-2 text-muted-foreground pl-11">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="text-sm">Consulting knowledge base...</span>
            </div>
          )}
        </div>
      </ScrollArea>

      <div className="border-t bg-card px-4 py-3">
        <div className="mx-auto max-w-3xl space-y-3">
          {!isNoSession && hasNoResults && messages.length <= 2 && (
            <div className="flex flex-wrap gap-2">
              {quickQuestions.map((q) => (
                <Button
                  key={q}
                  variant="outline"
                  size="sm"
                  className="h-auto py-1.5 text-xs"
                  onClick={() => handleSend(q)}
                  disabled={isThinking}
                >
                  {q}
                </Button>
              ))}
            </div>
          )}

          {isNoSession && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" />
                <span>No active session. Upload data and run analyses first to enable interpretation.</span>
              </div>
            </div>
          )}
          {!isNoSession && hasNoResults && (
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800">
              <div className="flex items-center gap-2">
                <BookOpen className="h-4 w-4" />
                <span>No analysis results available yet. Run analyses in the Microbiome tab first.</span>
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit} className="flex gap-2">
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about your data... (e.g., 'Why is alpha diversity not significant?')"
              className="flex-1"
              disabled={isThinking || isNoSession || hasNoResults}
            />
            <Button type="submit" disabled={isThinking || !input.trim() || isNoSession || hasNoResults} className="gap-2">
              {isThinking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </form>

          <p className="text-center text-[10px] text-muted-foreground">
            Powered by a structured knowledge base (80 taxa, 17 methods, 25 disease signatures), with optional external LLM enhancement.
          </p>
        </div>
      </div>
    </div>
  );
}
