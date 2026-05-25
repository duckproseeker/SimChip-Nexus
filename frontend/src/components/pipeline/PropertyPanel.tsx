import { usePipelineStore } from '../../features/pipeline/store';

export function PropertyPanel() {
  const { nodes, selectedNodeId, updateNodeData } = usePipelineStore();
  const node = nodes.find((n) => n.id === selectedNodeId);

  if (!node) {
    return (
      <aside className="w-80 border-l border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 flex items-center justify-center shrink-0">
        <p className="text-sm text-zinc-400 px-4 text-center">
          Select a node to configure it
        </p>
      </aside>
    );
  }

  return (
    <aside className="w-80 border-l border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 overflow-y-auto shrink-0">
      <div className="p-4">
        <div className="text-xs font-semibold uppercase tracking-wide text-zinc-400 mb-1">
          Node Properties
        </div>
        <div className="text-base font-semibold text-zinc-800 dark:text-zinc-100 mb-4 capitalize">
          {node.type?.replace('_', ' ')}
        </div>
        <NodeForm
          node={node}
          onChange={(data) => updateNodeData(node.id, data)}
        />
      </div>
    </aside>
  );
}

type SimpleNode = { type?: string; data: Record<string, unknown> };

function NodeForm({
  node,
  onChange,
}: {
  node: SimpleNode;
  onChange: (d: Record<string, unknown>) => void;
}) {
  const field = (key: string, label: string, placeholder = '') => (
    <label key={key} className="flex flex-col gap-1">
      <span className="text-xs font-medium text-zinc-500">{label}</span>
      <input
        className="rounded border border-zinc-200 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1.5 text-sm text-zinc-800 dark:text-zinc-100 focus:outline-none focus:border-blue-400"
        value={(node.data[key] as string) ?? ''}
        placeholder={placeholder}
        onChange={(e) => onChange({ [key]: e.target.value })}
      />
    </label>
  );

  if (node.type === 'project') {
    return <div className="flex flex-col gap-3">{field('project_id', 'Project ID', 'proj-...')}</div>;
  }
  if (node.type === 'scenario_config') {
    return (
      <div className="flex flex-col gap-3">
        {field('scenario_name', 'Scenario Name')}
        {field('map_name', 'Map Name')}
        {field('weather', 'Weather Preset', 'ClearNoon')}
      </div>
    );
  }
  if (node.type === 'sensor_profile') {
    return (
      <div className="flex flex-col gap-3">
        {field('sensor_profile_id', 'Profile ID (reference)')}
        <p className="text-xs text-zinc-400">
          Inline sensor editor available in a future update.
        </p>
      </div>
    );
  }
  if (node.type === 'run') {
    return (
      <p className="text-sm text-zinc-400">
        Run node executes automatically when the pipeline runs.
      </p>
    );
  }
  if (node.type === 'report') {
    return (
      <p className="text-sm text-zinc-400">
        Report node displays results after the run completes.
      </p>
    );
  }
  return null;
}
