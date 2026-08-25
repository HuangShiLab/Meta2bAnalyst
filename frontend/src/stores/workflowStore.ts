import { create } from "zustand";

export interface WorkflowNode {
  id: string;
  module: string;
  category: string;
  description: string;
  params: Record<string, any>;
  depends_on: string[];
  x: number;
  y: number;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
}

export interface StepResult {
  module: string;
  status: "complete" | "error";
  elapsed_time?: number;
  has_plot?: boolean;
  plot_omitted?: boolean;
  plot?: any;
  summary?: Record<string, any>;
  error?: string;
}

interface WorkflowState {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  selectedNodeId: string | null;
  moduleRegistry: Record<string, any> | null;
  categories: string[];
  isRunning: boolean;
  runEvents: any[];
  stepResults: Record<string, StepResult>;

  // Actions
  setRegistry: (registry: Record<string, any>, categories: string[]) => void;
  addNode: (module: string, category: string, description: string, x: number, y: number) => void;
  removeNode: (id: string) => void;
  selectNode: (id: string | null) => void;
  updateNodeParams: (id: string, params: Record<string, any>) => void;
  moveNode: (id: string, x: number, y: number) => void;
  autoLayout: () => void;
  clearWorkflow: () => void;
  setRunning: (running: boolean) => void;
  addRunEvent: (event: any) => void;
  recordStepResult: (stepId: string, result: StepResult) => void;
  clearRunEvents: () => void;
  loadWorkflow: (plan: any, layout?: { id: string; x: number; y: number }[] | null) => void;
  toPlanJSON: () => any;
}

let nodeCounter = 0;

export const useWorkflowStore = create<WorkflowState>((set, get) => ({
  nodes: [],
  edges: [],
  selectedNodeId: null,
  moduleRegistry: null,
  categories: [],
  isRunning: false,
  runEvents: [],
  stepResults: {},

  setRegistry: (registry, categories) => set({ moduleRegistry: registry, categories }),

  addNode: (module, category, description, x, y) => {
    const id = `step_${++nodeCounter}`;
    const node: WorkflowNode = {
      id,
      module,
      category,
      description,
      params: {},
      depends_on: [],
      x,
      y,
    };
    set((state) => {
      const nodes = [...state.nodes, node];
      const edges = computeEdges(nodes);
      return { nodes, edges, selectedNodeId: id };
    });
  },

  removeNode: (id) => {
    set((state) => {
      const nodes = state.nodes.filter((n) => n.id !== id);
      const edges = computeEdges(nodes);
      return { nodes, edges, selectedNodeId: state.selectedNodeId === id ? null : state.selectedNodeId };
    });
  },

  selectNode: (id) => set({ selectedNodeId: id }),

  updateNodeParams: (id, params) => {
    set((state) => ({
      nodes: state.nodes.map((n) => (n.id === id ? { ...n, params: { ...n.params, ...params } } : n)),
    }));
  },

  moveNode: (id, x, y) => {
    set((state) => ({
      nodes: state.nodes.map((n) => (n.id === id ? { ...n, x, y } : n)),
    }));
  },

  autoLayout: () => {
    set((state) => {
      const nodes = state.nodes.map((n, i) => ({ ...n, x: 300, y: 80 + i * 120 }));
      const edges = computeEdges(nodes);
      return { nodes, edges };
    });
  },

  clearWorkflow: () => set({ nodes: [], edges: [], selectedNodeId: null, runEvents: [], stepResults: {} }),

  setRunning: (running) => set({ isRunning: running }),

  addRunEvent: (event) => set((state) => ({ runEvents: [...state.runEvents, event] })),

  recordStepResult: (stepId, result) =>
    set((state) => ({ stepResults: { ...state.stepResults, [stepId]: result } })),

  clearRunEvents: () => set({ runEvents: [], stepResults: {} }),

  loadWorkflow: (plan, layout) => {
    const layoutMap = new Map((layout || []).map((l) => [l.id, l]));
    const nodes: WorkflowNode[] = (plan?.steps || []).map((s: any, i: number) => {
      const pos = layoutMap.get(s.id);
      return {
        id: s.id,
        module: s.module,
        category: "",
        description: s.description || "",
        params: s.params || {},
        depends_on: s.depends_on || [],
        x: pos?.x ?? 300,
        y: pos?.y ?? 80 + i * 120,
      };
    });
    // Keep the id counter ahead of restored ids so new nodes never collide.
    for (const n of nodes) {
      const m = /^step_(\d+)$/.exec(n.id);
      if (m) nodeCounter = Math.max(nodeCounter, parseInt(m[1], 10));
    }
    // Fill categories from the loaded registry when available.
    const registry = get().moduleRegistry;
    if (registry) {
      for (const n of nodes) n.category = registry[n.module]?.category || "";
    }
    set({ nodes, edges: computeEdges(nodes), selectedNodeId: null, runEvents: [], stepResults: {} });
  },

  toPlanJSON: () => {
    const { nodes } = get();
    return {
      query: "custom workflow",
      steps: nodes.map((n) => ({
        id: n.id,
        module: n.module,
        params: n.params,
        depends_on: n.depends_on,
        description: n.description,
      })),
      estimated_time: `${Math.max(1, nodes.length * 2)} minutes`,
      notes: ["Custom workflow built with visual editor"],
    };
  },
}));

function computeEdges(nodes: WorkflowNode[]): WorkflowEdge[] {
  const edges: WorkflowEdge[] = [];
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  for (const target of nodes) {
    for (const dep of target.depends_on) {
      if (nodeMap.has(dep)) {
        edges.push({ id: `${dep}->${target.id}`, source: dep, target: target.id });
      }
    }
  }
  return edges;
}
