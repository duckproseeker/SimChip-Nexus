import { create } from 'zustand';
import type { Node, Edge, Connection } from '@xyflow/react';
import type { IsValidConnection } from '@xyflow/react';
import type { Pipeline } from '../../api/types';
import { NODE_SPECS } from '../../components/pipeline/nodes';

interface PipelineStore {
  pipelineId: string | null;
  pipelineName: string | null;
  nodes: Node[];
  edges: Edge[];
  selectedNodeId: string | null;
  dirty: boolean;
  executionId: string | null;
  showTour: boolean;

  setPipeline: (pipeline: Pipeline) => void;
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;
  setSelectedNodeId: (id: string | null) => void;
  updateNodeData: (nodeId: string, data: Record<string, unknown>) => void;
  markClean: () => void;
  setExecutionId: (id: string | null) => void;
  setShowTour: (show: boolean) => void;
  isValidConnection: IsValidConnection<Edge>;
}

export const usePipelineStore = create<PipelineStore>((set, get) => ({
  pipelineId: null,
  pipelineName: null,
  nodes: [],
  edges: [],
  selectedNodeId: null,
  dirty: false,
  executionId: null,
  showTour: !localStorage.getItem('pipeline_tour_done'),

  setPipeline: (pipeline) =>
    set({
      pipelineId: pipeline.pipeline_id,
      pipelineName: pipeline.name,
      nodes: pipeline.nodes.map((n) => ({
        id: n.node_id,
        type: n.type,
        position: n.position,
        data: n.data,
      })),
      edges: pipeline.edges.map((e) => ({
        id: e.edge_id,
        source: e.source,
        sourceHandle: e.source_handle,
        target: e.target,
        targetHandle: e.target_handle,
      })),
      dirty: false,
    }),

  setNodes: (nodes) => set({ nodes, dirty: true }),
  setEdges: (edges) => set({ edges, dirty: true }),
  setSelectedNodeId: (id) => set({ selectedNodeId: id }),

  updateNodeData: (nodeId, data) =>
    set((state) => ({
      nodes: state.nodes.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, ...data } } : n
      ),
      dirty: true,
    })),

  markClean: () => set({ dirty: false }),
  setExecutionId: (id) => set({ executionId: id }),

  setShowTour: (show) => {
    if (!show) localStorage.setItem('pipeline_tour_done', '1');
    set({ showTour: show });
  },

  isValidConnection: (connection) => {
    const { nodes } = get();
    const sourceNode = nodes.find((n) => n.id === connection.source);
    const targetNode = nodes.find((n) => n.id === connection.target);
    if (!sourceNode || !targetNode) return false;
    const sourceSpec = NODE_SPECS[sourceNode.type!];
    const targetSpec = NODE_SPECS[targetNode.type!];
    if (!sourceSpec || !targetSpec) return false;
    return connection.sourceHandle === connection.targetHandle;
  },
}));
