import { create } from 'zustand';
import type { Edge, Node } from '@xyflow/react';
import type { Pipeline } from '../../api/types';

interface PipelineStore {
  pipeline: Pipeline | null;
  nodes: Node[];
  edges: Edge[];
  selectedNodeId: string | null;
  isDirty: boolean;
  executionId: string | null;

  setPipeline: (pipeline: Pipeline) => void;
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;
  setSelectedNodeId: (id: string | null) => void;
  updateNodeData: (nodeId: string, data: Record<string, unknown>) => void;
  markClean: () => void;
  setExecutionId: (id: string | null) => void;
}

export const usePipelineStore = create<PipelineStore>((set) => ({
  pipeline: null,
  nodes: [],
  edges: [],
  selectedNodeId: null,
  isDirty: false,
  executionId: null,

  setPipeline: (pipeline) =>
    set({
      pipeline,
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
      isDirty: false,
    }),

  setNodes: (nodes) => set({ nodes, isDirty: true }),
  setEdges: (edges) => set({ edges, isDirty: true }),
  setSelectedNodeId: (id) => set({ selectedNodeId: id }),

  updateNodeData: (nodeId, data) =>
    set((state) => ({
      nodes: state.nodes.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, ...data } } : n
      ),
      isDirty: true,
    })),

  markClean: () => set({ isDirty: false }),
  setExecutionId: (id) => set({ executionId: id }),
}));
