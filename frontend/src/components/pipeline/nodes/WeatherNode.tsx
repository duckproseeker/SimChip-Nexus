import { Handle, Position, type NodeProps } from '@xyflow/react';

export function WeatherNode({ data, selected }: NodeProps) {
  const label = (data.weather_preset_id as string)
    ? (data.display_name as string) || (data.weather_preset_id as string)
    : data.weather_custom
    ? '自定义'
    : '未设置';

  return (
    <div className={`rounded-lg border-2 bg-white dark:bg-zinc-900 px-4 py-3 min-w-[160px] shadow-sm ${selected ? 'border-blue-500' : 'border-zinc-200 dark:border-zinc-700'}`}>
      <div className="text-xs font-semibold uppercase tracking-wide text-zinc-400 mb-1">天气</div>
      <div className="text-sm font-medium truncate text-zinc-800 dark:text-zinc-100">{label}</div>
      <Handle type="source" position={Position.Right} id="weather" />
    </div>
  );
}
