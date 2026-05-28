import { Handle, Position, type NodeProps } from '@xyflow/react';

type PortDef = { id: string; type: 'source' | 'target'; position: Position };

interface NodeSpec {
  label: string;
  category: string;
  color: string;
  ports: PortDef[];
  renderBody?: (data: Record<string, unknown>) => React.ReactNode;
}

const NODE_SPECS: Record<string, NodeSpec> = {
  scene_replay: {
    label: '场景回放',
    category: 'scene_source',
    color: 'border-emerald-500',
    ports: [{ id: 'scene', type: 'source', position: Position.Right }],
    renderBody: (data) => (
      <div className="text-xs text-zinc-400">{(data.scenario_name as string) || '未选择场景'}</div>
    ),
  },
  env_override: {
    label: '环境覆盖',
    category: 'env_override',
    color: 'border-amber-500',
    ports: [
      { id: 'scene', type: 'target', position: Position.Left },
      { id: 'scene_out', type: 'source', position: Position.Right },
    ],
  },
  camera: {
    label: '摄像头',
    category: 'sensor',
    color: 'border-blue-500',
    ports: [
      { id: 'scene', type: 'target', position: Position.Left },
      { id: 'sensor_data', type: 'source', position: Position.Right },
    ],
    renderBody: (data) => {
      const res = data.width && data.height ? `${data.width}×${data.height}` : '';
      return res ? <div className="text-xs text-zinc-400">{res}</div> : null;
    },
  },
  lidar: {
    label: 'LiDAR',
    category: 'sensor',
    color: 'border-blue-500',
    ports: [
      { id: 'scene', type: 'target', position: Position.Left },
      { id: 'sensor_data', type: 'source', position: Position.Right },
    ],
  },
  radar: {
    label: '毫米波雷达',
    category: 'sensor',
    color: 'border-blue-500',
    ports: [
      { id: 'scene', type: 'target', position: Position.Left },
      { id: 'sensor_data', type: 'source', position: Position.Right },
    ],
  },
  gnss: {
    label: 'GNSS',
    category: 'sensor',
    color: 'border-blue-500',
    ports: [
      { id: 'scene', type: 'target', position: Position.Left },
      { id: 'sensor_data', type: 'source', position: Position.Right },
    ],
  },
  imu: {
    label: 'IMU',
    category: 'sensor',
    color: 'border-blue-500',
    ports: [
      { id: 'scene', type: 'target', position: Position.Left },
      { id: 'sensor_data', type: 'source', position: Position.Right },
    ],
  },
  rtp_output: {
    label: 'RTP 输出',
    category: 'output',
    color: 'border-purple-500',
    ports: [
      { id: 'sensor_data', type: 'target', position: Position.Left },
      { id: 'stream', type: 'source', position: Position.Right },
    ],
    renderBody: (data) => (
      <div className="text-xs text-zinc-400">{(data.address as string) || '未配置'}</div>
    ),
  },
  pointcloud_output: {
    label: '点云输出',
    category: 'output',
    color: 'border-purple-500',
    ports: [
      { id: 'sensor_data', type: 'target', position: Position.Left },
      { id: 'stream', type: 'source', position: Position.Right },
    ],
  },
  raw_output: {
    label: '原始输出',
    category: 'output',
    color: 'border-purple-500',
    ports: [
      { id: 'sensor_data', type: 'target', position: Position.Left },
      { id: 'stream', type: 'source', position: Position.Right },
    ],
  },
  dut: {
    label: 'DUT 设备',
    category: 'terminal',
    color: 'border-red-500',
    ports: [{ id: 'stream', type: 'target', position: Position.Left }],
    renderBody: (data) => (
      <div className="text-xs text-zinc-400">{(data.device_name as string) || '未配置'}</div>
    ),
  },
};

function createNodeComponent(nodeType: string) {
  const spec = NODE_SPECS[nodeType];
  if (!spec) throw new Error(`Unknown node type: ${nodeType}`);

  return function NodeComponent({ data, selected }: NodeProps) {
    return (
      <div className={`rounded-lg border-2 bg-white dark:bg-zinc-900 px-4 py-3 min-w-[160px] shadow-sm ${selected ? spec.color : 'border-zinc-200 dark:border-zinc-700'}`}>
        <div className="text-xs font-semibold uppercase tracking-wide text-zinc-400 mb-1">
          {spec.label}
        </div>
        {spec.renderBody?.(data as Record<string, unknown>)}
        {spec.ports.map((port, i) => (
          <Handle key={`${port.type}-${port.id}-${i}`} type={port.type} position={port.position} id={port.id} />
        ))}
      </div>
    );
  };
}

type NodeComponent = (props: NodeProps) => React.JSX.Element;

const NODE_TYPE_MAP: Record<string, NodeComponent> = {};
for (const nodeType of Object.keys(NODE_SPECS)) {
  NODE_TYPE_MAP[nodeType] = createNodeComponent(nodeType);
}

export { NODE_SPECS, NODE_TYPE_MAP, createNodeComponent };
