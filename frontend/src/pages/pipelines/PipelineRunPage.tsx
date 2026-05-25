import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { getPipelineExecution, stopPipelineExecution } from '../../api/pipelines';
import { StatusPill } from '../../components/common/StatusPill';

export default function PipelineRunPage() {
  const { id, eid } = useParams<{ id: string; eid: string }>();

  const { data: execution } = useQuery({
    queryKey: ['pipeline-execution', eid],
    queryFn: () => getPipelineExecution(eid!),
    enabled: !!eid,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'RUNNING' || status === 'PENDING' ? 2000 : false;
    },
  });

  const stop = useMutation({ mutationFn: () => stopPipelineExecution(eid!) });

  const isTerminal =
    execution &&
    ['COMPLETED', 'FAILED', 'STOPPED'].includes(execution.status);

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <div className="mb-6">
        <Link
          to={`/pipelines/${id}`}
          className="text-sm text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
        >
          ← Back to editor
        </Link>
      </div>

      <div className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-zinc-400 mb-1">
              Run Monitor
            </div>
            <div className="text-base font-semibold text-zinc-800 dark:text-zinc-100">
              Pipeline Execution
            </div>
          </div>
          {!isTerminal && (
            <button
              onClick={() => stop.mutate()}
              className="text-xs text-red-400 hover:text-red-300"
            >
              Stop
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 mb-5">
          <span className="text-sm text-zinc-500">Status:</span>
          {execution && <StatusPill status={execution.status} />}
          {!execution && <span className="text-sm text-zinc-400">Loading…</span>}
        </div>

        <div className="flex flex-col gap-2">
          {execution &&
            Object.entries(execution.node_states).map(([nodeId, state]) => (
              <div
                key={nodeId}
                className="flex items-center justify-between rounded border border-zinc-100 dark:border-zinc-700 px-3 py-2"
              >
                <span className="text-sm font-mono text-zinc-600 dark:text-zinc-300">
                  {nodeId}
                </span>
                <div className="flex items-center gap-2">
                  {state.run_id && (
                    <span className="text-xs text-zinc-400 font-mono">
                      {state.run_id.slice(0, 8)}
                    </span>
                  )}
                  <StatusPill status={state.status} />
                </div>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}
