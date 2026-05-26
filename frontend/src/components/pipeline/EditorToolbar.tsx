import { useNavigate } from 'react-router-dom';
import { usePipelineStore } from '../../features/pipeline/store';
import {
  updatePipeline,
  validatePipeline,
  executePipeline,
} from '../../api/pipelines';
import type { PipelineNodeDef, PipelineEdgeDef } from '../../api/types';

const SENSOR_TYPE_MAP: Record<string, string> = {
  sensor_camera: 'sensor.camera.rgb',
  sensor_lidar:  'sensor.lidar.ray_cast',
  sensor_radar:  'sensor.other.radar',
  sensor_gnss:   'sensor.other.gnss',
  sensor_imu:    'sensor.other.imu',
};

export function EditorToolbar() {
  const { pipeline, nodes, edges, isDirty, markClean, setExecutionId, updateNodeData } =
    usePipelineStore();
  const navigate = useNavigate();

  const buildPatch = () => ({
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

  const handleSave = async () => {
    if (!pipeline) return;
    await updatePipeline(pipeline.pipeline_id, buildPatch());
    markClean();
  };

  const handleRun = async () => {
    if (!pipeline) return;

    // Assemble sensors from canvas sensor nodes and write into run nodes
    const sensorNodes = nodes.filter((n) =>
      Object.keys(SENSOR_TYPE_MAP).includes(n.type ?? '')
    );
    const assembledSensors = sensorNodes.map((n) => ({
      id: n.data.sensor_id,
      type: SENSOR_TYPE_MAP[n.type!],
      ...n.data,
    }));

    // Write assembled_sensors into each live_run and replay_run node
    for (const n of nodes) {
      if (n.type === 'live_run' || n.type === 'replay_run') {
        updateNodeData(n.id, { assembled_sensors: assembledSensors });
      }
    }

    await handleSave();
    const result = await validatePipeline(pipeline.pipeline_id);
    if (!result.valid) {
      alert(result.errors.map((e) => e.message).join('\n'));
      return;
    }
    const execution = await executePipeline(pipeline.pipeline_id);
    setExecutionId(execution.execution_id);
    navigate(`/pipelines/${pipeline.pipeline_id}/run/${execution.execution_id}`);
  };

  return (
    <header className="flex items-center gap-3 border-b border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-4 py-2 h-12 shrink-0">
      <span className="font-medium text-sm flex-1 truncate text-zinc-800 dark:text-zinc-100">
        {pipeline?.name ?? 'Untitled Pipeline'}
      </span>
      {isDirty && <span className="text-xs text-zinc-400">Unsaved</span>}
      <button
        onClick={handleSave}
        className="px-3 py-1 text-sm rounded border border-zinc-200 dark:border-zinc-600 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-700 dark:text-zinc-200"
      >
        Save
      </button>
      <button
        onClick={handleRun}
        className="px-3 py-1 text-sm rounded bg-blue-500 hover:bg-blue-600 text-white font-medium"
      >
        Run
      </button>
    </header>
  );
}
