import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ReactFlowProvider } from '@xyflow/react';
import { getPipeline, updatePipeline } from '../../api/pipelines';
import { usePipelineStore } from '../../features/pipeline/store';
import { NodeLibrary } from '../../components/pipeline/NodeLibrary';
import { PipelineCanvas } from '../../components/pipeline/PipelineCanvas';
import { PropertyPanel } from '../../components/pipeline/PropertyPanel';
import { EditorToolbar } from '../../components/pipeline/EditorToolbar';
import { TemplateSelector } from '../../components/pipeline/TemplateSelector';
import { GuidedTour } from '../../components/pipeline/GuidedTour';
import type { PipelineNodeDef, PipelineEdgeDef } from '../../api/types';
import type { PipelineTemplate } from '../../features/pipeline/templates';

export default function PipelineEditorPage() {
  const { id } = useParams<{ id: string }>();
  const { setPipeline, setNodes, setEdges, nodes, edges, dirty, markClean, showTour, setShowTour } =
    usePipelineStore();
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [showTemplates, setShowTemplates] = useState(false);

  const { data: pipeline } = useQuery({
    queryKey: ['pipeline', id],
    queryFn: () => getPipeline(id!),
    enabled: !!id,
  });

  useEffect(() => {
    if (pipeline) {
      setPipeline(pipeline);
      if (pipeline.nodes.length === 0) {
        setShowTemplates(true);
      }
    }
  }, [pipeline, setPipeline]);

  const handleTemplateSelect = (template: PipelineTemplate) => {
    setNodes(template.nodes);
    setEdges(template.edges);
    setShowTemplates(false);
  };

  // Debounced auto-save
  useEffect(() => {
    if (!dirty || !id) return;
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
        })) as PipelineEdgeDef[],
      });
      markClean();
    }, 500);
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, [dirty, nodes, edges, id, markClean]);

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
      {showTemplates && (
        <TemplateSelector
          onSelect={handleTemplateSelect}
          onClose={() => setShowTemplates(false)}
        />
      )}
      {showTour && <GuidedTour onDismiss={() => setShowTour(false)} />}
    </ReactFlowProvider>
  );
}
