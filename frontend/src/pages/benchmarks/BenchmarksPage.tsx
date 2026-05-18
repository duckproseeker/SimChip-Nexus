import { useEffect, useMemo, useState } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';

import { createBenchmarkTask, listBenchmarkDefinitions, listBenchmarkTasks } from '../../api/benchmarks';
import { listGateways } from '../../api/gateways';
import { listProjects } from '../../api/projects';
import { listEvaluationProfiles, listScenarioCatalog } from '../../api/scenarios';
import type { BenchmarkDefinition, ScenarioCatalogItem } from '../../api/types';
import { EmptyState } from '../../components/common/EmptyState';
import { PageHeader } from '../../components/common/PageHeader';
import { Panel } from '../../components/common/Panel';
import { SelectionList } from '../../components/common/SelectionList';
import { StatusPill } from '../../components/common/StatusPill';
import { WorkflowNextStep } from '../../components/common/WorkflowNextStep';
import { setWorkflowSelection, useWorkflowSelection } from '../../features/workflow/state';
import { formatDateTime } from '../../lib/format';
import { findBenchmarkDefinition, findProjectRecord } from '../../lib/platform';

interface PlannedScenarioRow {
  scenario_id: string;
  display_name: string;
  execution_backend: string;
  map_name: string;
  timeout_seconds: number;
}

function planningModeLabel(mode: BenchmarkDefinition['planning_mode']) {
  if (mode === 'single_scenario') {
    return '单场景';
  }
  if (mode === 'timed_single_scenario') {
    return '长时单场景';
  }
  if (mode === 'all_runnable') {
    return '全量回归';
  }
  return '自定义批量';
}

function planningModeHint(mode: BenchmarkDefinition['planning_mode']) {
  if (mode === 'single_scenario') {
    return '从下拉列表选择 1 个场景直接进入本次测试。';
  }
  if (mode === 'timed_single_scenario') {
    return '选择 1 个高负载场景，并指定本轮仿真时长。';
  }
  if (mode === 'all_runnable') {
    return '自动把当前全部可执行场景加入本轮批量任务。';
  }
  return '点击加号打开场景目录，逐个加入当前测试。';
}

function formatDurationLabel(timeoutSeconds: number) {
  if (timeoutSeconds % 60 === 0) {
    return `${timeoutSeconds / 60} min`;
  }
  return `${timeoutSeconds} s`;
}

function deriveCandidateScenarios(
  definition: BenchmarkDefinition | null,
  runnableScenarios: ScenarioCatalogItem[]
) {
  if (!definition) {
    return [];
  }

  if (definition.candidate_scenario_ids.length === 0) {
    return runnableScenarios;
  }

  const catalogIndex = new Map(runnableScenarios.map((item) => [item.scenario_id, item]));
  return definition.candidate_scenario_ids
    .map((scenarioId) => catalogIndex.get(scenarioId) ?? null)
    .filter((item): item is ScenarioCatalogItem => item !== null);
}

function buildPlannedScenarioRows(
  definition: BenchmarkDefinition | null,
  candidateScenarios: ScenarioCatalogItem[],
  selectedScenarioIds: string[],
  runDurationMinutes: string
): PlannedScenarioRow[] {
  if (!definition) {
    return [];
  }

  const scenarioIndex = new Map(candidateScenarios.map((item) => [item.scenario_id, item]));
  const requestedDurationSeconds = Math.max(1, Number.parseInt(runDurationMinutes || '0', 10) || 0) * 60;

  const toRow = (scenario: ScenarioCatalogItem, timeoutSeconds?: number): PlannedScenarioRow => ({
    scenario_id: scenario.scenario_id,
    display_name: scenario.display_name,
    execution_backend: scenario.execution_backend ?? scenario.execution_support,
    map_name: scenario.default_map_name,
    timeout_seconds:
      timeoutSeconds ?? Number(scenario.descriptor_template.termination.timeout_seconds ?? 30)
  });

  if (definition.planning_mode === 'all_runnable') {
    return candidateScenarios.map((scenario) => toRow(scenario));
  }

  if (definition.planning_mode === 'single_scenario') {
    const selectedScenario = scenarioIndex.get(selectedScenarioIds[0] ?? '');
    return selectedScenario ? [toRow(selectedScenario)] : [];
  }

  if (definition.planning_mode === 'timed_single_scenario') {
    const selectedScenario = scenarioIndex.get(selectedScenarioIds[0] ?? '');
    return selectedScenario
      ? [
          toRow(
            selectedScenario,
            requestedDurationSeconds || definition.default_duration_seconds || 1800
          )
        ]
      : [];
  }

  return selectedScenarioIds
    .map((scenarioId) => scenarioIndex.get(scenarioId) ?? null)
    .filter((scenario): scenario is ScenarioCatalogItem => scenario !== null)
    .map((scenario) => toRow(scenario));
}

