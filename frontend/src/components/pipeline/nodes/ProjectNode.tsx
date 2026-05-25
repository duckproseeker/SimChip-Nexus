import { Handle, Position, type NodeProps } from '@xyflow/react';

export function ProjectNode({ data, selected }: NodeProps) {
  return (
    <div className={`rounded-lg border-2 bg-white dark:bg-zinc-900 px-4 py-3 min-w-[160px] shadow-sm ${selected ? 'border-blue-500' : 'border-zinc-200 dark:border-zinc-700'}`}>
      <div className="text-xs font-semibold uppercase tracking-wide text-zinc-400 mb-1">Project</div>
      <div className="text-sm font-medium truncate text-zinc-800 dark:text-zinc-100">
        {(data.project_id as string) || 'Not selected'}
      </div>
      <Handle type="source" position={Position.Right} id="project_id" />
    </div>
  );
}
