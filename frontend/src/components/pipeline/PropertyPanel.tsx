import { usePipelineStore } from '../../features/pipeline/store';
import { NODE_SPECS } from './nodes';
import { SceneReplayForm } from './forms/SceneReplayForm';
import { EnvOverrideForm } from './forms/EnvOverrideForm';
import { SensorCameraForm } from './forms/SensorCameraForm';
import { SensorLidarForm } from './forms/SensorLidarForm';
import { SensorRadarForm } from './forms/SensorRadarForm';
import { SensorGnssForm } from './forms/SensorGnssForm';
import { SensorImuForm } from './forms/SensorImuForm';
import { OutputForm } from './forms/OutputForm';
import { DUTForm } from './forms/DUTForm';

type FormProps = { data: Record<string, unknown>; onChange: (d: Record<string, unknown>) => void };

const SENSOR_FORMS: Record<string, React.FC<FormProps>> = {
  camera: SensorCameraForm,
  lidar: SensorLidarForm,
  radar: SensorRadarForm,
  gnss: SensorGnssForm,
  imu: SensorImuForm,
};

export function PropertyPanel() {
  const { nodes, selectedNodeId, updateNodeData } = usePipelineStore();
  const node = nodes.find((n) => n.id === selectedNodeId);

  if (!node) {
    return (
      <aside className="w-80 border-l border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 p-4">
        <p className="text-sm text-zinc-400">选择一个节点查看属性</p>
      </aside>
    );
  }

  const spec = NODE_SPECS[node.type!];
  const data = (node.data ?? {}) as Record<string, unknown>;
  const onChange = (newData: Record<string, unknown>) => updateNodeData(node.id, newData);

  function renderForm() {
    const type = node!.type!;
    if (type === 'scene_replay') return <SceneReplayForm data={data} onChange={onChange} />;
    if (type === 'env_override') return <EnvOverrideForm data={data} onChange={onChange} />;
    if (type in SENSOR_FORMS) {
      const Form = SENSOR_FORMS[type];
      return <Form data={data} onChange={onChange} />;
    }
    if (['rtp_output', 'pointcloud_output', 'raw_output'].includes(type)) {
      return <OutputForm nodeType={type} data={data} onChange={onChange} />;
    }
    if (type === 'dut') return <DUTForm data={data} onChange={onChange} />;
    return <p className="text-xs text-zinc-400">无需配置</p>;
  }

  return (
    <aside className="w-80 border-l border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 p-4 overflow-y-auto">
      <h3 className="text-sm font-semibold text-zinc-700 dark:text-zinc-200 mb-3">
        {spec?.label ?? node.type}
      </h3>
      {renderForm()}
    </aside>
  );
}
