import { useQuery } from '@tanstack/react-query';
import { fetchEnvironmentPresets } from '../../../api/pipelines';

interface Props {
  data: Record<string, unknown>;
  onChange: (d: Record<string, unknown>) => void;
}

export function WeatherForm({ data, onChange }: Props) {
  const { data: presets = [], isLoading } = useQuery({
    queryKey: ['environment-presets'],
    queryFn: fetchEnvironmentPresets,
  });

  const isCustom = !data.weather_preset_id && data.weather_custom;

  const numField = (key: string, label: string, min = 0, max = 100) => (
    <label key={key} className="flex flex-col gap-1">
      <span className="text-xs font-medium text-zinc-500">{label}</span>
      <input
        type="number" min={min} max={max}
        className="rounded border border-zinc-200 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1.5 text-sm text-zinc-800 dark:text-zinc-100 focus:outline-none focus:border-blue-400"
        value={((data.weather_custom as Record<string, number> | undefined)?.[key] ?? '') as string}
        onChange={(e) => onChange({
          weather_preset_id: '',
          weather_custom: { ...(data.weather_custom as object ?? {}), [key]: Number(e.target.value) },
        })}
      />
    </label>
  );

  return (
    <div className="flex flex-col gap-3">
      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-zinc-500">天气预设</span>
        <select
          className="rounded border border-zinc-200 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1.5 text-sm text-zinc-800 dark:text-zinc-100 focus:outline-none focus:border-blue-400"
          value={(data.weather_preset_id as string) ?? ''}
          onChange={(e) => onChange({ weather_preset_id: e.target.value, weather_custom: null })}
        >
          <option value="">{isLoading ? '加载中…' : '选择预设'}</option>
          {presets.map((p) => (
            <option key={p.preset_id} value={p.preset_id}>{p.display_name}</option>
          ))}
        </select>
      </label>
      <div className="text-xs text-zinc-400">或自定义参数：</div>
      {numField('precipitation', '降水量', 0, 100)}
      {numField('cloudiness', '云量', 0, 100)}
      {numField('fog_density', '雾密度', 0, 100)}
      {numField('wetness', '路面湿度', 0, 100)}
      {isCustom ? <div className="text-xs text-zinc-400">使用自定义天气</div> : null}
    </div>
  );
}
