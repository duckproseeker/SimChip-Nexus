import { useEffect, useState } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { getDevicesWorkspace } from '../../api/devices';
import { listScenarioCatalog, listSensorProfiles, saveSensorProfile } from '../../api/scenarios';
import { getPiGatewayStatus, startPiGateway, stopPiGateway } from '../../api/system';
import type {
  PiGatewayCommandResult,
  ScenarioCatalogItem,
  SensorProfile,
  SensorProfileSavePayload,
  SensorSpec
} from '../../api/types';
import { EmptyState } from '../../components/common/EmptyState';
import { JsonBlock } from '../../components/common/JsonBlock';
import { MetricCard } from '../../components/common/MetricCard';
import { PageHeader } from '../../components/common/PageHeader';
import { Panel } from '../../components/common/Panel';
import { StatusPill } from '../../components/common/StatusPill';
import { formatDateTime } from '../../lib/format';

interface EditableSensorSpec extends SensorSpec {
  attributes_text: string;
}

interface SensorProfileEditorState {
  profile_name: string;
  display_name: string;
  description: string;
  vehicle_model: string;
  metadata_text: string;
  sensors: EditableSensorSpec[];
  is_new: boolean;
}

const SENSOR_NUMBER_FIELDS: Array<{
  key: keyof SensorSpec;
  label: string;
  step?: number;
  min?: number;
}> = [
  { key: 'x', label: 'X', step: 0.01 },
  { key: 'y', label: 'Y', step: 0.01 },
  { key: 'z', label: 'Z', step: 0.01 },
  { key: 'roll', label: 'Roll', step: 0.1 },
  { key: 'pitch', label: 'Pitch', step: 0.1 },
  { key: 'yaw', label: 'Yaw', step: 0.1 },
  { key: 'width', label: 'Width', min: 1, step: 1 },
  { key: 'height', label: 'Height', min: 1, step: 1 },
  { key: 'fov', label: 'FOV', min: 0.1, step: 0.1 },
  { key: 'horizontal_fov', label: 'Horizontal FOV', min: 0.1, step: 0.1 },
  { key: 'vertical_fov', label: 'Vertical FOV', min: 0.1, step: 0.1 },
  { key: 'range', label: 'Range', min: 0.1, step: 0.1 },
  { key: 'channels', label: 'Channels', min: 1, step: 1 },
  { key: 'points_per_second', label: 'Points / s', min: 1, step: 1 },
  { key: 'rotation_frequency', label: 'Rotation Hz', min: 0.1, step: 0.1 },
  { key: 'reading_frequency', label: 'Reading Hz', min: 0.1, step: 0.1 }
];

function buildEmptySensor(type = 'sensor.camera.rgb'): EditableSensorSpec {
  return {
    id: '',
    type,
    x: 0,
    y: 0,
    z: 0,
    roll: 0,
    pitch: 0,
    yaw: 0,
    width: type.startsWith('sensor.camera.') ? 1920 : undefined,
    height: type.startsWith('sensor.camera.') ? 1080 : undefined,
    fov: type.startsWith('sensor.camera.') ? 90 : undefined,
    range: type === 'sensor.lidar.ray_cast' ? 85 : undefined,
    channels: type === 'sensor.lidar.ray_cast' ? 64 : undefined,
    points_per_second: type === 'sensor.lidar.ray_cast' ? 600000 : undefined,
    rotation_frequency: type === 'sensor.lidar.ray_cast' ? 10 : undefined,
    attributes_text: '{}'
  };
}

function sanitizeMetadata(metadata: Record<string, unknown>) {
  const next = { ...metadata };
  delete next.vehicle_model;
  return next;
}

function profileToEditor(profile: SensorProfile): SensorProfileEditorState {
  return {
    profile_name: profile.profile_name,
    display_name: profile.display_name,
    description: profile.description,
    vehicle_model: profile.vehicle_model ?? '',
    metadata_text: JSON.stringify(sanitizeMetadata(profile.metadata), null, 2),
    sensors: profile.sensors.map((sensor) => ({
      ...sensor,
      attributes_text: JSON.stringify(sensor.attributes ?? {}, null, 2)
    })),
    is_new: false
  };
}

