import { NODE_SPECS } from './nodes';

const CATEGORIES = [
  { key: 'scene_source', label: '场景源', types: ['scene_replay'] },
  { key: 'env_override', label: '环境配置', types: ['env_override'] },
  { key: 'sensor', label: '传感器', types: ['camera', 'lidar', 'radar', 'gnss', 'imu'] },
  { key: 'output', label: '输出', types: ['rtp_output', 'pointcloud_output', 'raw_output'] },
  { key: 'terminal', label: '终端', types: ['dut'] },
];

export function NodeLibrary() {
  function onDragStart(e: React.DragEvent, nodeType: string) {
    e.dataTransfer.setData('application/reactflow', nodeType);
    e.dataTransfer.effectAllowed = 'move';
  }

  return (
    <aside className="w-60 border-r border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 overflow-y-auto p-3">
      <h2 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 mb-3">节点库</h2>
      {CATEGORIES.map((cat) => (
        <div key={cat.key} className="mb-4">
          <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">{cat.label}</h3>
          <div className="space-y-1">
            {cat.types.map((t) => {
              const spec = NODE_SPECS[t];
              if (!spec) return null;
              return (
                <div
                  key={t}
                  draggable
                  onDragStart={(e) => onDragStart(e, t)}
                  className="px-3 py-2 rounded-md bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 cursor-grab text-sm text-zinc-700 dark:text-zinc-200 hover:border-blue-400 transition-colors"
                >
                  {spec.label}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </aside>
  );
}
