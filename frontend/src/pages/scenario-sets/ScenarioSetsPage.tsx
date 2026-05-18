import { useEffect, useMemo, useState } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { listBenchmarkDefinitions } from '../../api/benchmarks';
import { listProjects } from '../../api/projects';
import {
  launchScenario,
  listEnvironmentPresets,
  listMaps,
  listScenarioCatalog,
  listSensorProfiles
} from '../../api/scenarios';
import type {
  EnvironmentPreset,
  MapOption,
  ScenarioCatalogItem,
  SensorProfile,
  ScenarioTemplateParameterSchema,
  ScenarioTemplateParamValue
} from '../../api/types';
import { EmptyState } from '../../components/common/EmptyState';
import { SelectionList } from '../../components/common/SelectionList';
import { StatusPill } from '../../components/common/StatusPill';
import { setWorkflowSelection, useWorkflowSelection } from '../../features/workflow/state';
import { findBenchmarkDefinition, findProjectRecord } from '../../lib/platform';

interface ScenarioSectionRow {
  label: string;
  value: string;
}

interface ScenarioSection {
  title: string;
  rows: ScenarioSectionRow[];
}

const INTEGER_PARAMETER_TYPES = new Set([
  'int',
  'integer',
  'long',
  'short',
  'unsignedint',
  'unsignedinteger',
  'unsignedlong',
  'unsignedshort'
]);

function mapFamilyKey(mapName: string) {
  const parts = mapName.trim().split('/').filter(Boolean);
  const tail = parts[parts.length - 1] ?? '';
  const normalized = tail.toLowerCase().endsWith('_opt') ? tail.slice(0, -4) : tail;
  return normalized.toLowerCase() === 'town10' ? 'town10hd' : normalized.toLowerCase();
}

function mapSelectionMode(item: ScenarioCatalogItem) {
  return item.map_selection_mode ?? (item.launch_capabilities.map_editable ? 'all' : 'fixed');
}

function buildScenarioMapOptions(
  item: ScenarioCatalogItem | null,
  runtimeMaps: MapOption[] | undefined
) {
  if (!item) {
    return [];
  }

  const mode = mapSelectionMode(item);
  const runtimeMapNames = runtimeMaps?.map((map) => map.map_name) ?? [];
  if (mode === 'fixed') {
    return [item.default_map_name];
  }
  if (mode === 'all') {
    return runtimeMapNames.length > 0 ? runtimeMapNames : [item.default_map_name];
  }

  const allowedMapNames =
    item.allowed_map_names.length > 0 ? item.allowed_map_names : [item.default_map_name];
  if (runtimeMapNames.length === 0) {
    return allowedMapNames;
  }

  const allowedFamilyKeys = new Set(allowedMapNames.map(mapFamilyKey));
  const intersected = runtimeMapNames.filter((mapName) => allowedFamilyKeys.has(mapFamilyKey(mapName)));
  return intersected.length > 0 ? intersected : allowedMapNames;
}

function formatMapSelectionMeta(item: ScenarioCatalogItem) {
  const mode = mapSelectionMode(item);
  if (mode === 'fixed') {
    return '固定地图';
  }
  if (mode === 'all') {
    return '全地图可用';
  }
  const count = item.allowed_map_names.length || 1;
  return `可选 ${count} 张地图`;
}

function numberLabel(value: number | undefined) {
  if (typeof value !== 'number') {
    return '-';
  }
  return Number.isInteger(value) ? `${value}` : value.toFixed(2);
}

function buildDefaultTemplateParams(
  parameters: ScenarioTemplateParameterSchema[]
): Record<string, ScenarioTemplateParamValue> {
  const defaults: Record<string, ScenarioTemplateParamValue> = {};
  for (const parameter of parameters) {
    if (parameter.default !== undefined && parameter.default !== null) {
      defaults[parameter.field] = parameter.default;
      continue;
    }
    if (parameter.type === 'boolean') {
      defaults[parameter.field] = false;
      continue;
    }
    if (parameter.type === 'enum' && parameter.options[0]) {
      defaults[parameter.field] = parameter.options[0];
      continue;
    }
    if (parameter.type === 'number') {
      defaults[parameter.field] = parameter.min ?? 0;
      continue;
    }
    defaults[parameter.field] = '';
  }
  return defaults;
}

function formatTemplateParamValue(
  parameter: ScenarioTemplateParameterSchema,
  value: ScenarioTemplateParamValue | undefined
) {
  if (value === undefined || value === null || value === '') {
    return '-';
  }
  if (typeof value === 'boolean') {
    return value ? '是' : '否';
  }
  const rendered = typeof value === 'number' ? numberLabel(value) : `${value}`;
  return parameter.unit ? `${rendered} ${parameter.unit}` : rendered;
}

function clampTemplateNumberValue(
  parameter: ScenarioTemplateParameterSchema,
  value: number
) {
  let next = value;
  if (typeof parameter.min === 'number') {
    next = Math.max(parameter.min, next);
  }
  if (typeof parameter.max === 'number') {
    next = Math.min(parameter.max, next);
  }
  if (INTEGER_PARAMETER_TYPES.has((parameter.parameter_type ?? '').toLowerCase())) {
    next = Math.trunc(next);
  }
  return next;
}

