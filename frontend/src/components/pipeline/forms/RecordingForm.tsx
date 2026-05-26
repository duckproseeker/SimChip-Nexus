import { useQuery } from '@tanstack/react-query';
import { fetchRecordings } from '../../../api/pipelines';

interface Props {
  data: Record<string, unknown>;
  onChange: (d: Record<string, unknown>) => void;
}

export function RecordingForm({ data, onChange }: Props) {
  const { data: recordings = [], isLoading } = useQuery({
    queryKey: ['scenario-recordings'],
    queryFn: fetchRecordings,
  });

  return (
    <div className="flex flex-col gap-3">
      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-zinc-500">场景录制</span>
        <select
          className="rounded border border-zinc-200 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1.5 text-sm text-zinc-800 dark:text-zinc-100 focus:outline-none focus:border-blue-400"
          value={(data.recording_id as string) ?? ''}
          onChange={(e) => {
            const rec = recordings.find((r) => r.recording_id === e.target.value);
            onChange({
              recording_id: e.target.value,
              name: rec?.name ?? '',
              map_name: rec?.map_name ?? '',
              duration_seconds: rec?.duration_seconds ?? null,
            });
          }}
        >
          <option value="">{isLoading ? '加载中…' : '选择录制'}</option>
          {recordings.map((r) => (
            <option key={r.recording_id} value={r.recording_id}>
              {r.name || r.recording_id} — {r.map_name}
            </option>
          ))}
        </select>
      </label>
      {(data.map_name as string) && (
        <div className="text-xs text-zinc-400">
          地图: {data.map_name as string}
          {data.duration_seconds ? ` · ${Math.round(data.duration_seconds as number)}s` : ''}
        </div>
      )}
    </div>
  );
}
