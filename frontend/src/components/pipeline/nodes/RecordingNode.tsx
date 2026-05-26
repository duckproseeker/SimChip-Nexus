import { Handle, Position, type NodeProps } from '@xyflow/react';

export function RecordingNode({ data, selected }: NodeProps) {
  const duration = data.duration_seconds as number | undefined;
  const durationStr = duration ? `${Math.round(duration)}s` : '';

  return (
    <div className={`rounded-lg border-2 bg-white dark:bg-zinc-900 px-4 py-3 min-w-[180px] shadow-sm ${selected ? 'border-blue-500' : 'border-zinc-200 dark:border-zinc-700'}`}>
      <div className="text-xs font-semibold uppercase tracking-wide text-zinc-400 mb-1">场景录制</div>
      <div className="text-sm font-medium truncate text-zinc-800 dark:text-zinc-100">
        {(data.name as string) || '未选择'}
      </div>
      {(data.map_name as string) && (
        <div className="text-xs text-zinc-400 truncate">
          {data.map_name as string}{durationStr ? ` · ${durationStr}` : ''}
        </div>
      )}
      <Handle type="source" position={Position.Right} id="recording" />
    </div>
  );
}
