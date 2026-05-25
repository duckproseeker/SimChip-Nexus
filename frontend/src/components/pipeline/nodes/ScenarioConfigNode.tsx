import { Handle, Position, type NodeProps } from '@xyflow/react';

export function ScenarioConfigNode({ data, selected }: NodeProps) {
  return (
    <div className={`rounded-lg border-2 bg-white dark:bg-zinc-900 px-4 py-3 min-w-[180px] shadow-sm ${selected ? 'border-blue-500' : 'border-zinc-200 dark:border-zinc-700'}`}>
      <Handle type="target" position={Position.Left} id="project_id" />
      <div className="text-xs font-semibold uppercase tracking-wide text-zinc-400 mb-1">Scenario</div>
      <div className="text-sm font-medium truncate text-zinc-800 dark:text-zinc-100">
        {(data.scenario_name as string) || 'Not selected'}
      </div>
      {(data.map_name as string) && (
        <div className="text-xs text-zinc-400 truncate">{data.map_name as string}</div>
      )}
      <Handle type="source" position={Position.Right} id="scenario_config" />
    </div>
  );
}
