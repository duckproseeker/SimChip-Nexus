interface Props {
  data: Record<string, unknown>;
  onChange: (d: Record<string, unknown>) => void;
}

function numField(key: string, label: string, data: Record<string, unknown>, onChange: (d: Record<string, unknown>) => void, step = 0.1) {
  return (
    <label key={key} className="flex flex-col gap-1">
      <span className="text-xs font-medium text-zinc-500">{label}</span>
      <input type="number" step={step}
        className="rounded border border-zinc-200 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1.5 text-sm text-zinc-800 dark:text-zinc-100 focus:outline-none focus:border-blue-400"
        value={(data[key] as number | string) ?? ''}
        onChange={(e) => onChange({ [key]: Number(e.target.value) })}
      />
    </label>
  );
}

function textField(key: string, label: string, placeholder: string, data: Record<string, unknown>, onChange: (d: Record<string, unknown>) => void) {
  return (
    <label key={key} className="flex flex-col gap-1">
      <span className="text-xs font-medium text-zinc-500">{label}</span>
      <input type="text" placeholder={placeholder}
        className="rounded border border-zinc-200 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1.5 text-sm text-zinc-800 dark:text-zinc-100 focus:outline-none focus:border-blue-400"
        value={(data[key] as string) ?? ''}
        onChange={(e) => onChange({ [key]: e.target.value })}
      />
    </label>
  );
}

export function SensorLidarForm({ data, onChange }: Props) {
  return (
    <div className="flex flex-col gap-3">
      {textField('sensor_id', '传感器 ID', 'lidar_top', data, onChange)}
      <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wide">位置</div>
      <div className="grid grid-cols-3 gap-2">
        {numField('x', 'X', data, onChange)} {numField('y', 'Y', data, onChange)} {numField('z', 'Z', data, onChange)}
      </div>
      <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wide">旋转</div>
      <div className="grid grid-cols-3 gap-2">
        {numField('roll', 'Roll', data, onChange)} {numField('pitch', 'Pitch', data, onChange)} {numField('yaw', 'Yaw', data, onChange)}
      </div>
      <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wide">参数</div>
      {numField('channels', '通道数', data, onChange, 1)}
      {numField('range', '量程 (m)', data, onChange, 1)}
      {numField('points_per_second', '点/秒', data, onChange, 1000)}
      {numField('rotation_frequency', '转速 (Hz)', data, onChange, 1)}
    </div>
  );
}
