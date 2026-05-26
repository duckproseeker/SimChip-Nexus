import { Handle, Position, type NodeProps } from '@xyflow/react';

export function SensorCameraNode({ data, selected }: NodeProps) {
  const res = data.width && data.height ? `${data.width}×${data.height}` : '';
  return (
    <div className={`rounded-lg border-2 bg-white dark:bg-zinc-900 px-4 py-3 min-w-[160px] shadow-sm ${selected ? 'border-blue-500' : 'border-zinc-200 dark:border-zinc-700'}`}>
      <div className="text-xs font-semibold uppercase tracking-wide text-zinc-400 mb-1">摄像头</div>
      <div className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
        {(data.sensor_id as string) || 'Camera'}
      </div>
      {res && <div className="text-xs text-zinc-400">{res}{data.fov ? ` · ${data.fov}°` : ''}</div>}
      <Handle type="source" position={Position.Right} id="sensor" />
    </div>
  );
}