function parseTemplateNumberInput(
  rawValue: string,
  parameter: ScenarioTemplateParameterSchema,
  fallback: number
) {
  if (!rawValue.trim()) {
    const defaultValue =
      typeof parameter.default === 'number' ? parameter.default : fallback;
    return clampTemplateNumberValue(parameter, defaultValue);
  }
  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return clampTemplateNumberValue(parameter, parsed);
}

function buildTemplateParamsPayload(
  parameters: ScenarioTemplateParameterSchema[],
  values: Record<string, ScenarioTemplateParamValue>
) {
  const payload: Record<string, ScenarioTemplateParamValue> = {};
  for (const parameter of parameters) {
    const currentValue = values[parameter.field];
    if (currentValue === undefined || currentValue === null || currentValue === '') {
      if (parameter.required) {
        const fallback = parameter.default;
        if (fallback !== undefined && fallback !== null && fallback !== '') {
          payload[parameter.field] = fallback;
        }
      }
      continue;
    }
    payload[parameter.field] = currentValue;
  }
  return Object.keys(payload).length > 0 ? payload : undefined;
}

function buildScenarioSections(
  item: ScenarioCatalogItem,
  selectedMapName: string,
  selectedPreset: EnvironmentPreset | undefined,
  selectedSensorProfile: SensorProfile | undefined,
  vehicleCount: number,
  walkerCount: number,
  trafficSeedLabel: string,
  timeoutSeconds: number,
  templateParams: Record<string, ScenarioTemplateParamValue>
): ScenarioSection[] {
  const descriptor = item.descriptor_template;
  const spawn = descriptor.ego_vehicle.spawn_point;

  const sections: ScenarioSection[] = [
    {
      title: '启动配置',
      rows: [
        { label: '测试地图', value: selectedMapName || item.default_map_name },
        { label: '天气预设', value: selectedPreset?.display_name ?? '未选择' },
        { label: '传感器模板', value: selectedSensorProfile?.display_name ?? '未启用' },
        { label: '背景车辆', value: `${vehicleCount}` },
        { label: '背景行人', value: `${walkerCount}` },
        { label: '随机种子', value: trafficSeedLabel },
        {
          label: '最长运行时长',
          value:
            item.launch_capabilities.timeout_editable === false
              ? '手动停止'
              : `${timeoutSeconds} s`
        }
      ]
    },
    {
      title: 'Ego 初始状态',
      rows: [
        { label: '蓝图', value: descriptor.ego_vehicle.blueprint },
        {
          label: 'Spawn',
          value: `x ${numberLabel(spawn.x)}, y ${numberLabel(spawn.y)}, z ${numberLabel(spawn.z)}`
        },
        { label: 'Yaw', value: numberLabel(spawn.yaw) },
        {
          label: '同步模式',
          value: descriptor.sync.enabled
            ? `${numberLabel(descriptor.sync.fixed_delta_seconds)} s / tick`
            : 'Disabled'
        }
      ]
    },
    {
      title: '剧本约束',
      rows: [
        { label: '事件摘要', value: item.preset.event_summary },
        { label: 'Actor 摘要', value: item.preset.actors_summary },
        {
          label: '可调项',
          value: ['地图', '天气', '传感器模板', '背景车辆', '背景行人', '超时']
            .filter((label, index) => {
              const flags = [
                item.launch_capabilities.map_editable,
                item.launch_capabilities.weather_editable,
                item.launch_capabilities.sensor_profile_editable,
                item.launch_capabilities.traffic_vehicle_count_editable,
                item.launch_capabilities.traffic_walker_count_editable,
                item.launch_capabilities.timeout_editable
              ];
              return flags[index];
            })
            .concat(item.parameter_schema.length > 0 ? ['剧本参数'] : [])
            .join(' / ')
        }
      ]
    }
  ];

  if (item.parameter_schema.length > 0) {
    sections.push({
      title: '剧本参数',
      rows: item.parameter_schema.map((parameter) => ({
        label: parameter.label,
        value: formatTemplateParamValue(parameter, templateParams[parameter.field])
      }))
    });
  }

  return sections;
}

function clampCount(value: number, max: number) {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(max, Math.max(0, Math.trunc(value)));
}

function parseIntegerInput(rawValue: string, fallback: number) {
  if (!rawValue.trim()) {
    return fallback;
  }
  const parsed = Number(rawValue);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : fallback;
}

function parseOptionalSeedInput(rawValue: string) {
  if (!rawValue.trim()) {
    return undefined;
  }
  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed)) {
    return undefined;
  }
  return Math.max(0, Math.trunc(parsed));
}

function buildLaunchTags(
  scenarioId: string,
  projectId: string | null,
  benchmarkDefinitionId: string | null
) {
  return [
    'scenario_runner',
    'scenario_launch',
    scenarioId,
    projectId ? `project:${projectId}` : null,
    benchmarkDefinitionId ? `benchmark:${benchmarkDefinitionId}` : null
  ].filter((value): value is string => Boolean(value));
}

