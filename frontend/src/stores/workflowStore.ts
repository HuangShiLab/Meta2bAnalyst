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

interface WorkflowState {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  selectedNodeId: string | null;
  moduleRegistry: Record<string, any> | null;
  categories: string[];
  isRunning: boolean;
  runEvents: any[];

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
  clearRunEvents: () => void;
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

  clearWorkflow: () => set({ nodes: [], edges: [], selectedNodeId: null, runEvents: [] }),

  setRunning: (running) => set({ isRunning: running }),

  addRunEvent: (event) => set((state) => ({ runEvents: [...state.runEvents, event] })),

  clearRunEvents: () => set({ runEvents: [] }),

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
