import { Handle, Position, type NodeProps } from '@xyflow/react';

const STATUS_CLASS: Record<string, string> = {
  IDLE: 'text-zinc-400', PENDING: 'text-zinc-400',
  RUNNING: 'text-blue-500', COMPLETED: 'text-green-500',
  FAILED: 'text-red-500', STOPPED: 'text-yellow-500',
};

export function ReplayRunNode({ data, selected }: NodeProps) {
  const status = (data.executionStatus as string) || 'IDLE';
  return (
    <div className={`rounded-lg border-2 bg-white dark:bg-zinc-900 px-4 py-3 min-w-[160px] shadow-sm ${selected ? 'border-blue-500' : 'border-zinc-200 dark:border-zinc-700'}`}>
      <Handle type="target" position={Position.Left} id="project" style={{ top: '25%' }} />
      <Handle type="target" position={Position.Left} id="recording" style={{ top: '50%' }} />
      <Handle type="target" position={Position.Left} id="sensor" style={{ top: '75%' }} />
      <div className="text-xs font-semibold uppercase tracking-wide text-zinc-400 mb-1">录制回放</div>
      <div className={`text-sm font-medium ${STATUS_CLASS[status] ?? 'text-zinc-800 dark:text-zinc-100'}`}>{status}</div>
      {(data.run_id as string) && (
        <div className="text-xs text-zinc-400 font-mono">{(data.run_id as string).slice(0, 8)}</div>
      )}
      <Handle type="source" position={Position.Right} id="run_id" />
    </div>
  );
}
