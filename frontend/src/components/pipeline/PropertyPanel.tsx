import { usePipelineStore } from '../../features/pipeline/store';
import { ProjectForm } from './forms/ProjectForm';
import { ScenarioForm } from './forms/ScenarioForm';
import { MapForm } from './forms/MapForm';
import { WeatherForm } from './forms/WeatherForm';
import { RecordingForm } from './forms/RecordingForm';
import { SensorCameraForm } from './forms/SensorCameraForm';
import { SensorLidarForm } from './forms/SensorLidarForm';
import { SensorRadarForm } from './forms/SensorRadarForm';
import { SensorGnssForm } from './forms/SensorGnssForm';
import { SensorImuForm } from './forms/SensorImuForm';

const LEGACY_TYPES = new Set(['scenario_config', 'sensor_profile', 'run']);

const NODE_LABELS: Record<string, string> = {
  project: '项目', scenario: '场景', map: '地图', weather: '天气',
  recording: '场景录制', sensor_camera: '摄像头', sensor_lidar: '激光雷达',
  sensor_radar: '毫米波雷达', sensor_gnss: 'GNSS', sensor_imu: 'IMU',
  live_run: '实时仿真', replay_run: '录制回放', report: '报告',
};

export function PropertyPanel() {
  const { nodes, selectedNodeId, updateNodeData } = usePipelineStore();
  const node = nodes.find((n) => n.id === selectedNodeId);

  if (!node) {
    return (
      <aside className="w-80 border-l border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 flex items-center justify-center shrink-0">
        <p className="text-sm text-zinc-400 px-4 text-center">选择节点以配置</p>
      </aside>
    );
  }

  const label = NODE_LABELS[node.type ?? ''] ?? node.type?.replace(/_/g, ' ') ?? '节点';
  const onChange = (d: Record<string, unknown>) => updateNodeData(node.id, d);

  return (
    <aside className="w-80 border-l border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 overflow-y-auto shrink-0">
      <div className="p-4">
        <div className="text-xs font-semibold uppercase tracking-wide text-zinc-400 mb-1">节点属性</div>
        <div className="text-base font-semibold text-zinc-800 dark:text-zinc-100 mb-4">{label}</div>
        {LEGACY_TYPES.has(node.type ?? '') ? (
          <div className="rounded-md border border-yellow-300 bg-yellow-50 dark:bg-yellow-900/20 px-3 py-2 text-sm text-yellow-700 dark:text-yellow-400">
            ⚠️ 此节点为旧版类型，请删除后重新添加。
          </div>
        ) : (
          <NodeForm node={node} onChange={onChange} />
        )}
      </div>
    </aside>
  );
}

type SimpleNode = { type?: string; data: Record<string, unknown> };

function NodeForm({ node, onChange }: { node: SimpleNode; onChange: (d: Record<string, unknown>) => void }) {
  const { type, data } = node;
  if (type === 'project') return <ProjectForm data={data} onChange={onChange} />;
  if (type === 'scenario') return <ScenarioForm data={data} onChange={onChange} />;
  if (type === 'map') return <MapForm data={data} onChange={onChange} />;
  if (type === 'weather') return <WeatherForm data={data} onChange={onChange} />;
  if (type === 'recording') return <RecordingForm data={data} onChange={onChange} />;
  if (type === 'sensor_camera') return <SensorCameraForm data={data} onChange={onChange} />;
  if (type === 'sensor_lidar') return <SensorLidarForm data={data} onChange={onChange} />;
  if (type === 'sensor_radar') return <SensorRadarForm data={data} onChange={onChange} />;
  if (type === 'sensor_gnss') return <SensorGnssForm data={data} onChange={onChange} />;
  if (type === 'sensor_imu') return <SensorImuForm data={data} onChange={onChange} />;
  if (type === 'live_run' || type === 'replay_run') {
    return <p className="text-sm text-zinc-400">连接所需节点后点击运行。</p>;
  }
  if (type === 'report') {
    return <p className="text-sm text-zinc-400">运行完成后自动生成报告。</p>;
  }
  return null;
}
