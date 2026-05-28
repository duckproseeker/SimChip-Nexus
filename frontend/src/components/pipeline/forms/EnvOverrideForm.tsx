interface Props {
  data: Record<string, unknown>;
  onChange: (data: Record<string, unknown>) => void;
}

const WEATHER_PRESETS = [
  { id: 'clear_noon', label: '晴天正午' },
  { id: 'clear_night', label: '晴天夜晚' },
  { id: 'cloudy_noon', label: '多云正午' },
  { id: 'cloudy_night', label: '多云夜晚' },
  { id: 'rain_noon', label: '中雨正午' },
  { id: 'rain_night', label: '雨天日落' },
  { id: 'heavy_rain', label: '暴雨' },
  { id: 'fog_morning', label: '雾天清晨' },
  { id: 'fog_night', label: '雾天夜晚' },
  { id: 'wet_noon', label: '湿地正午' },
  { id: 'wet_night', label: '湿地夜晚' },
];

export function EnvOverrideForm({ data, onChange }: Props) {
  return (
    <div className="space-y-3">
      <label className="block text-xs font-medium text-zinc-500">天气预设</label>
      <select
        className="w-full rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1.5 text-sm"
        value={(data.weather_preset as string) || ''}
        onChange={(e) => onChange({ ...data, weather_preset: e.target.value })}
      >
        <option value="">-- 不覆盖 --</option>
        {WEATHER_PRESETS.map(p => (
          <option key={p.id} value={p.id}>{p.label}</option>
        ))}
      </select>
      <label className="block text-xs font-medium text-zinc-500">太阳高度角</label>
      <input
        type="number"
        className="w-full rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1.5 text-sm"
        placeholder="45"
        value={(data.sun_altitude as number) ?? ''}
        onChange={(e) => onChange({ ...data, sun_altitude: Number(e.target.value) })}
      />
    </div>
  );
}
