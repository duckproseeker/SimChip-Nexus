import { useQuery } from '@tanstack/react-query';
import { fetchScenarioCatalog } from '../../../api/pipelines';

interface Props {
  data: Record<string, unknown>;
  onChange: (d: Record<string, unknown>) => void;
}

export function ScenarioForm({ data, onChange }: Props) {
  const { data: scenarios = [], isLoading } = useQuery({
    queryKey: ['scenarios-catalog'],
    queryFn: fetchScenarioCatalog,
  });

  return (
    <div className="flex flex-col gap-3">
      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-zinc-500">场景</span>
        <select
          className="rounded border border-zinc-200 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1.5 text-sm text-zinc-800 dark:text-zinc-100 focus:outline-none focus:border-blue-400"
          value={(data.scenario_name as string) ?? ''}
          onChange={(e) => {
            const selected = scenarios.find((s) => s.scenario_name === e.target.value);
            onChange({ scenario_name: e.target.value, display_name: selected?.display_name ?? '' });
          }}
        >
          <option value="">{isLoading ? '加载中…' : '选择场景'}</option>
          {scenarios.map((s) => (
            <option key={s.scenario_name} value={s.scenario_name}>{s.display_name || s.scenario_name}</option>
          ))}
        </select>
      </label>
    </div>
  );
}
