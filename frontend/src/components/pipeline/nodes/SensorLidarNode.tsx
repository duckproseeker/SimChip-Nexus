import { Handle, Position, type NodeProps } from '@xyflow/react';

export function SensorLidarNode({ data, selected }: NodeProps) {
  return (
    <div className={`rounded-lg border-2 bg-white dark:bg-zinc-900 px-4 py-3 min-w-[160px] shadow-sm ${selected ? 'border-blue-500' : 'border-zinc-200 dark:border-zinc-700'}`}>
      <div className="text-xs font-semibold uppercase tracking-wide text-zinc-400 mb-1">激光雷达</div>
      <div className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
        {(data.sensor_id as string) || 'LiDAR'}
      </div>
      {data.channels != null ? <div className="text-xs text-zinc-400">{String(data.channels)}ch · {String(data.range)}m</div> : null}
      <Handle type="source" position={Position.Right} id="sensor" />
    </div>
  );
}
