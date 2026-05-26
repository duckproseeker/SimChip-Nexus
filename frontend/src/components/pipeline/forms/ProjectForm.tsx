import { useQuery } from '@tanstack/react-query';
import { fetchProjects } from '../../../api/pipelines';

interface Props {
  data: Record<string, unknown>;
  onChange: (d: Record<string, unknown>) => void;
}

export function ProjectForm({ data, onChange }: Props) {
  const { data: projects = [], isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: fetchProjects,
  });

  return (
    <div className="flex flex-col gap-3">
      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-zinc-500">项目</span>
        <select
          className="rounded border border-zinc-200 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1.5 text-sm text-zinc-800 dark:text-zinc-100 focus:outline-none focus:border-blue-400"
          value={(data.project_id as string) ?? ''}
          onChange={(e) => {
            const selected = projects.find((p) => p.project_id === e.target.value);
            onChange({ project_id: e.target.value, project_name: selected?.name ?? '' });
          }}
        >
          <option value="">{isLoading ? '加载中…' : '选择项目'}</option>
          {projects.map((p) => (
            <option key={p.project_id} value={p.project_id}>{p.name}</option>
          ))}
        </select>
      </label>
    </div>
  );
}