export function ScenarioSetsPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const workflow = useWorkflowSelection();
  const [searchParams] = useSearchParams();
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [selectedEnvironmentPresetId, setSelectedEnvironmentPresetId] = useState('');
  const [selectedSensorProfileName, setSelectedSensorProfileName] = useState('');
  const [selectedMapName, setSelectedMapName] = useState('');
  const [vehicleCount, setVehicleCount] = useState(0);
  const [walkerCount, setWalkerCount] = useState(0);
  const [trafficSeedInput, setTrafficSeedInput] = useState('');
  const [timeoutSeconds, setTimeoutSeconds] = useState(120);
  const [autoStart, setAutoStart] = useState(true);
  const [templateParams, setTemplateParams] = useState<Record<string, ScenarioTemplateParamValue>>(
    {}
  );

  const projectsQuery = useQuery({ queryKey: ['projects'], queryFn: listProjects });
  const definitionsQuery = useQuery({
    queryKey: ['benchmark-definitions'],
    queryFn: listBenchmarkDefinitions
  });
  const catalogQuery = useQuery({ queryKey: ['scenario-catalog'], queryFn: listScenarioCatalog });
  const mapsQuery = useQuery({ queryKey: ['maps'], queryFn: listMaps });
  const environmentPresetsQuery = useQuery({
    queryKey: ['environment-presets'],
    queryFn: listEnvironmentPresets
  });
  const sensorProfilesQuery = useQuery({
    queryKey: ['sensor-profiles'],
    queryFn: listSensorProfiles
  });

  const runnableScenarios = (catalogQuery.data ?? []).filter(
    (item) => item.execution_support === 'native' || item.execution_support === 'scenario_runner'
  );
  const environmentPresets = environmentPresetsQuery.data ?? [];
  const sensorProfiles = sensorProfilesQuery.data ?? [];
  const selectedScenario = workflow.scenarioId
    ? runnableScenarios.find((item) => item.scenario_id === workflow.scenarioId) ?? null
    : null;
  const selectedProject = workflow.projectId
    ? findProjectRecord(projectsQuery.data ?? [], workflow.projectId)
    : null;
  const selectedBenchmark = workflow.benchmarkDefinitionId
    ? findBenchmarkDefinition(definitionsQuery.data ?? [], workflow.benchmarkDefinitionId)
    : null;
  const selectedEnvironmentPreset = environmentPresets.find(
    (item) => item.preset_id === selectedEnvironmentPresetId
  );
  const selectedSensorProfile = sensorProfiles.find(
    (item) => item.profile_name === selectedSensorProfileName
  );

  const selectedCapabilities = selectedScenario?.launch_capabilities;
  const availableMaps = useMemo(
    () => buildScenarioMapOptions(selectedScenario, mapsQuery.data),
    [mapsQuery.data, selectedScenario]
  );
  const launchModeLabel = autoStart ? '创建后立即执行' : '仅创建待启动';
  const scenarioSections = selectedScenario
    ? buildScenarioSections(
        selectedScenario,
        selectedMapName || selectedScenario.default_map_name,
        selectedEnvironmentPreset,
        selectedSensorProfile,
        vehicleCount,
        walkerCount,
        trafficSeedInput.trim() || '自动生成',
        timeoutSeconds,
        templateParams
      )
    : [];

  useEffect(() => {
    if (!workflow.scenarioId && runnableScenarios[0]) {
      setWorkflowSelection({ scenarioId: runnableScenarios[0].scenario_id });
    }
  }, [runnableScenarios, workflow.scenarioId]);

  useEffect(() => {
    const scenarioFromQuery = searchParams.get('scenario');
    if (
      scenarioFromQuery &&
      runnableScenarios.some((item) => item.scenario_id === scenarioFromQuery) &&
      scenarioFromQuery !== workflow.scenarioId
    ) {
      setWorkflowSelection({ scenarioId: scenarioFromQuery });
    }
  }, [runnableScenarios, searchParams, workflow.scenarioId]);

  useEffect(() => {
    if (!selectedEnvironmentPresetId && environmentPresets[0]) {
      setSelectedEnvironmentPresetId(environmentPresets[0].preset_id);
    }
  }, [environmentPresets, selectedEnvironmentPresetId]);

  useEffect(() => {
    if (!selectedSensorProfileName && sensorProfiles[0]) {
      setSelectedSensorProfileName(sensorProfiles[0].profile_name);
    }
  }, [selectedSensorProfileName, sensorProfiles]);

  useEffect(() => {
    if (!selectedScenario) {
      return;
    }
    setSelectorOpen(false);
    setSelectedMapName(selectedScenario.default_map_name);
    setVehicleCount(clampCount(selectedScenario.descriptor_template.traffic.num_vehicles, 48));
    setWalkerCount(clampCount(selectedScenario.descriptor_template.traffic.num_walkers, 48));
    setTrafficSeedInput(
      typeof selectedScenario.descriptor_template.traffic.seed === 'number'
        ? `${selectedScenario.descriptor_template.traffic.seed}`
        : ''
    );
    setTimeoutSeconds(selectedScenario.descriptor_template.termination.timeout_seconds);
    setTemplateParams(buildDefaultTemplateParams(selectedScenario.parameter_schema));
    const defaultSensorProfileName = selectedScenario.descriptor_template.sensors.profile_name;
    if (defaultSensorProfileName) {
      setSelectedSensorProfileName(defaultSensorProfileName);
    }
  }, [selectedScenario?.scenario_id]);

  useEffect(() => {
    if (!selectedScenario) {
      return;
    }
    if (!selectedMapName) {
      setSelectedMapName(selectedScenario.default_map_name);
      return;
    }
    const selectedMapAllowed = availableMaps.some(
      (mapName) => mapFamilyKey(mapName) === mapFamilyKey(selectedMapName)
    );
    if (availableMaps.length > 0 && !selectedMapAllowed) {
      setSelectedMapName(selectedScenario.default_map_name);
    }
  }, [availableMaps, selectedMapName, selectedScenario?.default_map_name]);

  const launchMutation = useMutation({
    mutationFn: async () => {
      if (!selectedScenario) {
        throw new Error('请先选择运行场景');
      }
      if (!selectedEnvironmentPreset) {
        throw new Error('请先选择天气预设');
      }

      return launchScenario({
        scenario_id: selectedScenario.scenario_id,
        map_name:
          mapSelectionMode(selectedScenario) === 'fixed'
            ? selectedScenario.default_map_name
            : selectedMapName || selectedScenario.default_map_name,
        weather:
          selectedCapabilities?.weather_editable === false
            ? undefined
            : selectedEnvironmentPreset.weather,
        traffic: {
          num_vehicles: clampCount(
            vehicleCount,
            selectedCapabilities?.max_vehicle_count ?? 48
          ),
          num_walkers: clampCount(
            walkerCount,
            selectedCapabilities?.max_walker_count ?? 48
          ),
          seed: parseOptionalSeedInput(trafficSeedInput)
        },
        sensor_profile_name:
          selectedCapabilities?.sensor_profile_editable === true
            ? selectedSensorProfileName || undefined
            : undefined,
        template_params: buildTemplateParamsPayload(
          selectedScenario.parameter_schema,
          templateParams
        ),
        timeout_seconds:
          selectedCapabilities?.timeout_editable === false ? undefined : timeoutSeconds,
        auto_start: autoStart,
        metadata: {
          author: 'scenario-sets-ui',
          description: `${selectedScenario.display_name}（Scenario Sets Launch）`,
          tags: buildLaunchTags(
            selectedScenario.scenario_id,
            workflow.projectId,
            workflow.benchmarkDefinitionId
          )
        }
      });
    },
    onSuccess: (run) => {
      setWorkflowSelection({
        scenarioId: run.scenario_name,
        runId: run.run_id
      });
      void queryClient.invalidateQueries({ queryKey: ['runs'] });
      void queryClient.invalidateQueries({ queryKey: ['system-status'] });
      void queryClient.invalidateQueries({ queryKey: ['runs', run.run_id] });
      navigate(`/executions/${run.run_id}`);
    }
  });

  const launchDisabled =
    launchMutation.isPending || environmentPresetsQuery.isError || !selectedScenario;
  const launchButtonLabel = launchMutation.isPending
    ? '提交中...'
    : autoStart
      ? '创建并启动场景'
      : '创建场景运行';
  const selectedMapLabel = selectedScenario
    ? selectedMapName || selectedScenario.default_map_name
    : '未选择';
  const validationLabel = !selectedScenario
    ? '等待场景'
    : environmentPresetsQuery.isError
      ? '校验失败'
      : mapsQuery.isError
        ? '部分降级'
        : '可创建并运行';
  const validationTone = !selectedScenario
    ? 'muted'
    : environmentPresetsQuery.isError
      ? 'error'
      : mapsQuery.isError
        ? 'warning'
        : launchMutation.isPending
          ? 'info'
          : 'success';

  return (
    <div className="page-stack project-console scenario-automation">
      <header className="scenario-automation__topbar">
        <div className="scenario-automation__path">
          场景集 / 参数编排 / 单次运行自动化
        </div>
        <div className="scenario-automation__topbar-actions">
          <span
            className={[
              'scenario-automation__status-badge',
              `scenario-automation__status-badge--${validationTone}`
            ].join(' ')}
          >
            {validationLabel}
          </span>
          <Link className="horizon-button-secondary" to="/benchmarks" viewTransition>
            返回基准任务台
          </Link>
          <Link className="horizon-button-secondary" to="/executions" viewTransition>
            打开执行台
          </Link>
          <button
            className="horizon-button scenario-automation__primary-action"
            disabled={launchDisabled}
            onClick={() => launchMutation.mutate()}
            type="button"
          >
            {launchButtonLabel}
          </button>
        </div>
      </header>

      <div className="scenario-automation__layout">
        <main className="scenario-automation__main">
          <section className="scenario-automation__intro horizon-card">
            <div className="scenario-automation__intro-copy">
              <span className="project-console__section-label">场景集配置</span>
              <h1 className="scenario-automation__title" style={{ viewTransitionName: 'page-title' }}>
                场景集 / 单次运行自动化
              </h1>
              <p>
                从场景目录选择一个运行模板，再为这次运行实例补齐地图、天气、传感器、背景交通和启动模式。
              </p>
            </div>
            <div className="scenario-automation__intro-actions">
              {selectedScenario && <StatusPill canonical status="READY" />}
              <button
                className="project-console__picker-button"
                onClick={() => setSelectorOpen(true)}
                type="button"
              >
                {selectedScenario ? '切换场景' : '选择运行场景'}
              </button>
            </div>
          </section>

          {!selectedScenario ? (
            <section className="scenario-automation__empty horizon-card">
              <EmptyState
                description="先选择场景，再设置地图、天气、传感器模板和背景交通。"
                title="未选择场景"
              />
            </section>
          ) : (
            <>
              <section className="scenario-summary horizon-card">
                <header className="scenario-summary__header">
                  <div>
                    <span className="project-console__section-label">运行配置摘要</span>
                    <h2>当前运行实例</h2>
                  </div>
                  <span
                    className={[
                      'scenario-automation__status-badge',
                      autoStart
                        ? 'scenario-automation__status-badge--info'
                        : 'scenario-automation__status-badge--muted'
                    ].join(' ')}
                  >
                    {launchModeLabel}
                  </span>
                </header>

                <div className="scenario-summary__grid">
                  <div className="scenario-summary__item">
                    <span>场景</span>
                    <strong>{selectedScenario.display_name}</strong>
                    <small>{selectedScenario.scenario_id}</small>
                  </div>
                  <div className="scenario-summary__item">
                    <span>地图范围</span>
                    <strong>{formatMapSelectionMeta(selectedScenario)}</strong>
                    <small>{selectedMapLabel}</small>
                  </div>
                  <div className="scenario-summary__item">
                    <span>剧本参数</span>
                    <strong>{selectedScenario.parameter_schema.length}</strong>
                    <small>只展示当前场景支持直观调整的参数</small>
                  </div>
                  <div className="scenario-summary__item">
                    <span>传感器模板</span>
                    <strong>{selectedSensorProfile?.display_name ?? '未绑定'}</strong>
                    <small>{selectedSensorProfileName || '未选择模板'}</small>
                  </div>
                </div>
              </section>

              <section className="scenario-config horizon-card">
                <header className="scenario-config__header">
                  <div>
                    <span className="project-console__section-label">详细配置</span>
                    <h2>{selectedScenario.display_name}</h2>
                    <p>地图、天气、传感器模板和背景交通只写入本次运行，不改变模板默认值。</p>
                  </div>
                  <StatusPill status={autoStart ? 'READY' : 'CREATED'} />
                </header>

                <div className="scenario-config__stack">
                  <section className="scenario-config__section">
                    <header className="scenario-config__section-header">
                      <h3>目标配置</h3>
                      <p>确认本次运行的场景、地图、天气与传感器模板。</p>
                    </header>
                    <div className="scenario-config__field-grid">
                      <div className="scenario-config__selector-field">
                        <span className="project-console__section-label">运行场景</span>
                        <strong>{selectedScenario.display_name}</strong>
                        <p>{selectedScenario.description}</p>
                        <button
                          className="project-console__picker-button"
                          onClick={() => setSelectorOpen(true)}
                          type="button"
                        >
                          切换场景
                        </button>
                      </div>

                      <label className="field">
                        <span>测试地图</span>
                        <select
                          disabled={mapSelectionMode(selectedScenario) === 'fixed'}
                          onChange={(event) => setSelectedMapName(event.target.value)}
                          value={selectedMapName}
                        >
                          {(availableMaps.length > 0
                            ? availableMaps
                            : [selectedScenario.default_map_name]
                          ).map((mapName) => (
                            <option key={mapName} value={mapName}>
                              {mapName}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label className="field">
                        <span>天气预设</span>
                        <select
                          disabled={selectedCapabilities?.weather_editable === false}
                          onChange={(event) => setSelectedEnvironmentPresetId(event.target.value)}
                          value={selectedEnvironmentPresetId}
                        >
                          {environmentPresets.map((item) => (
                            <option key={item.preset_id} value={item.preset_id}>
                              {item.display_name}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label className="field">
                        <span>传感器模板</span>
                        <select
                          disabled={selectedCapabilities?.sensor_profile_editable === false}
                          onChange={(event) => setSelectedSensorProfileName(event.target.value)}
                          value={selectedSensorProfileName}
                        >
                          {sensorProfiles.map((item) => (
                            <option key={item.profile_name} value={item.profile_name}>
                              {item.display_name}
                            </option>
                          ))}
                        </select>
                        <small className="mt-2 block text-xs text-secondaryGray-500">
                          模板参数在
                          {' '}
                          <Link className="font-semibold text-brand-500 underline-offset-4 hover:underline" to="/studio">
                            运维页
                          </Link>
                          {' '}
                          维护。
                        </small>
                      </label>
                    </div>
                  </section>

                  <section className="scenario-config__section">
                    <header className="scenario-config__section-header">
                      <h3>执行策略</h3>
                      <p>设置背景参与者、随机性和创建后的启动方式。</p>
                    </header>
                    <div className="scenario-config__field-grid">
                      <label className="field">
                        <span>背景车辆</span>
                        <input
                          disabled={selectedCapabilities?.traffic_vehicle_count_editable === false}
                          max={selectedCapabilities?.max_vehicle_count ?? 48}
                          min={0}
                          onChange={(event) =>
                            setVehicleCount(
                              clampCount(
                                parseIntegerInput(event.target.value, vehicleCount),
                                selectedCapabilities?.max_vehicle_count ?? 48
                              )
                            )
                          }
                          type="number"
                          value={vehicleCount}
                        />
                      </label>

                      <label className="field">
                        <span>背景行人</span>
                        <input
                          disabled={selectedCapabilities?.traffic_walker_count_editable === false}
                          max={selectedCapabilities?.max_walker_count ?? 48}
                          min={0}
                          onChange={(event) =>
                            setWalkerCount(
                              clampCount(
                                parseIntegerInput(event.target.value, walkerCount),
                                selectedCapabilities?.max_walker_count ?? 48
                              )
                            )
                          }
                          type="number"
                          value={walkerCount}
                        />
                      </label>

                      <label className="field">
                        <span>随机种子</span>
                        <input
                          min={0}
                          onChange={(event) => setTrafficSeedInput(event.target.value)}
                          placeholder="留空自动生成"
                          type="number"
                          value={trafficSeedInput}
                        />
                        <small className="text-xs text-slate-500">
                          控制背景交通与自由漫游的随机性；留空时后端会为每条 run 自动生成。
                        </small>
                      </label>

                      <section className="project-console__launch-card scenario-config__launch-mode">
                        <div className="project-console__launch-copy">
                          <span className="project-console__section-label">启动模式</span>
                          <strong>{autoStart ? '创建后立即执行' : '仅创建到执行队列'}</strong>
                          <p>
                            {autoStart
                              ? '提交后立即执行。'
                              : '提交后稍后手动启动。'}
                          </p>
                        </div>

                        <div className="project-console__launch-controls">
                          <span
                            className={[
                              'project-console__state-chip',
                              autoStart
                                ? 'project-console__state-chip--warm'
                                : 'project-console__state-chip--muted'
                            ].join(' ')}
                          >
                            {autoStart ? '自动启动' : '手动启动'}
                          </span>

                          <label className="project-console__launch-toggle">
                            <input
                              checked={autoStart}
                              onChange={(event) => setAutoStart(event.target.checked)}
                              type="checkbox"
                            />
                            <span className="project-console__launch-toggle-track">
                              <span className="project-console__launch-toggle-thumb" />
                            </span>
                            <span className="project-console__launch-toggle-copy">
                              立即执行
                            </span>
                          </label>
                        </div>
                      </section>
                    </div>
                  </section>

                  <section className="scenario-config__section">
                    <header className="scenario-config__section-header">
                      <h3>运行参数</h3>
                      <p>设置运行时长和当前场景暴露的剧本参数。</p>
                    </header>
                    <div className="scenario-config__field-grid">
                      <label className="field">
                        <span>最长运行时长（秒）</span>
                        <input
                          disabled={selectedCapabilities?.timeout_editable === false}
                          min={1}
                          onChange={(event) =>
                            setTimeoutSeconds(Math.max(1, parseIntegerInput(event.target.value, timeoutSeconds)))
                          }
                          type="number"
                          value={timeoutSeconds}
                        />
                        <small className="text-xs text-slate-500">
                          {selectedCapabilities?.timeout_editable === false
                            ? '该场景需要手动停止。'
                            : '到时后会自动结束。'}
                        </small>
                      </label>

                      {selectedScenario.parameter_schema.length > 0 ? (
                        selectedScenario.parameter_schema.map((parameter) => {
                          if (parameter.type === 'boolean') {
                            return (
                              <label className="field field--checkbox" key={parameter.field}>
                                <input
                                  checked={Boolean(templateParams[parameter.field])}
                                  onChange={(event) =>
                                    setTemplateParams((current) => ({
                                      ...current,
                                      [parameter.field]: event.target.checked
                                    }))
                                  }
                                  type="checkbox"
                                />
                                <span>{parameter.label}</span>
                              </label>
                            );
                          }

                          if (parameter.type === 'enum') {
                            return (
                              <label className="field" key={parameter.field}>
                                <span>{parameter.label}</span>
                                <select
                                  onChange={(event) =>
                                    setTemplateParams((current) => ({
                                      ...current,
                                      [parameter.field]: event.target.value
                                    }))
                                  }
                                  value={String(templateParams[parameter.field] ?? '')}
                                >
                                  {parameter.options.map((option) => (
                                    <option key={option} value={option}>
                                      {option}
                                    </option>
                                  ))}
                                </select>
                                {parameter.description && (
                                  <small className="text-xs text-slate-500">
                                    {parameter.description}
                                  </small>
                                )}
                              </label>
                            );
                          }

                          if (parameter.type === 'number') {
                            const currentValue = templateParams[parameter.field];
                            const fallbackValue =
                              typeof currentValue === 'number'
                                ? currentValue
                                : typeof parameter.default === 'number'
                                  ? parameter.default
                                  : 0;
                            return (
                              <label className="field" key={parameter.field}>
                                <span>{parameter.label}</span>
                                <input
                                  max={parameter.max ?? undefined}
                                  min={parameter.min ?? undefined}
                                  onChange={(event) =>
                                    setTemplateParams((current) => ({
                                      ...current,
                                      [parameter.field]: parseTemplateNumberInput(
                                        event.target.value,
                                        parameter,
                                        fallbackValue
                                      )
                                    }))
                                  }
                                  step={parameter.step ?? undefined}
                                  type="number"
                                  value={typeof currentValue === 'number' ? currentValue : fallbackValue}
                                />
                                {(parameter.description || parameter.unit) && (
                                  <small className="text-xs text-slate-500">
                                    {[parameter.description, parameter.unit ? `单位: ${parameter.unit}` : null]
                                      .filter(Boolean)
                                      .join(' / ')}
                                  </small>
                                )}
                              </label>
                            );
                          }

                          return (
                            <label className="field" key={parameter.field}>
                              <span>{parameter.label}</span>
                              <input
                                onChange={(event) =>
                                  setTemplateParams((current) => ({
                                    ...current,
                                    [parameter.field]: event.target.value
                                  }))
                                }
                                type="text"
                                value={String(templateParams[parameter.field] ?? '')}
                              />
                              {parameter.description && (
                                <small className="text-xs text-slate-500">
                                  {parameter.description}
                                </small>
                              )}
                            </label>
                          );
                        })
                      ) : (
                        <div className="scenario-config__inline-note">
                          当前场景没有额外剧本参数。
                        </div>
                      )}
                    </div>
                  </section>

                  <section className="scenario-config__section">
                    <header className="scenario-config__section-header">
                      <h3>高级设置</h3>
                      <p>这里汇总场景真正会带进运行的配置。</p>
                    </header>
                    <div className="scenario-brief-grid">
                      {scenarioSections.map((section) => (
                        <section className="project-console__parameter-card" key={section.title}>
                          <header>
                            <strong>{section.title}</strong>
                          </header>
                          <div className="project-console__parameter-rows">
                            {section.rows.map((row) => (
                              <div
                                className="project-console__parameter-row"
                                key={`${section.title}-${row.label}`}
                              >
                                <span>{row.label}</span>
                                <strong>{row.value}</strong>
                              </div>
                            ))}
                          </div>
                        </section>
                      ))}
                    </div>
                  </section>

                  {(mapsQuery.isError || environmentPresetsQuery.isError || launchMutation.error) && (
                    <div className="scenario-config__alerts">
                      {mapsQuery.isError && (
                        <p className="scenario-alert scenario-alert--warning">
                          地图接口当前不可用，先回退到场景默认地图。
                        </p>
                      )}
                      {environmentPresetsQuery.isError && (
                        <p className="scenario-alert scenario-alert--error">
                          天气预设加载失败，当前无法安全发起运行。
                        </p>
                      )}
                      {launchMutation.error && (
                        <p className="scenario-alert scenario-alert--error">{launchMutation.error.message}</p>
                      )}
                    </div>
                  )}
                </div>
              </section>
            </>
          )}
        </main>

        <aside className="scenario-context">
          <section className="scenario-context__card horizon-card">
            <header className="scenario-context__header">
              <div>
                <span className="project-console__section-label">执行上下文</span>
                <h2>运行上下文</h2>
              </div>
              <span
                className={[
                  'scenario-automation__status-badge',
                  `scenario-automation__status-badge--${validationTone}`
                ].join(' ')}
              >
                {validationLabel}
              </span>
            </header>

            {selectedScenario ? (
              <div className="scenario-context__stack">
                <div className="scenario-context__row">
                  <span>项目</span>
                  <strong>{selectedProject?.name ?? '未选择项目'}</strong>
                </div>
                <div className="scenario-context__row">
                  <span>模板</span>
                  <strong>{selectedBenchmark?.name ?? '未选择模板'}</strong>
                </div>
                <div className="scenario-context__row">
                  <span>地图</span>
                  <strong>{selectedMapLabel}</strong>
                </div>
                <div className="scenario-context__row">
                  <span>天气</span>
                  <strong>{selectedEnvironmentPreset?.display_name ?? '未选择'}</strong>
                </div>
                <div className="scenario-context__row">
                  <span>背景交通</span>
                  <strong>{vehicleCount} 车 / {walkerCount} 行人</strong>
                </div>
                <div className="scenario-context__row">
                  <span>随机种子</span>
                  <strong>{trafficSeedInput.trim() || '自动生成'}</strong>
                </div>
                {selectedScenario.parameter_schema.map((parameter) => (
                  <div className="scenario-context__row" key={parameter.field}>
                    <span>{parameter.label}</span>
                    <strong>{formatTemplateParamValue(parameter, templateParams[parameter.field])}</strong>
                  </div>
                ))}
                <small>{autoStart ? '创建后会直接执行。' : '创建后等待手动启动。'}</small>
              </div>
            ) : (
              <EmptyState description="选择场景后，这里会汇总当前运行上下文。" title="没有运行上下文" />
            )}

            <div className="scenario-context__actions">
              <button
                className="horizon-button scenario-context__action"
                disabled={launchDisabled}
                onClick={() => launchMutation.mutate()}
                type="button"
              >
                {launchButtonLabel}
              </button>
              <Link className="horizon-button-secondary scenario-context__action" to="/executions" viewTransition>
                打开执行台
              </Link>
            </div>
          </section>

          <section className="scenario-context__card horizon-card">
            <header className="scenario-context__header">
              <div>
                <span className="project-console__section-label">配置校验</span>
                <h2>提交条件</h2>
              </div>
            </header>
            <div className="scenario-validation">
              <div
                className={[
                  'scenario-validation__item',
                  selectedScenario
                    ? 'scenario-validation__item--success'
                    : 'scenario-validation__item--muted'
                ].join(' ')}
              >
                <span />
                <strong>{selectedScenario ? '已选择运行场景' : '等待选择运行场景'}</strong>
              </div>
              <div
                className={[
                  'scenario-validation__item',
                  mapsQuery.isError
                    ? 'scenario-validation__item--warning'
                    : 'scenario-validation__item--success'
                ].join(' ')}
              >
                <span />
                <strong>{mapsQuery.isError ? '地图接口降级到默认值' : '地图范围已匹配'}</strong>
              </div>
              <div
                className={[
                  'scenario-validation__item',
                  environmentPresetsQuery.isError
                    ? 'scenario-validation__item--error'
                    : 'scenario-validation__item--success'
                ].join(' ')}
              >
                <span />
                <strong>{environmentPresetsQuery.isError ? '天气预设加载失败' : '天气预设可用'}</strong>
              </div>
              <div
                className={[
                  'scenario-validation__item',
                  launchMutation.isPending
                    ? 'scenario-validation__item--info'
                    : 'scenario-validation__item--muted'
                ].join(' ')}
              >
                <span />
                <strong>{launchMutation.isPending ? '正在提交运行请求' : '等待提交'}</strong>
              </div>
            </div>
          </section>

          {selectedScenario && (
            <section className="scenario-context__card horizon-card">
              <header className="scenario-context__header">
                <div>
                  <span className="project-console__section-label">运行元信息</span>
                  <h2>场景说明</h2>
                </div>
              </header>
              <div className="scenario-context__stack">
                <p>{selectedScenario.description}</p>
                {selectedScenario.launch_capabilities.notes.map((note) => (
                  <small key={note}>{note}</small>
                ))}
              </div>
            </section>
          )}
        </aside>
      </div>

      {selectorOpen && (
        <button
          aria-label="关闭场景选择抽屉"
          className="project-console__drawer-backdrop"
          onClick={() => setSelectorOpen(false)}
          type="button"
        />
      )}

      <aside
        aria-hidden={!selectorOpen}
        className={
          selectorOpen
            ? 'project-console__drawer project-console__drawer--open'
            : 'project-console__drawer'
        }
      >
          <header className="project-console__drawer-header">
            <div>
              <span className="project-console__section-label">选择运行场景</span>
              <strong>场景目录</strong>
            </div>
            <button
              className="project-console__drawer-close"
              onClick={() => setSelectorOpen(false)}
              type="button"
            >
              关闭
            </button>
          </header>

          <div className="project-console__drawer-copy">
            <p>请选择要运行的场景。</p>
          </div>

          {catalogQuery.isLoading ? (
            <EmptyState description="正在读取场景目录。" title="场景加载中" />
          ) : catalogQuery.isError ? (
            <EmptyState
              description={catalogQuery.error instanceof Error ? catalogQuery.error.message : '场景接口异常。'}
              title="场景加载失败"
            />
          ) : (
            <SelectionList
              collapseLabel="收起目录"
              emptyDescription="当前环境未返回可执行场景。"
              emptyTitle="没有可执行场景"
              expandLabel="展开目录"
              items={runnableScenarios.map((scenario) => ({
                id: scenario.scenario_id,
                title: scenario.display_name,
                subtitle: scenario.description,
                meta: `${formatMapSelectionMeta(scenario)} / 默认 ${scenario.default_map_name}`,
                status: 'READY',
                hint: scenario.scenario_id
              }))}
              maxVisible={8}
              onSelect={(id) => setWorkflowSelection({ scenarioId: id })}
              selectedId={selectedScenario?.scenario_id ?? null}
            />
          )}
      </aside>
    </div>
  );
}
