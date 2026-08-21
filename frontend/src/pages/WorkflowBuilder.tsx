import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useWorkflowStore } from "@/stores/workflowStore";
import { cn } from "@/lib/utils";
import {
  Play,
  Trash2,
  Plus,
  GripVertical,
  ChevronRight,
  ChevronDown,
  Zap,
  LayoutGrid,
  ArrowDown,
  X,
  Loader2,
  Save,
  RotateCcw,
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const CATEGORY_COLORS: Record<string, string> = {
  preprocessing: "bg-amber-100 text-amber-800 border-amber-300",
  individual_omics: "bg-blue-100 text-blue-800 border-blue-300",
  integration: "bg-purple-100 text-purple-800 border-purple-300",
  marker: "bg-rose-100 text-rose-800 border-rose-300",
  visualization: "bg-gray-100 text-gray-800 border-gray-300",
  network: "bg-emerald-100 text-emerald-800 border-emerald-300",
};

// ───────────────────────────────────────────────────────────────
// MODULE PALETTE (left sidebar)
// ───────────────────────────────────────────────────────────────
function ModulePalette() {
  const { moduleRegistry, categories, addNode } = useWorkflowStore();
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const modulesByCategory = categories.map((cat) => ({
    category: cat,
    modules: Object.values(moduleRegistry || {}).filter((m: any) => m.category === cat),
  }));

  const onDragStart = (e: React.DragEvent, module: string, category: string, desc: string) => {
    e.dataTransfer.setData("application/json", JSON.stringify({ module, category, description: desc }));
  };

  return (
    <div className="w-72 border-r bg-muted/30 flex flex-col">
      <div className="p-3 border-b bg-background">
        <h3 className="font-semibold text-sm flex items-center gap-2">
          <LayoutGrid className="w-4 h-4" />
          Analysis Bricks
        </h3>
        <p className="text-xs text-muted-foreground mt-1">Drag modules to canvas</p>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {modulesByCategory.map(({ category, modules }) => (
            <div key={category}>
              <button
                className="w-full flex items-center gap-1 px-2 py-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground hover:bg-accent rounded-sm transition-colors"
                onClick={() => setExpanded((p) => ({ ...p, [category]: !p[category] }))}
              >
                {expanded[category] !== false ? (
                  <ChevronDown className="w-3 h-3" />
                ) : (
                  <ChevronRight className="w-3 h-3" />
                )}
                {category.replace(/_/g, " ")}
                <Badge variant="secondary" className="ml-auto text-[10px]">
                  {modules.length}
                </Badge>
              </button>
              {(expanded[category] !== false) && (
                <div className="ml-2 mt-1 space-y-0.5">
                  {modules.map((m: any) => (
                    <div
                      key={m.name}
                      draggable
                      onDragStart={(e) => onDragStart(e, m.name, m.category, m.description)}
                      className={cn(
                        "px-2 py-1.5 text-xs rounded-md cursor-grab active:cursor-grabbing border transition-all hover:shadow-sm",
                        CATEGORY_COLORS[m.category] || "bg-gray-50 border-gray-200"
                      )}
                      title={m.description}
                    >
                      <div className="font-medium truncate">{m.name}</div>
                      <div className="text-[10px] opacity-70 truncate">{m.description.slice(0, 60)}...</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────
// PARAM PANEL (right sidebar)
// ───────────────────────────────────────────────────────────────
function ParamPanel() {
  const { selectedNodeId, nodes, moduleRegistry, updateNodeParams, removeNode } = useWorkflowStore();
  const node = nodes.find((n) => n.id === selectedNodeId);
  const spec: any = node ? (moduleRegistry || {})[node.module] : null;

  if (!node || !spec) {
    return (
      <div className="w-72 border-l bg-muted/30 flex flex-col">
        <div className="p-4 text-center text-sm text-muted-foreground">
          <Zap className="w-8 h-8 mx-auto mb-2 opacity-40" />
          Select a brick to configure parameters
        </div>
      </div>
    );
  }

  return (
    <div className="w-72 border-l bg-muted/30 flex flex-col">
      <div className="p-3 border-b bg-background flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-sm">{node.module}</h3>
          <Badge variant="outline" className="text-[10px] mt-1">
            {node.category}
          </Badge>
        </div>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => removeNode(node.id)}>
          <Trash2 className="w-3.5 h-3.5 text-destructive" />
        </Button>
      </div>
      <ScrollArea className="flex-1 p-3">
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">{spec.description}</p>

          {spec.constraints?.length > 0 && (
            <div className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-2">
              <strong>Constraints:</strong>
              <ul className="list-disc ml-4 mt-0.5">
                {spec.constraints.map((c: string, i: number) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="space-y-2">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Parameters
            </h4>
            {Object.entries(spec.parameters || {}).map(([key, param]: [string, any]) => (
              <div key={key} className="space-y-1">
                <label className="text-xs font-medium">{key}</label>
                {param.type === "enum" ? (
                  <select
                    className="w-full text-xs border rounded-md px-2 py-1.5 bg-background"
                    value={node.params[key] ?? param.default ?? ""}
                    onChange={(e) => updateNodeParams(node.id, { [key]: e.target.value })}
                  >
                    {(Array.isArray(param.options) ? param.options : []).map((opt: string) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                ) : param.type === "bool" ? (
                  <input
                    type="checkbox"
                    checked={node.params[key] ?? param.default ?? false}
                    onChange={(e) => updateNodeParams(node.id, { [key]: e.target.checked })}
                    className="w-4 h-4"
                  />
                ) : param.type === "float" || param.type === "int" ? (
                  <Input
                    type="number"
                    className="h-8 text-xs"
                    value={node.params[key] ?? param.default ?? ""}
                    onChange={(e) =>
                      updateNodeParams(node.id, {
                        [key]: param.type === "int" ? parseInt(e.target.value) : parseFloat(e.target.value),
                      })
                    }
                  />
                ) : (
                  <Input
                    type="text"
                    className="h-8 text-xs"
                    value={node.params[key] ?? param.default ?? ""}
                    onChange={(e) => updateNodeParams(node.id, { [key]: e.target.value })}
                    placeholder={param.description || ""}
                  />
                )}
                {param.description && (
                  <p className="text-[10px] text-muted-foreground">{param.description}</p>
                )}
              </div>
            ))}
            {Object.keys(spec.parameters || {}).length === 0 && (
              <p className="text-xs text-muted-foreground italic">No configurable parameters</p>
            )}
          </div>

          <div className="space-y-1">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Inputs
            </h4>
            {Object.entries(spec.input_requirements || {}).map(([key, req]: [string, any]) => (
              <Badge key={key} variant={req === "required" ? "default" : "secondary"} className="text-[10px]">
                {key}: {req}
              </Badge>
            ))}
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────
// DAG CANVAS (center)
// ───────────────────────────────────────────────────────────────
function DAGCanvas() {
  const { nodes, edges, selectedNodeId, selectNode, moveNode, autoLayout } = useWorkflowStore();
  const canvasRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState<string | null>(null);
  const dragOffset = useRef({ x: 0, y: 0 });

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const data = e.dataTransfer.getData("application/json");
      if (!data) return;
      const { module, category, description } = JSON.parse(data);
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      useWorkflowStore.getState().addNode(module, category, description, x, y);
    },
    []
  );

  const onMouseDown = (e: React.MouseEvent, nodeId: string) => {
    const node = nodes.find((n) => n.id === nodeId);
    if (!node) return;
    selectNode(nodeId);
    setDragging(nodeId);
    dragOffset.current = { x: e.clientX - node.x, y: e.clientY - node.y };
  };

  const onMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!dragging) return;
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;
      moveNode(dragging, e.clientX - rect.left, e.clientY - rect.top);
    },
    [dragging, moveNode]
  );

  const onMouseUp = useCallback(() => {
    setDragging(null);
  }, []);

  // Auto-layout on first mount if nodes exist
  useEffect(() => {
    if (nodes.length > 0 && nodes[0].x === 0 && nodes[0].y === 0) {
      autoLayout();
    }
  }, []);

  return (
    <div
      ref={canvasRef}
      className="flex-1 relative bg-[#f8f9fa] overflow-hidden"
      onDrop={onDrop}
      onDragOver={(e) => e.preventDefault()}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseUp}
    >
      {/* Grid background */}
      <div
        className="absolute inset-0 opacity-30"
        style={{
          backgroundImage:
            "linear-gradient(#e5e7eb 1px, transparent 1px), linear-gradient(90deg, #e5e7eb 1px, transparent 1px)",
          backgroundSize: "20px 20px",
        }}
      />

      {/* Edges */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none">
        <defs>
          <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#94a3b8" />
          </marker>
        </defs>
        {edges.map((edge) => {
          const src = nodes.find((n) => n.id === edge.source);
          const tgt = nodes.find((n) => n.id === edge.target);
          if (!src || !tgt) return null;
          return (
            <line
              key={edge.id}
              x1={src.x + 120}
              y1={src.y + 40}
              x2={tgt.x + 120}
              y2={tgt.y}
              stroke="#94a3b8"
              strokeWidth={2}
              markerEnd="url(#arrowhead)"
            />
          );
        })}
      </svg>

      {/* Nodes */}
      {nodes.map((node) => (
        <div
          key={node.id}
          className={cn(
            "absolute w-60 rounded-lg border-2 shadow-sm cursor-grab active:cursor-grabbing transition-shadow hover:shadow-md bg-white",
            selectedNodeId === node.id ? "border-primary ring-2 ring-primary/20" : "border-gray-200"
          )}
          style={{ left: node.x, top: node.y }}
          onMouseDown={(e) => onMouseDown(e, node.id)}
        >
          <div
            className={cn(
              "px-3 py-2 rounded-t-md border-b flex items-center gap-2",
              CATEGORY_COLORS[node.category] || "bg-gray-50 border-gray-200"
            )}
          >
            <GripVertical className="w-3.5 h-3.5 opacity-50" />
            <span className="text-xs font-semibold truncate flex-1">{node.module}</span>
            <span className="text-[10px] opacity-60">{node.id}</span>
          </div>
          <div className="px-3 py-2">
            <p className="text-[11px] text-muted-foreground line-clamp-2">{node.description}</p>
            {Object.keys(node.params).length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {Object.entries(node.params).slice(0, 3).map(([k, v]) => (
                  <Badge key={k} variant="outline" className="text-[9px] h-4">
                    {k}={String(v).slice(0, 12)}
                  </Badge>
                ))}
                {Object.keys(node.params).length > 3 && (
                  <Badge variant="outline" className="text-[9px] h-4">
                    +{Object.keys(node.params).length - 3}
                  </Badge>
                )}
              </div>
            )}
          </div>
        </div>
      ))}

      {nodes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center text-muted-foreground">
            <Plus className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p className="text-sm font-medium">Drag bricks here to build your workflow</p>
            <p className="text-xs mt-1">Start with Data Validator, then add analysis modules</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ───────────────────────────────────────────────────────────────
// MAIN PAGE
// ───────────────────────────────────────────────────────────────
export default function WorkflowBuilder() {
  const navigate = useNavigate();
  const {
    nodes,
    setRegistry,
    clearWorkflow,
    toPlanJSON,
    isRunning,
    runEvents,
    setRunning,
    addRunEvent,
    clearRunEvents,
    autoLayout,
  } = useWorkflowStore();
  const [sessionId, setSessionId] = useState("");

  // Fetch module registry on mount
  useEffect(() => {
    axios
      .get(`${API_BASE}/agent/modules`)
      .then((res) => {
        setRegistry(res.data.modules, res.data.categories);
      })
      .catch((err) => console.error("Failed to load modules:", err));
  }, [setRegistry]);

  const handleRun = async () => {
    if (!sessionId) {
      alert("Please enter a session ID with uploaded data");
      return;
    }
    if (nodes.length === 0) {
      alert("Workflow is empty");
      return;
    }
    clearRunEvents();
    setRunning(true);

    const plan = toPlanJSON();
    try {
      const response = await fetch(`${API_BASE}/agent/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, plan }),
      });

      const reader = response.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        for (const line of chunk.split("\n")) {
          if (line.startsWith("data: ")) {
            try {
              const event = JSON.parse(line.slice(6));
              addRunEvent(event);
              if (event.event_type === "complete" || event.event_type === "error") {
                setRunning(false);
              }
            } catch {
              // ignore
            }
          }
        }
      }
    } catch (err) {
      console.error("Execution failed:", err);
      setRunning(false);
    }
  };

  const failedSteps = runEvents.filter((e) => e.event_type === "step_error");
  const completedSteps = runEvents.filter((e) => e.event_type === "step_complete");

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <header className="h-14 border-b bg-background flex items-center px-4 gap-3">
        <h1 className="font-semibold text-sm flex items-center gap-2">
          <Zap className="w-4 h-4 text-primary" />
          Workflow Builder
        </h1>
        <div className="flex-1" />
        <div className="flex items-center gap-2">
          <Input
            placeholder="Session ID"
            className="h-8 w-40 text-xs"
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
          />
          <Button variant="outline" size="sm" className="h-8 text-xs gap-1" onClick={autoLayout}>
            <ArrowDown className="w-3.5 h-3.5" />
            Layout
          </Button>
          <Button variant="outline" size="sm" className="h-8 text-xs gap-1" onClick={clearWorkflow}>
            <RotateCcw className="w-3.5 h-3.5" />
            Clear
          </Button>
          <Button
            size="sm"
            className="h-8 text-xs gap-1"
            onClick={handleRun}
            disabled={isRunning || nodes.length === 0}
          >
            {isRunning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            Run Workflow
          </Button>
        </div>
      </header>

      {/* Main */}
      <div className="flex-1 flex overflow-hidden">
        <ModulePalette />
        <DAGCanvas />
        <ParamPanel />
      </div>

      {/* Status bar */}
      <footer className="h-8 border-t bg-background flex items-center px-4 text-[11px] text-muted-foreground gap-4">
        <span>{nodes.length} bricks</span>
        {isRunning && <span className="flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" /> Running…</span>}
        {completedSteps.length > 0 && <span className="text-green-600">{completedSteps.length} completed</span>}
        {failedSteps.length > 0 && <span className="text-red-600">{failedSteps.length} failed</span>}
      </footer>
    </div>
  );
}
