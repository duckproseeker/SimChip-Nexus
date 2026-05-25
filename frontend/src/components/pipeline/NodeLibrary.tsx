const NODE_TYPES = [
  { type: 'project', label: 'Project', description: 'Select a project' },
  { type: 'scenario_config', label: 'Scenario', description: 'Map, weather, traffic' },
  { type: 'sensor_profile', label: 'Sensor Profile', description: 'Camera, lidar, radar' },
  { type: 'run', label: 'Run', description: 'Execute in Carla' },
  { type: 'report', label: 'Report', description: 'View results' },
  { type: 'recording', label: 'Recording', description: 'Corner case capture', disabled: true },
] as const;

export function NodeLibrary() {
  const onDragStart = (e: React.DragEvent, nodeType: string) => {
    e.dataTransfer.setData('application/reactflow', nodeType);
    e.dataTransfer.effectAllowed = 'move';
  };

  return (
    <aside className="w-60 border-r border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 flex flex-col gap-1 p-3 overflow-y-auto shrink-0">
      <div className="text-xs font-semibold uppercase tracking-wide text-zinc-400 px-1 mb-2">
        Nodes
      </div>
      {NODE_TYPES.map(({ type, label, description, ...rest }) => {
        const disabled = 'disabled' in rest ? (rest as { disabled: boolean }).disabled : false;
        return (
          <div
            key={type}
            draggable={!disabled}
            onDragStart={disabled ? undefined : (e) => onDragStart(e, type)}
            className={`rounded-md border px-3 py-2 select-none transition-colors ${
              disabled
                ? 'border-zinc-100 dark:border-zinc-800 opacity-40 cursor-not-allowed'
                : 'border-zinc-200 dark:border-zinc-700 cursor-grab hover:border-blue-400 hover:bg-white dark:hover:bg-zinc-800 active:cursor-grabbing'
            }`}
          >
            <div className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
              {label}
              {disabled && (
                <span className="ml-2 text-xs text-zinc-400">soon</span>
              )}
            </div>
            <div className="text-xs text-zinc-400">{description}</div>
          </div>
        );
      })}
    </aside>
  );
}
