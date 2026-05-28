import { useEffect, useState } from 'react';

interface Props {
  data: Record<string, unknown>;
  onChange: (data: Record<string, unknown>) => void;
}

interface ScenarioItem {
  id: string;
  name: string;
  map_name: string;
  duration_seconds: number;
}

export function SceneReplayForm({ data, onChange }: Props) {
  const [scenarios, setScenarios] = useState<ScenarioItem[]>([]);

  useEffect(() => {
    fetch('/scenario-assets')
      .then(r => r.json())
      .then(setScenarios)
      .catch(() => {});
  }, []);

  return (
    <div className="space-y-3">
      <label className="block text-xs font-medium text-zinc-500">选择场景</label>
      <select
        className="w-full rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1.5 text-sm"
        value={(data.scenario_id as string) || ''}
        onChange={(e) => {
          const s = scenarios.find(item => item.id === e.target.value);
          onChange({ ...data, scenario_id: e.target.value, scenario_name: s?.name || '' });
        }}
      >
        <option value="">-- 选择场景 --</option>
        {scenarios.map((s) => (
          <option key={s.id} value={s.id}>{s.name} ({s.map_name}, {s.duration_seconds}s)</option>
        ))}
      </select>
      {typeof data.scenario_name === 'string' && data.scenario_name && (
        <div className="text-xs text-zinc-400">已选: {data.scenario_name}</div>
      )}
    </div>
  );
}
