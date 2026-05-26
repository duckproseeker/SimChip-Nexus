import { useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ReactFlowProvider } from '@xyflow/react';
import { getPipeline, updatePipeline } from '../../api/pipelines';
import { usePipelineStore } from '../../features/pipeline/store';
import { NodeLibrary } from '../../components/pipeline/NodeLibrary';
import { PipelineCanvas } from '../../components/pipeline/PipelineCanvas';
import { PropertyPanel } from '../../components/pipeline/PropertyPanel';
import { EditorToolbar } from '../../components/pipeline/EditorToolbar';
import type { PipelineNodeDef } from '../../api/types';

export default function PipelineEditorPage() {
  const { id } = useParams<{ id: string }>();
  const { setPipeline, nodes, edges, isDirty, markClean } = usePipelineStore();
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { data: pipeline } = useQuery({
    queryKey: ['pipeline', id],
    queryFn: () => getPipeline(id!),
    enabled: !!id,
  });

  useEffect(() => {
    if (pipeline) setPipeline(pipeline);
  }, [pipeline, setPipeline]);

  // Debounced auto-save
  useEffect(() => {
    if (!isDirty || !id) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      await updatePipeline(id, {
        nodes: nodes.map((n) => ({
          node_id: n.id,
          type: n.type as PipelineNodeDef['type'],
          position: n.position as { x: number; y: number },
          data: (n.data ?? {}) as Record<string, unknown>,
        })),
        edges: edges.map((e) => ({
          edge_id: e.id,
          source: e.source,
          source_handle: e.sourceHandle ?? '',
          target: e.target,
          target_handle: e.targetHandle ?? '',
        })),
      });
      markClean();
    }, 500);
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, [isDirty, nodes, edges, id, markClean]);

  return (
    <ReactFlowProvider>
      <div className="flex flex-col h-screen">
        <EditorToolbar />
        <div className="flex flex-1 overflow-hidden">
          <NodeLibrary />
          <PipelineCanvas />
          <PropertyPanel />
        </div>
      </div>
    </ReactFlowProvider>
  );
}
