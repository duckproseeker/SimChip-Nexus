import { Handle, Position, type NodeProps } from '@xyflow/react';

export function SensorProfileNode({ data, selected }: NodeProps) {
  const sensorCount = Array.isArray(data.sensors) ? (data.sensors as unknown[]).length : 0;
  const label =
    (data.profile_name as string) ||
    (data.sensor_profile_id as string) ||
    'Not configured';

  return (
    <div className={`rounded-lg border-2 bg-white dark:bg-zinc-900 px-4 py-3 min-w-[180px] shadow-sm ${selected ? 'border-blue-500' : 'border-zinc-200 dark:border-zinc-700'}`}>
      <Handle type="target" position={Position.Left} id="project_id" />
      <div className="text-xs font-semibold uppercase tracking-wide text-zinc-400 mb-1">
        Sensor Profile
      </div>
      <div className="text-sm font-medium truncate text-zinc-800 dark:text-zinc-100">{label}</div>
      {sensorCount > 0 && (
        <div className="text-xs text-zinc-400">{sensorCount} sensors</div>
      )}
      <Handle type="source" position={Position.Right} id="sensor_profile_id" />
    </div>
  );
}
