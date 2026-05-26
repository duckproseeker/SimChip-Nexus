import { Handle, Position, type NodeProps } from '@xyflow/react';

export function ScenarioNode({ data, selected }: NodeProps) {
  return (
    <div className={`rounded-lg border-2 bg-white dark:bg-zinc-900 px-4 py-3 min-w-[180px] shadow-sm ${selected ? 'border-blue-500' : 'border-zinc-200 dark:border-zinc-700'}`}>
      <div className="text-xs font-semibold uppercase tracking-wide text-zinc-400 mb-1">场景</div>
      <div className="text-sm font-medium truncate text-zinc-800 dark:text-zinc-100">
        {(data.display_name as string) || (data.scenario_name as string) || '未选择'}
      </div>
      <Handle type="source" position={Position.Right} id="scenario" />
    </div>
  );
}
