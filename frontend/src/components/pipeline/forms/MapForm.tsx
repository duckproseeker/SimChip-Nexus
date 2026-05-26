const MAP_OPTIONS = [
  'Town01_Opt', 'Town02_Opt', 'Town03_Opt', 'Town04_Opt', 'Town05_Opt',
  'Town06_Opt', 'Town07_Opt', 'Town10HD_Opt',
  'Town01', 'Town02', 'Town03', 'Town04', 'Town05', 'Town06', 'Town07', 'Town10HD',
];

interface Props {
  data: Record<string, unknown>;
  onChange: (d: Record<string, unknown>) => void;
}

export function MapForm({ data, onChange }: Props) {
  return (
    <div className="flex flex-col gap-3">
      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-zinc-500">地图</span>
        <select
          className="rounded border border-zinc-200 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1.5 text-sm text-zinc-800 dark:text-zinc-100 focus:outline-none focus:border-blue-400"
          value={(data.map_name as string) ?? ''}
          onChange={(e) => onChange({ map_name: e.target.value })}
        >
          <option value="">选择地图</option>
          {MAP_OPTIONS.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </label>
    </div>
  );
}
