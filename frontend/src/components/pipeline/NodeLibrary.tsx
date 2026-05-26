const NODE_GROUPS = [
  {
    label: '流程骨架',
    nodes: [
      { type: 'project', label: '项目', description: '选择项目' },
      { type: 'live_run', label: '实时仿真', description: '连接场景/地图/天气/传感器' },
      { type: 'replay_run', label: '录制回放', description: '连接录制/传感器' },
      { type: 'report', label: '报告', description: '查看运行结果' },
    ],
  },
  {
    label: '环境配置',
    nodes: [
      { type: 'scenario', label: '场景', description: '选择仿真场景' },
      { type: 'map', label: '地图', description: '选择地图' },
      { type: 'weather', label: '天气', description: '天气预设或自定义' },
    ],
  },
  {
    label: '场景录制',
    nodes: [
      { type: 'recording', label: '场景录制', description: '选择已录制的场景' },
    ],
  },
  {
    label: '传感器',
    nodes: [
      { type: 'sensor_camera', label: '摄像头', description: 'RGB 相机' },
      { type: 'sensor_lidar', label: '激光雷达', description: 'LiDAR 点云' },
      { type: 'sensor_radar', label: '毫米波雷达', description: 'Radar' },
      { type: 'sensor_gnss', label: 'GNSS', description: '全球定位' },
      { type: 'sensor_imu', label: 'IMU', description: '惯性测量' },
    ],
  },
] as const;

export function NodeLibrary() {
  const onDragStart = (e: React.DragEvent, nodeType: string) => {
    e.dataTransfer.setData('application/reactflow', nodeType);
    e.dataTransfer.effectAllowed = 'move';
  };

  return (
    <aside className="w-60 border-r border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 flex flex-col gap-3 p-3 overflow-y-auto shrink-0">
      {NODE_GROUPS.map((group) => (
        <div key={group.label}>
          <div className="text-xs font-semibold uppercase tracking-wide text-zinc-400 px-1 mb-1">
            {group.label}
          </div>
          <div className="flex flex-col gap-1">
            {group.nodes.map(({ type, label, description }) => (
              <div
                key={type}
                draggable
                onDragStart={(e) => onDragStart(e, type)}
                className="rounded-md border border-zinc-200 dark:border-zinc-700 px-3 py-2 select-none cursor-grab hover:border-blue-400 hover:bg-white dark:hover:bg-zinc-800 active:cursor-grabbing transition-colors"
              >
                <div className="text-sm font-medium text-zinc-800 dark:text-zinc-100">{label}</div>
                <div className="text-xs text-zinc-400">{description}</div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </aside>
  );
}
