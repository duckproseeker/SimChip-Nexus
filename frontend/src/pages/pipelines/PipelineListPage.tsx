import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { createPipeline, deletePipeline, listPipelines } from '../../api/pipelines';

export default function PipelineListPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: pipelines = [] } = useQuery({
    queryKey: ['pipelines'],
    queryFn: listPipelines,
  });

  const create = useMutation({
    mutationFn: () => createPipeline('New Pipeline'),
    onSuccess: (p) => navigate(`/pipelines/${p.pipeline_id}`),
  });

  const remove = useMutation({
    mutationFn: deletePipeline,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipelines'] }),
  });

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-zinc-800 dark:text-zinc-100">Pipelines</h1>
        <button
          onClick={() => create.mutate()}
          disabled={create.isPending}
          className="px-4 py-2 text-sm rounded bg-blue-500 hover:bg-blue-600 text-white font-medium disabled:opacity-50"
        >
          New Pipeline
        </button>
      </div>

      {pipelines.length === 0 ? (
        <div className="rounded-lg border border-zinc-200 dark:border-zinc-700 p-8 text-center">
          <p className="text-sm text-zinc-400">No pipelines yet. Create one to get started.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {pipelines.map((p) => (
            <div
              key={p.pipeline_id}
              className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-4 py-3 flex items-center gap-3"
            >
              <button
                onClick={() => navigate(`/pipelines/${p.pipeline_id}`)}
                className="flex-1 text-left"
              >
                <div className="font-medium text-zinc-800 dark:text-zinc-100">{p.name}</div>
                <div className="text-xs text-zinc-400">
                  {p.nodes.length} nodes · {p.edges.length} edges
                </div>
              </button>
              <button
                onClick={() => remove.mutate(p.pipeline_id)}
                className="text-xs text-zinc-400 hover:text-red-400"
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
