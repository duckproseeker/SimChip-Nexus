import { Handle, Position, type NodeProps } from '@xyflow/react';

export function ReportNode({ data, selected }: NodeProps) {
  const runId = data.run_id as string | undefined;

  return (
    <div className={`rounded-lg border-2 bg-white dark:bg-zinc-900 px-4 py-3 min-w-[160px] shadow-sm ${selected ? 'border-blue-500' : 'border-zinc-200 dark:border-zinc-700'}`}>
      <Handle type="target" position={Position.Left} id="run_id" />
      <div className="text-xs font-semibold uppercase tracking-wide text-zinc-400 mb-1">Report</div>
      {runId ? (
        <div className="text-xs text-zinc-400 font-mono truncate">{runId.slice(0, 8)}</div>
      ) : (
        <div className="text-sm text-zinc-400">Awaiting run</div>
      )}
    </div>
  );
}