function createEmptyEditor(): SensorProfileEditorState {
  return {
    profile_name: '',
    display_name: '',
    description: '',
    vehicle_model: '',
    metadata_text: '{}',
    sensors: [buildEmptySensor()],
    is_new: true
  };
}

function parseJsonObject(raw: string, label: string) {
  const normalized = raw.trim();
  if (!normalized) {
    return {};
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(normalized);
  } catch (error) {
    throw new Error(`${label} 必须是合法 JSON`);
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${label} 必须是 JSON 对象`);
  }
  return parsed as Record<string, unknown>;
}

function buildSavePayload(editor: SensorProfileEditorState): SensorProfileSavePayload {
  const metadata = parseJsonObject(editor.metadata_text, '元数据');
  if (editor.vehicle_model.trim()) {
    metadata.vehicle_model = editor.vehicle_model.trim();
  }

  return {
    profile_name: editor.profile_name.trim(),
    display_name: editor.display_name.trim(),
    description: editor.description.trim(),
    vehicle_model: editor.vehicle_model.trim() || null,
    metadata,
    sensors: editor.sensors.map((sensor, index) => ({
      id: sensor.id.trim() || `Sensor${index + 1}`,
      type: sensor.type.trim(),
      x: sensor.x,
      y: sensor.y,
      z: sensor.z,
      roll: sensor.roll,
      pitch: sensor.pitch,
      yaw: sensor.yaw,
      width: sensor.width,
      height: sensor.height,
      fov: sensor.fov,
      horizontal_fov: sensor.horizontal_fov,
      vertical_fov: sensor.vertical_fov,
      range: sensor.range,
      channels: sensor.channels,
      points_per_second: sensor.points_per_second,
      rotation_frequency: sensor.rotation_frequency,
      reading_frequency: sensor.reading_frequency,
      attributes: parseJsonObject(sensor.attributes_text, `传感器 ${sensor.id || index + 1} 的高级属性`)
    }))
  };
}

function countSensors(profiles: SensorProfile[]) {
  return profiles.reduce((total, profile) => total + profile.sensors.length, 0);
}

function parseOptionalNumber(rawValue: string) {
  if (!rawValue.trim()) {
    return undefined;
  }
  const parsed = Number(rawValue);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export function StudioPage() {
  const queryClient = useQueryClient();
  const sensorProfilesQuery = useQuery({
    queryKey: ['sensor-profiles'],
    queryFn: listSensorProfiles
  });
  const devicesWorkspaceQuery = useQuery({
    queryKey: ['devices', 'workspace'],
    queryFn: getDevicesWorkspace,
    refetchInterval: 5000
  });
  const piGatewayQuery = useQuery({
    queryKey: ['system', 'pi-gateway'],
    queryFn: getPiGatewayStatus,
    refetchInterval: 5000
  });
  const catalogQuery = useQuery({
    queryKey: ['scenario-catalog'],
    queryFn: listScenarioCatalog
  });

  const sensorProfiles = sensorProfilesQuery.data ?? [];
  const gateways = devicesWorkspaceQuery.data?.gateways ?? [];
  const catalogItems = catalogQuery.data ?? [];
  const editableScenarioCount = catalogItems.filter(
    (item) => item.launch_capabilities.sensor_profile_editable
  ).length;
  const vehicleBoundCount = sensorProfiles.filter((item) => item.vehicle_model).length;

  const [selectedProfileName, setSelectedProfileName] = useState('');
  const [editor, setEditor] = useState<SensorProfileEditorState>(createEmptyEditor);

  useEffect(() => {
    if (!selectedProfileName && sensorProfiles[0]) {
      setSelectedProfileName(sensorProfiles[0].profile_name);
      setEditor(profileToEditor(sensorProfiles[0]));
    }
  }, [selectedProfileName, sensorProfiles]);

  const selectedProfile =
    sensorProfiles.find((item) => item.profile_name === selectedProfileName) ?? null;

  const previewPayload = (() => {
    try {
      return buildSavePayload(editor);
    } catch (error) {
      return { preview_error: error instanceof Error ? error.message : '预览生成失败' };
    }
  })();

  const saveMutation = useMutation({
    mutationFn: async () => saveSensorProfile(buildSavePayload(editor)),
    onSuccess: async (savedProfile) => {
      setSelectedProfileName(savedProfile.profile_name);
      setEditor(profileToEditor(savedProfile));
      await queryClient.invalidateQueries({ queryKey: ['sensor-profiles'] });
    }
  });
  const piGatewayStartMutation = useMutation({
    mutationFn: startPiGateway,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['system', 'pi-gateway'] });
      await queryClient.invalidateQueries({ queryKey: ['devices', 'workspace'] });
    }
  });
  const piGatewayStopMutation = useMutation({
    mutationFn: stopPiGateway,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['system', 'pi-gateway'] });
      await queryClient.invalidateQueries({ queryKey: ['devices', 'workspace'] });
    }
  });

  function selectProfile(profile: SensorProfile) {
    setSelectedProfileName(profile.profile_name);
    setEditor(profileToEditor(profile));
  }

  function updateEditor<K extends keyof SensorProfileEditorState>(
    key: K,
    value: SensorProfileEditorState[K]
  ) {
    setEditor((current) => ({ ...current, [key]: value }));
  }

  function updateSensor(
    index: number,
    updater: (current: EditableSensorSpec) => EditableSensorSpec
  ) {
    setEditor((current) => ({
      ...current,
      sensors: current.sensors.map((sensor, sensorIndex) =>
        sensorIndex === index ? updater(sensor) : sensor
      )
    }));
  }

  function addSensor(type = 'sensor.camera.rgb') {
    setEditor((current) => ({
      ...current,
      sensors: [...current.sensors, buildEmptySensor(type)]
    }));
  }

  function removeSensor(index: number) {
    setEditor((current) => ({
      ...current,
      sensors:
        current.sensors.length > 1
          ? current.sensors.filter((_, sensorIndex) => sensorIndex !== index)
          : current.sensors
    }));
  }

  const selectedProfileScenarioDefaults = catalogItems.filter((item) => {
    return (
      item.descriptor_template.sensors.profile_name === selectedProfileName ||
      (selectedProfileName && item.launch_capabilities.sensor_profile_editable)
    );
  });
  const latestPiGatewayMutation =
    piGatewayStartMutation.data ?? piGatewayStopMutation.data ?? null;
  const piGatewayBusy = piGatewayStartMutation.isPending || piGatewayStopMutation.isPending;

  return (
    <div className="page-stack studio-page">
      <PageHeader
        title="运维工作台"
        description="管理传感器模板和网关状态。"
        actions={
          <div className="flex flex-wrap gap-3">
            <Link className="horizon-button-secondary" to="/scenario-sets">
              去场景集使用模板
            </Link>
            <button
              className="horizon-button"
              onClick={() => {
                setSelectedProfileName('');
                setEditor(createEmptyEditor());
              }}
              type="button"
            >
              新建模板
            </button>
          </div>
        }
        chips={['运维配置', '传感器模板', '车型绑定']}
        eyebrow="运维 / 模板工作区"
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard accent="blue" label="传感器模板" value={sensorProfiles.length} hint="YAML 模板总数" />
        <MetricCard accent="teal" label="车型绑定" value={vehicleBoundCount} hint="已声明 vehicle_model 的模板数" />
        <MetricCard accent="violet" label="传感器总数" value={countSensors(sensorProfiles)} hint="所有模板里的传感器数量" />
        <MetricCard accent="orange" label="可用场景" value={editableScenarioCount} hint="支持直接选择传感器模板的场景数" />
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <Panel
          title="Pi 网关链路"
          subtitle="查看状态并手动启动或停止。"
          actions={
            <div className="flex flex-wrap gap-3">
              <button
                className="horizon-button-secondary"
                disabled={piGatewayBusy || !piGatewayQuery.data?.stop_command_configured}
                onClick={() => piGatewayStopMutation.mutate()}
                type="button"
              >
                {piGatewayStopMutation.isPending ? '停止中...' : '停止树莓派链路'}
              </button>
              <button
                className="horizon-button"
                disabled={piGatewayBusy || !piGatewayQuery.data?.start_command_configured}
                onClick={() => piGatewayStartMutation.mutate()}
                type="button"
              >
                {piGatewayStartMutation.isPending ? '启动中...' : '启动树莓派链路'}
              </button>
            </div>
          }
        >
          {piGatewayQuery.isLoading ? (
            <EmptyState title="正在探测 Pi 网关" description="正在读取状态。" />
          ) : piGatewayQuery.isError ? (
            <EmptyState
              title="Pi 网关状态读取失败"
              description={piGatewayQuery.error.message}
            />
          ) : piGatewayQuery.data ? (
            <div className="studio-runtime-shell">
              <div className="flex flex-wrap items-center gap-3">
                <StatusPill status={piGatewayQuery.data.status} />
                <span className="studio-runtime-chip">
                  {piGatewayQuery.data.host ?? '未配置主机'}:{piGatewayQuery.data.port ?? '-'}
                </span>
                <span className="studio-runtime-chip">
                  用户 {piGatewayQuery.data.user ?? '未配置'}
                </span>
              </div>

              <div className="studio-runtime-meta">
                <div className="studio-runtime-stat">
                  <span>最近探测</span>
                  <strong>{formatDateTime(piGatewayQuery.data.last_probe_at_utc)}</strong>
                </div>
                <div className="studio-runtime-stat">
                  <span>启动命令</span>
                  <strong>{piGatewayQuery.data.start_command_configured ? '已配置' : '未配置'}</strong>
                </div>
                <div className="studio-runtime-stat">
                  <span>停止命令</span>
                  <strong>{piGatewayQuery.data.stop_command_configured ? '已配置' : '未配置'}</strong>
                </div>
              </div>

              <p className="studio-runtime-note">
                {piGatewayQuery.data.reachable
                  ? '树莓派当前可达。'
                  : '树莓派当前不可达，运行时会跳过 Pi 注入。'}
              </p>

              {piGatewayQuery.data.warning ? (
                <p className="studio-inline-feedback studio-inline-feedback--error">
                  {piGatewayQuery.data.warning}
                </p>
              ) : null}

              {renderPiGatewayCommandFeedback(latestPiGatewayMutation)}
            </div>
          ) : null}
        </Panel>

        <Panel
          title="已注册网关"
          subtitle="查看最近心跳和当前运行。"
        >
          {devicesWorkspaceQuery.isLoading ? (
            <EmptyState title="网关列表加载中" description="正在同步平台已注册设备。" />
          ) : devicesWorkspaceQuery.isError ? (
            <EmptyState
              title="网关列表加载失败"
              description={devicesWorkspaceQuery.error.message}
            />
          ) : gateways.length === 0 ? (
            <EmptyState
              title="当前没有已注册网关"
              description="Agent 上报心跳后会显示在这里。"
            />
          ) : (
            <div className="studio-gateway-list">
              {gateways.map((gateway) => (
                <article key={gateway.gateway_id} className="studio-gateway-card">
                  <div className="flex flex-wrap items-center gap-3">
                    <StatusPill status={gateway.status} />
                    <strong className="studio-gateway-card__title">{gateway.name}</strong>
                  </div>
                  <div className="studio-gateway-card__meta">
                    <span>网关 ID: {gateway.gateway_id}</span>
                    <span>最近心跳: {formatDateTime(gateway.last_heartbeat_at_utc)}</span>
                    <span>当前运行: {gateway.current_run_id ?? '空闲'}</span>
                  </div>
                  {gateway.status_detail ? (
                    <p className="mt-3 text-sm text-secondaryGray-500 dark:text-slate-400">
                      {gateway.status_detail}
                    </p>
                  ) : null}
                </article>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[340px_minmax(0,1fr)]">
        <Panel
          title="模板列表"
          subtitle="选择模板后在右侧编辑。"
          actions={
            sensorProfilesQuery.isLoading ? <span className="studio-panel-status">加载中...</span> : null
          }
        >
          {sensorProfilesQuery.isError ? (
            <EmptyState
              title="传感器模板加载失败"
              description={sensorProfilesQuery.error.message}
            />
          ) : sensorProfiles.length === 0 ? (
            <EmptyState title="还没有模板" description="先创建一个和车型绑定的传感器模板。" />
          ) : (
            <div className="studio-template-list">
              {sensorProfiles.map((profile) => (
                <button
                  aria-pressed={selectedProfileName === profile.profile_name}
                  key={profile.profile_name}
                  className={[
                    'studio-template-card',
                    selectedProfileName === profile.profile_name ? 'studio-template-card--active' : ''
                  ].join(' ')}
                  onClick={() => selectProfile(profile)}
                  type="button"
                >
                  <strong className="studio-template-card__title">{profile.display_name}</strong>
                  <p className="studio-template-card__subtitle">{profile.vehicle_model ?? '未绑定车型'}</p>
                  <div className="studio-template-card__meta">
                    <span className="studio-template-card__badge">{profile.profile_name}</span>
                    <span className="studio-template-card__badge">
                      {profile.sensors.length} sensors
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </Panel>

        <div className="flex flex-col gap-5">
          <Panel
            title="模板编辑"
            subtitle="修改后保存即可。"
            actions={
              <button
                className="horizon-button"
                disabled={saveMutation.isPending}
                onClick={() => saveMutation.mutate()}
                type="button"
              >
                {saveMutation.isPending ? '保存中...' : editor.is_new ? '创建模板' : '保存模板'}
              </button>
            }
          >
            <div className="form-grid">
              <label className="field">
                <span>模板标识</span>
                <input
                  onChange={(event) => updateEditor('profile_name', event.target.value)}
                  placeholder="vehicle_sedan_alpha"
                  value={editor.profile_name}
                />
              </label>

              <label className="field">
                <span>显示名称</span>
                <input
                  onChange={(event) => updateEditor('display_name', event.target.value)}
                  placeholder="Sedan Alpha"
                  value={editor.display_name}
                />
              </label>

              <label className="field">
                <span>车型蓝图</span>
                <input
                  onChange={(event) => updateEditor('vehicle_model', event.target.value)}
                  placeholder="vehicle.lincoln.mkz_2017"
                  value={editor.vehicle_model}
                />
              </label>

              <label className="field">
                <span>描述</span>
                <input
                  onChange={(event) => updateEditor('description', event.target.value)}
                  placeholder="该车型的默认前向采集模板"
                  value={editor.description}
                />
              </label>
            </div>

            <label className="field mt-4">
              <span>扩展元数据 JSON</span>
              <textarea
                className="min-h-[120px]"
                onChange={(event) => updateEditor('metadata_text', event.target.value)}
                value={editor.metadata_text}
              />
            </label>

            <div className="studio-sensor-toolbar">
              <button className="horizon-button-secondary" onClick={() => addSensor('sensor.camera.rgb')} type="button">
                添加 RGB 相机
              </button>
              <button className="horizon-button-secondary" onClick={() => addSensor('sensor.lidar.ray_cast')} type="button">
                添加 LiDAR
              </button>
              <button className="horizon-button-secondary" onClick={() => addSensor('sensor.other.radar')} type="button">
                添加 Radar
              </button>
            </div>

            <div className="studio-sensor-stack">
              {editor.sensors.map((sensor, index) => (
                <section
                  key={`${sensor.id || 'sensor'}-${index}`}
                  className="studio-sensor-card"
                >
                  <div className="studio-sensor-card__header">
                    <div>
                      <strong className="studio-sensor-card__title">传感器 {index + 1}</strong>
                      <p className="studio-sensor-card__subtitle">
                        按车型维护传感器参数。
                      </p>
                    </div>
                    <button
                      className="studio-button-danger"
                      disabled={editor.sensors.length <= 1}
                      onClick={() => removeSensor(index)}
                      type="button"
                    >
                      删除
                    </button>
                  </div>

                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <label className="field">
                      <span>ID</span>
                      <input
                        onChange={(event) =>
                          updateSensor(index, (current) => ({ ...current, id: event.target.value }))
                        }
                        value={sensor.id}
                      />
                    </label>

                    <label className="field">
                      <span>类型</span>
                      <input
                        onChange={(event) =>
                          updateSensor(index, (current) => ({ ...current, type: event.target.value }))
                        }
                        value={sensor.type}
                      />
                    </label>
                  </div>

                  <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                    {SENSOR_NUMBER_FIELDS.map((field) => (
                      <label key={field.key} className="field">
                        <span>{field.label}</span>
                        <input
                          min={field.min}
                          onChange={(event) =>
                            updateSensor(index, (current) => ({
                              ...current,
                              [field.key]: parseOptionalNumber(event.target.value)
                            }))
                          }
                          step={field.step}
                          type="number"
                          value={
                            typeof sensor[field.key] === 'number' ? `${sensor[field.key]}` : ''
                          }
                        />
                      </label>
                    ))}
                  </div>

                  <label className="field mt-4">
                    <span>高级属性 JSON</span>
                    <textarea
                      className="min-h-[110px]"
                      onChange={(event) =>
                        updateSensor(index, (current) => ({
                          ...current,
                          attributes_text: event.target.value
                        }))
                      }
                      value={sensor.attributes_text}
                    />
                  </label>
                </section>
              ))}
            </div>

            {saveMutation.error ? (
              <p className="studio-inline-feedback studio-inline-feedback--error">{saveMutation.error.message}</p>
            ) : null}
            {saveMutation.data ? (
              <p className="studio-inline-feedback studio-inline-feedback--success">
                已保存模板 {saveMutation.data.display_name}。
              </p>
            ) : null}
          </Panel>

          <div className="grid gap-5 2xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <Panel className="studio-preview-panel" title="当前保存态" subtitle="最近一次保存结果。">
              {selectedProfile ? (
                <pre className="json-block json-block--compact studio-preview-block">{selectedProfile.raw_yaml}</pre>
              ) : (
                <EmptyState title="还没有已保存模板" description="先选择或创建一个传感器模板。" />
              )}
            </Panel>

            <Panel className="studio-preview-panel" title="待保存预览" subtitle="即将提交的数据。">
              <JsonBlock compact value={previewPayload} />
            </Panel>
          </div>

          <Panel title="模板使用范围" subtitle="可使用当前模板的场景。">
            {selectedProfileName ? (
              selectedProfileScenarioDefaults.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {selectedProfileScenarioDefaults.map((item: ScenarioCatalogItem) => (
                    <span key={item.scenario_id} className="studio-usage-chip">
                      {item.display_name}
                    </span>
                  ))}
                </div>
              ) : (
                <EmptyState
                  title="当前没有默认绑定场景"
                  description="可在支持模板切换的场景中手动选择。"
                />
              )
            ) : (
              <EmptyState title="未选择模板" description="先从左侧选择一个模板。" />
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}

function renderPiGatewayCommandFeedback(result: PiGatewayCommandResult | null) {
  if (!result) {
    return null;
  }

  return (
    <div className="studio-runtime-command">
      <p
        className={
          result.success
            ? 'studio-inline-feedback studio-inline-feedback--success'
            : 'studio-inline-feedback studio-inline-feedback--error'
        }
      >
        最近一次 {result.action === 'start' ? '启动' : '停止'}
        {result.success ? '成功' : '失败'}，exit code {result.exit_code}。
      </p>
      {result.output ? <pre className="json-block json-block--compact studio-command-log">{result.output}</pre> : null}
    </div>
  );
}