export function BenchmarksPage() {
  const workflow = useWorkflowSelection();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const [selectedScenarioIds, setSelectedScenarioIds] = useState<string[]>([]);
  const [runDurationMinutes, setRunDurationMinutes] = useState('30');
  const [dutModel, setDutModel] = useState('');
  const [selectedGatewayId, setSelectedGatewayId] = useState(workflow.gatewayId ?? '');
  const [evaluationProfileName, setEvaluationProfileName] = useState('');
  const [scenarioDrawerOpen, setScenarioDrawerOpen] = useState(false);
  const [pendingScenarioId, setPendingScenarioId] = useState<string | null>(null);

  const definitionsQuery = useQuery({
    queryKey: ['benchmark-definitions'],
    queryFn: listBenchmarkDefinitions
  });
  const tasksQuery = useQuery({
    queryKey: ['benchmark-tasks'],
    queryFn: () => listBenchmarkTasks(),
    refetchInterval: 5000
  });
  const projectsQuery = useQuery({ queryKey: ['projects'], queryFn: listProjects });
  const catalogQuery = useQuery({ queryKey: ['scenario-catalog'], queryFn: listScenarioCatalog });
  const gatewaysQuery = useQuery({
    queryKey: ['gateways'],
    queryFn: listGateways,
    refetchInterval: 5000
  });
  const profilesQuery = useQuery({
    queryKey: ['evaluation-profiles'],
    queryFn: listEvaluationProfiles
  });

  const definitions = definitionsQuery.data ?? [];
  const tasks = tasksQuery.data ?? [];
  const projects = projectsQuery.data ?? [];
  const gateways = gatewaysQuery.data ?? [];
  const evaluationProfiles = profilesQuery.data ?? [];
  const runnableScenarios = (catalogQuery.data ?? []).filter(
    (item) => item.execution_support === 'native' || item.execution_support === 'scenario_runner'
  );

  const selectedDefinition = workflow.benchmarkDefinitionId
    ? findBenchmarkDefinition(definitions, workflow.benchmarkDefinitionId)
    : null;

  const selectedProject = selectedDefinition?.default_project_id
    ? findProjectRecord(projects, selectedDefinition.default_project_id)
    : null;

  const candidateScenarios = useMemo(
    () => deriveCandidateScenarios(selectedDefinition, runnableScenarios),
    [runnableScenarios, selectedDefinition]
  );

  const plannedScenarios = useMemo(
    () =>
      buildPlannedScenarioRows(
        selectedDefinition,
        candidateScenarios,
        selectedScenarioIds,
        runDurationMinutes
      ),
    [candidateScenarios, runDurationMinutes, selectedDefinition, selectedScenarioIds]
  );

  const availableCustomScenarios = useMemo(
    () =>
      candidateScenarios.filter((scenario) => !selectedScenarioIds.includes(scenario.scenario_id)),
    [candidateScenarios, selectedScenarioIds]
  );

  const selectedDefinitionTasks = useMemo(
    () =>
      tasks.filter(
        (task) =>
          (!selectedDefinition ||
            task.benchmark_definition_id === selectedDefinition.benchmark_definition_id) &&
          (!selectedProject || task.project_id === selectedProject.project_id)
      ),
    [selectedDefinition, selectedProject, tasks]
  );

  useEffect(() => {
    if (!selectedDefinition && definitions[0]) {
      setWorkflowSelection({ benchmarkDefinitionId: definitions[0].benchmark_definition_id });
    }
  }, [definitions, selectedDefinition]);

  useEffect(() => {
    if (selectedProject && selectedProject.project_id !== workflow.projectId) {
      setWorkflowSelection({ projectId: selectedProject.project_id });
    }
  }, [selectedProject?.project_id, workflow.projectId]);

  useEffect(() => {
    if (!selectedDefinition) {
      setSelectedScenarioIds([]);
      return;
    }

    const candidateIds = candidateScenarios.map((item) => item.scenario_id);

    if (selectedDefinition.planning_mode === 'all_runnable') {
      setSelectedScenarioIds(candidateIds);
      setWorkflowSelection({ scenarioId: candidateIds[0] ?? null });
      return;
    }

    if (
      selectedDefinition.planning_mode === 'single_scenario' ||
      selectedDefinition.planning_mode === 'timed_single_scenario'
    ) {
      const fallbackScenarioId = candidateIds[0] ?? '';
      const nextScenarioId = candidateIds.includes(selectedScenarioIds[0] ?? '')
        ? selectedScenarioIds[0]
        : fallbackScenarioId;
      setSelectedScenarioIds(nextScenarioId ? [nextScenarioId] : []);
      setWorkflowSelection({ scenarioId: nextScenarioId || null });
      return;
    }

    setSelectedScenarioIds((current) => current.filter((scenarioId) => candidateIds.includes(scenarioId)));
  }, [candidateScenarios, selectedDefinition]);

  useEffect(() => {
    if (selectedDefinition?.planning_mode === 'custom_multi_scenario') {
      setWorkflowSelection({ scenarioId: selectedScenarioIds[0] ?? null });
    }
  }, [selectedDefinition?.planning_mode, selectedScenarioIds]);

  useEffect(() => {
    if (selectedDefinition?.planning_mode !== 'custom_multi_scenario') {
      setScenarioDrawerOpen(false);
    }
  }, [selectedDefinition?.planning_mode]);

  useEffect(() => {
    if (!selectedDefinition?.supports_duration_seconds) {
      return;
    }
    const nextMinutes = Math.max(
      1,
      Math.round((selectedDefinition.default_duration_seconds ?? 1800) / 60)
    );
    setRunDurationMinutes(`${nextMinutes}`);
  }, [selectedDefinition?.benchmark_definition_id]);

  useEffect(() => {
    if (!selectedDefinition) {
      return;
    }
    setEvaluationProfileName(
      selectedDefinition.default_evaluation_profile_name ?? evaluationProfiles[0]?.profile_name ?? ''
    );
  }, [evaluationProfiles, selectedDefinition?.benchmark_definition_id]);

  useEffect(() => {
    if (!scenarioDrawerOpen) {
      return;
    }
    setPendingScenarioId(availableCustomScenarios[0]?.scenario_id ?? null);
  }, [availableCustomScenarios, scenarioDrawerOpen]);

  const createTaskMutation = useMutation({
    mutationFn: async (autoStart: boolean) => {
      if (!selectedDefinition) {
        throw new Error('请先选择基准模板');
      }
      if (!selectedProject) {
        throw new Error('当前模板没有默认归档项目');
      }
      if (plannedScenarios.length === 0) {
        throw new Error(
          selectedDefinition.planning_mode === 'custom_multi_scenario'
            ? '请先增加至少 1 个场景测试'
            : '当前模板还没有形成可执行测试场景'
        );
      }

      return createBenchmarkTask({
        benchmark_definition_id: selectedDefinition.benchmark_definition_id,
        dut_model: dutModel.trim() || undefined,
        selected_scenario_ids:
          selectedDefinition.planning_mode === 'all_runnable'
            ? undefined
            : plannedScenarios.map((item) => item.scenario_id),
        run_duration_seconds: selectedDefinition.supports_duration_seconds
          ? plannedScenarios[0]?.timeout_seconds
          : undefined,
        hil_config: selectedGatewayId
          ? {
              mode: 'camera_open_loop',
              gateway_id: selectedGatewayId,
              video_source: 'hdmi_x1301',
              dut_input_mode: 'uvc_camera',
              result_ingest_mode: 'http_push'
            }
          : undefined,
        evaluation_profile_name: evaluationProfileName || undefined,
        auto_start: autoStart
      });
    },
    onSuccess: (task, autoStart) => {
      setScenarioDrawerOpen(false);
      void queryClient.invalidateQueries({ queryKey: ['benchmark-tasks'] });
      void queryClient.invalidateQueries({ queryKey: ['runs'] });
      setWorkflowSelection({
        runId: null,
        scenarioId: plannedScenarios[0]?.scenario_id ?? null
      });

      if (autoStart) {
        navigate(`/executions?task=${task.benchmark_task_id}`);
      }
    }
  });

  function removeCustomScenario(scenarioId: string) {
    setSelectedScenarioIds((current) => current.filter((item) => item !== scenarioId));
  }

  function addPendingScenario() {
    if (!pendingScenarioId) {
      return;
    }
    setSelectedScenarioIds((current) => Array.from(new Set([...current, pendingScenarioId])));
    setScenarioDrawerOpen(false);
  }

  function renderCurrentScenarioList(options: {
    allowRemove: boolean;
    emptyTitle: string;
    emptyDescription: string;
  }) {
    if (plannedScenarios.length === 0) {
      return (
        <EmptyState description={options.emptyDescription} title={options.emptyTitle} />
      );
    }

    return (
      <div className="project-console__queue-list">
        {plannedScenarios.map((scenario) => (
          <div
            className="project-console__queue-item"
            key={`${scenario.scenario_id}-${scenario.timeout_seconds}`}
          >
            <div className="project-console__queue-copy">
              <strong>{scenario.display_name}</strong>
              <small>
                {scenario.execution_backend} / {scenario.map_name} /{' '}
                {formatDurationLabel(scenario.timeout_seconds)}
              </small>
            </div>

            {options.allowRemove && (
              <button
                className="project-console__queue-remove"
                onClick={() => removeCustomScenario(scenario.scenario_id)}
                type="button"
              >
                移除
              </button>
            )}
          </div>
        ))}
      </div>
    );
  }

  function renderPlannerContent() {
    if (!selectedDefinition) {
      return (
        <Panel
          bodyClassName="flex min-h-[260px] items-center"
          eyebrow="场景编排"
          subtitle="先确定评测模板，再把要执行的场景加入当前任务。"
          title="尚未选择基准模板"
        >
          <EmptyState
            description="先在上方模板入口选择一个基准模板，页面才会展开对应的场景编排规则。"
            title="还不能开始编排"
          />
        </Panel>
      );
    }

    return (
      <Panel
        eyebrow="场景编排"
        subtitle={selectedDefinition.queue_note ?? planningModeHint(selectedDefinition.planning_mode)}
        title={selectedDefinition.name}
        actions={
          <div className="project-console__toggle">
            <span className="project-console__toggle-item project-console__toggle-item--active">
              {planningModeLabel(selectedDefinition.planning_mode)}
            </span>
          </div>
        }
      >
        {selectedDefinition.planning_mode === 'custom_multi_scenario' && (
          <div className="project-console__planner-stack">
            <div className="project-console__queue-toolbar">
              <div className="project-console__picker-copy">
                <strong>增加场景测试</strong>
                <p>点击右侧加号，从场景目录里逐个加入当前测试任务。</p>
              </div>

              <div className="project-console__picker-actions">
                <button
                  className="project-console__picker-button"
                  onClick={() => setScenarioDrawerOpen(true)}
                  type="button"
                >
                  + 增加场景测试
                </button>
              </div>
            </div>

            {renderCurrentScenarioList({
              allowRemove: true,
              emptyTitle: '还没有加入测试场景',
              emptyDescription: '点击上方加号，从场景目录里选择要加入的测试场景。'
            })}
          </div>
        )}

        {selectedDefinition.planning_mode === 'single_scenario' && (
          <div className="project-console__planner-stack">
            <div className="project-console__picker-copy">
              <strong>增加场景测试</strong>
              <p>当前模板一次只运行 1 个场景，选择后会直接显示在下方。</p>
            </div>

            <div className="project-console__form-stack">
              <label className="field">
                <span>选择运行场景</span>
                <select
                  onChange={(event) => {
                    const value = event.target.value;
                    setSelectedScenarioIds(value ? [value] : []);
                    setWorkflowSelection({ scenarioId: value || null });
                  }}
                  value={selectedScenarioIds[0] ?? ''}
                >
                  <option value="">请选择场景</option>
                  {candidateScenarios.map((scenario) => (
                    <option key={scenario.scenario_id} value={scenario.scenario_id}>
                      {scenario.display_name}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {renderCurrentScenarioList({
              allowRemove: false,
              emptyTitle: '尚未选择场景',
              emptyDescription: '从上方下拉列表选择 1 个场景作为本次基线评测输入。'
            })}
          </div>
        )}

        {selectedDefinition.planning_mode === 'timed_single_scenario' && (
          <div className="project-console__planner-stack">
            <div className="project-console__picker-copy">
              <strong>增加场景测试</strong>
              <p>选择 1 个高负载场景，并指定这一轮仿真的持续时长。</p>
            </div>

            <div className="project-console__inline-form project-console__inline-form--compact">
              <label className="field project-console__inline-field">
                <span>选择运行场景</span>
                <select
                  onChange={(event) => {
                    const value = event.target.value;
                    setSelectedScenarioIds(value ? [value] : []);
                    setWorkflowSelection({ scenarioId: value || null });
                  }}
                  value={selectedScenarioIds[0] ?? ''}
                >
                  <option value="">请选择场景</option>
                  {candidateScenarios.map((scenario) => (
                    <option key={scenario.scenario_id} value={scenario.scenario_id}>
                      {scenario.display_name}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field project-console__inline-field">
                <span>运行时长（分钟）</span>
                <input
                  min={1}
                  onChange={(event) => setRunDurationMinutes(event.target.value)}
                  type="number"
                  value={runDurationMinutes}
                />
              </label>
            </div>

            {renderCurrentScenarioList({
              allowRemove: false,
              emptyTitle: '尚未选择场景',
              emptyDescription: '先选择一个高负载场景，页面会直接显示当前这轮长稳测试输入。'
            })}
          </div>
        )}

        {selectedDefinition.planning_mode === 'all_runnable' && (
          <div className="project-console__planner-stack">
            <div className="project-console__summary-stack">
              <p>这个模板会自动把当前全部可执行场景各跑一遍，不需要手动增加场景。</p>
              <small>如果后续要裁剪覆盖范围，再调整模板的候选场景集合。</small>
            </div>

            {renderCurrentScenarioList({
              allowRemove: false,
              emptyTitle: '没有可执行场景',
              emptyDescription: '当前环境里没有可用于回归的场景。'
            })}
          </div>
        )}

        <div className="project-console__actions">
          <button
            className="horizon-button-secondary"
            disabled={
              createTaskMutation.isPending || !selectedProject || plannedScenarios.length === 0
            }
            onClick={() => createTaskMutation.mutate(false)}
            type="button"
          >
            仅创建任务
          </button>
          <button
            className="horizon-button"
            disabled={
              createTaskMutation.isPending || !selectedProject || plannedScenarios.length === 0
            }
            onClick={() => createTaskMutation.mutate(true)}
            type="button"
          >
            创建并立即执行
          </button>
        </div>

        {createTaskMutation.isError && (
          <div className="project-console__feedback project-console__feedback--error">
            {createTaskMutation.error instanceof Error
              ? createTaskMutation.error.message
              : '任务创建失败'}
          </div>
        )}

        {!selectedProject && selectedDefinition && (
          <div className="project-console__feedback project-console__feedback--error">
            当前模板没有配置默认归档项目，暂时无法创建任务。
          </div>
        )}

        {createTaskMutation.isSuccess && (
          <div className="project-console__feedback">
            已生成批量任务，当前模板对应的 run 队列已经写入后端。
          </div>
        )}
      </Panel>
    );
  }

  return (
    <div className="page-stack project-console">
      <PageHeader
        title="基准任务台 / 模板编排"
        eyebrow="基准模板 / 批量任务"
        chips={['模板入口', '场景编排', '任务归档']}
        description="先选基准模板，再按模板规则把场景加入当前测试。项目只作为后台归档字段，不再在这里手动选择。"
        actions={
          <>
            <Link className="horizon-button-secondary" to="/projects" viewTransition>
              返回项目页
            </Link>
            <Link className="horizon-button" to="/executions" viewTransition>
              打开执行台
            </Link>
          </>
        }
      />

      <div className="project-console__status-bar">
        <span className="project-console__status-pill">
          模板 {selectedDefinition?.name ?? '未选择'}
        </span>
        <span className="project-console__status-pill">
          候选场景 {candidateScenarios.length}
        </span>
        <span className={`project-console__status-pill${plannedScenarios.length > 0 ? ' project-console__status-pill--online' : ''}`}>
          已选 {plannedScenarios.length}
        </span>
        <span className="project-console__status-pill">
          归档 {selectedProject?.name ?? '等待关联'}
        </span>
      </div>

      <div className="project-console__section-stack">
          <Panel
            eyebrow="模板入口"
            subtitle="模板决定归档项目、候选场景范围、协议和默认编排方式。"
            title="基准模板"
          >
            {definitionsQuery.isLoading ? (
              <EmptyState description="正在同步模板目录。" title="模板加载中" />
            ) : definitionsQuery.isError ? (
              <EmptyState
                description={
                  definitionsQuery.error instanceof Error
                    ? definitionsQuery.error.message
                    : '模板接口异常。'
                }
                title="模板加载失败"
              />
            ) : definitions.length === 0 ? (
              <EmptyState
                description="当前环境没有可用基准模板。先回到后端补齐模板目录，再回来继续编排。"
                title="没有可用模板"
              />
            ) : (
              <div className="project-console__definition-grid">
                {definitions.map((definition) => {
                  const active =
                    selectedDefinition?.benchmark_definition_id ===
                    definition.benchmark_definition_id;
                  const archiveProject = definition.default_project_id
                    ? findProjectRecord(projects, definition.default_project_id)
                    : null;

                  return (
                    <button
                      key={definition.benchmark_definition_id}
                      className={
                        active
                          ? 'project-console__definition-card project-console__definition-card--active'
                          : 'project-console__definition-card'
                      }
                      onClick={() =>
                        setWorkflowSelection({
                          benchmarkDefinitionId: definition.benchmark_definition_id
                        })
                      }
                      type="button"
                    >
                      <span className="project-console__section-label">
                        {planningModeLabel(definition.planning_mode)}
                      </span>
                      <strong>{definition.name}</strong>
                      <p>{definition.description}</p>
                      <small>
                        自动归档到 {archiveProject?.name ?? '未配置项目'}。
                        {definition.queue_note ?? planningModeHint(definition.planning_mode)}
                      </small>
                    </button>
                  );
                })}
              </div>
            )}
          </Panel>

          {renderPlannerContent()}

          <Panel
            eyebrow="任务附加项"
            subtitle="这些字段会统一写入这次批量任务的所有运行实例。"
            title="统一附加配置"
          >
            <div className="grid gap-4 xl:grid-cols-3">
              <label className="field project-console__inline-field">
                <span>待测端型号</span>
                <input
                  onChange={(event) => setDutModel(event.target.value)}
                  placeholder="例如 域控制器样机 / 车载算力平台"
                  value={dutModel}
                />
                <small className="text-xs text-text-muted">
                  待测端型号只写入本次任务实例，不会影响项目或模板的默认信息。
                </small>
              </label>

              <label className="field project-console__inline-field">
                <span>评测协议</span>
                <select
                  onChange={(event) => setEvaluationProfileName(event.target.value)}
                  value={evaluationProfileName}
                >
                  <option value="">不绑定</option>
                  {evaluationProfiles.map((profile) => (
                    <option key={profile.profile_name} value={profile.profile_name}>
                      {profile.display_name}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field project-console__inline-field">
                <span>绑定设备</span>
                <select
                  onChange={(event) => {
                    setSelectedGatewayId(event.target.value);
                    setWorkflowSelection({ gatewayId: event.target.value || null });
                  }}
                  value={selectedGatewayId}
                >
                  <option value="">不绑定网关</option>
                  {gateways.map((gateway) => (
                    <option key={gateway.gateway_id} value={gateway.gateway_id}>
                      {gateway.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </Panel>

          <Panel eyebrow="任务历史" subtitle="这里展示当前模板最近生成的批量任务。" title="最近批量任务">
            {tasksQuery.isLoading ? (
              <EmptyState description="正在同步批量任务记录。" title="任务加载中" />
            ) : tasksQuery.isError ? (
              <EmptyState
                description={
                  tasksQuery.error instanceof Error
                    ? tasksQuery.error.message
                    : '任务接口异常。'
                }
                title="任务加载失败"
              />
            ) : selectedDefinitionTasks.length === 0 ? (
              <EmptyState
                description="创建任务后，最近记录会出现在这里，方便回看是否已经归档到正确项目。"
                title="暂无批量任务"
              />
            ) : (
              <div className="project-console__table">
                {selectedDefinitionTasks.slice(0, 8).map((task) => (
                  <div className="project-console__table-row" key={task.benchmark_task_id}>
                    <div>
                      <span>{task.benchmark_name}</span>
                      <strong>{task.project_name}</strong>
                    </div>
                    <StatusPill canonical status={task.status} />
                    <small>
                      {task.planned_run_count} runs / {formatDateTime(task.updated_at_utc)}
                    </small>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>

      {scenarioDrawerOpen && selectedDefinition?.planning_mode === 'custom_multi_scenario' && (
        <button
          aria-label="关闭场景选择抽屉"
          className="project-console__drawer-backdrop"
          onClick={() => setScenarioDrawerOpen(false)}
          type="button"
        />
      )}

      {selectedDefinition?.planning_mode === 'custom_multi_scenario' && (
        <aside
          aria-hidden={!scenarioDrawerOpen}
          className={
            scenarioDrawerOpen
              ? 'project-console__drawer project-console__drawer--open'
              : 'project-console__drawer'
          }
        >
            <header className="project-console__drawer-header">
              <div>
                <span className="project-console__section-label">增加场景测试</span>
                <strong>场景目录</strong>
              </div>
              <button
                className="project-console__drawer-close"
                onClick={() => setScenarioDrawerOpen(false)}
                type="button"
              >
                关闭
              </button>
            </header>

            <div className="project-console__drawer-copy">
              <p>从目录里逐个选择场景加入当前测试，不再使用复选框勾选。</p>
            </div>

            {availableCustomScenarios.length === 0 ? (
              <EmptyState description="候选场景已经全部加入当前测试。" title="没有可加入场景" />
            ) : (
              <SelectionList
                emptyDescription="当前模板没有可加入场景。"
                emptyTitle="场景为空"
                expandLabel="展开目录"
                items={availableCustomScenarios.map((scenario) => ({
                  id: scenario.scenario_id,
                  title: scenario.display_name,
                  subtitle: scenario.description,
                  meta: `${scenario.execution_backend ?? scenario.execution_support} / ${scenario.default_map_name}`,
                  status: 'READY',
                  hint: scenario.scenario_id
                }))}
                maxVisible={8}
                onSelect={(id) => setPendingScenarioId(id)}
                selectedId={pendingScenarioId}
              />
            )}

            <div className="project-console__actions">
              <button
                className="horizon-button-secondary"
                onClick={() => setScenarioDrawerOpen(false)}
                type="button"
              >
                取消
              </button>
              <button
                className="horizon-button"
                disabled={!pendingScenarioId}
                onClick={addPendingScenario}
                type="button"
              >
                加入当前场景
              </button>
            </div>
        </aside>
      )}
      <WorkflowNextStep />
    </div>
  );
}
