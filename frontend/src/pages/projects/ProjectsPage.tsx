import { useMemo, useState } from 'react';

import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { getDevicesWorkspace } from '../../api/devices';
import { getProjectWorkspace, listProjects } from '../../api/projects';
import { getReportsWorkspace, listReports } from '../../api/reports';
import { getSystemStatus } from '../../api/system';
import { DonutStatusChart } from '../../components/common/DonutStatusChart';
import { EmptyState } from '../../components/common/EmptyState';
import { MetricCard } from '../../components/common/MetricCard';
import { PageHeader } from '../../components/common/PageHeader';
import { Panel } from '../../components/common/Panel';
import { SelectionList } from '../../components/common/SelectionList';
import { StatusPill } from '../../components/common/StatusPill';
import { setWorkflowSelection, useWorkflowSelection } from '../../features/workflow/state';
import { formatDateTime, sortByActivity, truncateMiddle } from '../../lib/format';
import { findProjectRecord } from '../../lib/platform';

type ProjectViewMode = 'overview' | 'reports' | 'runtime';
type PlatformIncident = {
  id: string;
  type: string;
  status: string;
  message: string;
  to: string;
  updated_at_utc?: string | null;
  created_at_utc?: string | null;
};

function planningModeLabel(mode: string) {
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

function canArchiveReport(status: string) {
  return ['COMPLETED', 'PARTIAL_FAILED', 'FAILED', 'CANCELED'].includes(status);
}

function isActiveTask(status: string) {
  return ['CREATED', 'RUNNING'].includes(status);
}

function chartColorForStatus(status: string) {
  if (status === 'COMPLETED' || status === 'READY') {
    return '#22c55e';
  }
  if (status === 'DEGRADED' || status === 'QUEUED' || status === 'STARTING' || status === 'RUNNING' || status === 'STOPPING' || status === 'BUSY') {
    return '#f59e0b';
  }
  if (status === 'FAILED' || status === 'ERROR' || status === 'CANCELED' || status === 'OFFLINE') {
    return '#ef4444';
  }
  return '#64748b';
}

function normalizeApiStatus(status: string | null | undefined) {
  if (!status) {
    return '未知';
  }
  if (status.toLowerCase() === 'ok') {
    return '在线';
  }
  return status;
}

function normalizeRuntimeStatus(status: string | null | undefined) {
  if (!status) {
    return '未知';
  }

  const labelMap: Record<string, string> = {
    READY: '就绪',
    RUNNING: '运行中',
    COMPLETED: '已完成',
    FAILED: '失败',
    DEGRADED: '降级',
    UNKNOWN: '未知',
    CREATED: '已创建',
    QUEUED: '排队中',
    STARTING: '启动中',
    STOPPING: '停止中',
    PAUSED: '已暂停',
    CANCELED: '已取消',
    STOPPED: '已停止',
    ERROR: '错误',
    BUSY: '忙碌',
    OFFLINE: '离线'
  };

  return labelMap[status] ?? status;
}

function gatewaySummaryLabel(gateway: { metrics: Record<string, unknown>; address: string | null }) {
  return String(gateway.metrics.capture_resolution ?? gateway.address ?? '-');
}

export function ProjectsPage() {
  const workflow = useWorkflowSelection();
  const [viewMode, setViewMode] = useState<ProjectViewMode>('overview');

  const projectsQuery = useQuery({ queryKey: ['projects'], queryFn: listProjects });
  const systemQuery = useQuery({
    queryKey: ['system-status'],
    queryFn: getSystemStatus,
    refetchInterval: 3000
  });
  const devicesWorkspaceQuery = useQuery({
    queryKey: ['devices', 'workspace'],
    queryFn: getDevicesWorkspace,
    refetchInterval: 5000
  });
  const reportsWorkspaceQuery = useQuery({
    queryKey: ['reports', 'workspace'],
    queryFn: getReportsWorkspace,
    refetchInterval: 5000
  });

  const projects = projectsQuery.data ?? [];
  const selectedProject = workflow.projectId ? findProjectRecord(projects, workflow.projectId) : null;

  const workspaceQuery = useQuery({
    queryKey: ['projects', workflow.projectId, 'workspace'],
    queryFn: () => getProjectWorkspace(workflow.projectId ?? ''),
    enabled: Boolean(workflow.projectId)
  });
  const reportsQuery = useQuery({
    queryKey: ['reports', workflow.projectId],
    queryFn: () => listReports({ projectId: workflow.projectId ?? '' }),
    enabled: Boolean(workflow.projectId),
    refetchInterval: 5000
  });

  const workspace = workspaceQuery.data;
  const reports = reportsQuery.data ?? [];
  const devicesWorkspace = devicesWorkspaceQuery.data;
  const reportsWorkspace = reportsWorkspaceQuery.data;
  const reportedTaskIds = useMemo(
    () => new Set(reports.map((report) => report.benchmark_task_id)),
    [reports]
  );
  const platformGateways = useMemo(
    () => sortByActivity(devicesWorkspace?.gateways ?? []),
    [devicesWorkspace?.gateways]
  );
  const platformCaptures = useMemo(
    () => sortByActivity(devicesWorkspace?.captures ?? []),
    [devicesWorkspace?.captures]
  );

  const latestReport = reports[0] ?? null;
  const latestTask = workspace?.benchmark_tasks[0] ?? null;
  const latestRun = workspace?.recent_runs[0] ?? null;
  const latestPlatformCapture = platformCaptures[0] ?? null;
  const latestPlatformGateway = platformGateways[0] ?? null;
  const activeTaskCount = workspace?.benchmark_tasks.filter((task) => isActiveTask(task.status)).length ?? 0;
  const archivableTaskCount =
    workspace?.benchmark_tasks.filter((task) => canArchiveReport(task.status)).length ?? 0;
  const pendingReportTasks =
    workspace?.benchmark_tasks.filter(
      (task) => canArchiveReport(task.status) && !reportedTaskIds.has(task.benchmark_task_id)
    ) ?? [];
  const recentIncidents = useMemo<PlatformIncident[]>(() => {
    const runIncidents = (reportsWorkspace?.recent_failures ?? []).map((run) => ({
      id: run.run_id,
      type: '执行',
      status: run.status,
      message: run.error_reason ?? run.scenario_name,
      to: `/executions/${run.run_id}`,
      updated_at_utc: run.updated_at_utc,
      created_at_utc: run.created_at_utc
    }));
    const captureIncidents = platformCaptures
      .filter((capture) => capture.status === 'FAILED')
      .map((capture) => ({
        id: capture.capture_id,
        type: '采集',
        status: capture.status,
        message: capture.error_reason ?? capture.gateway_id,
        to: `/devices/${capture.gateway_id}`,
        updated_at_utc: capture.updated_at_utc,
        created_at_utc: capture.created_at_utc
      }));
    const gatewayIncidents = platformGateways
      .filter(
        (gateway) =>
          ['FAILED', 'ERROR', 'OFFLINE'].includes(gateway.status) || Boolean(gateway.metrics.last_error)
      )
      .map((gateway) => ({
        id: gateway.gateway_id,
        type: '网关',
        status: gateway.status,
        message: String(gateway.metrics.last_error ?? gateway.address ?? '设备状态异常'),
        to: `/devices/${gateway.gateway_id}`,
        updated_at_utc: gateway.updated_at_utc,
        created_at_utc: gateway.created_at_utc
      }));

    return sortByActivity([...runIncidents, ...captureIncidents, ...gatewayIncidents]).slice(0, 6);
  }, [platformCaptures, platformGateways, reportsWorkspace?.recent_failures]);
  const executorHealthStatus = !systemQuery.data
    ? 'UNKNOWN'
    : systemQuery.data.executor.alive
      ? 'READY'
      : systemQuery.data.executor.pending_commands > 0
        ? 'DEGRADED'
        : 'OFFLINE';
  const platformApiStatus = normalizeApiStatus(systemQuery.data?.api.status);

  return (
    <div className="page-stack project-console">
      <PageHeader
        title="项目台 / 归档与运行总览"
        eyebrow="项目 / 归档与运行态"
        chips={['平台健康', '项目归档', '运行态']}
        description="集中查看平台健康、异常入口、项目归档结果与近期运行状态。"
        actions={
          <>
            <Link className="horizon-button-secondary" to="/reports" viewTransition>
              打开报告中心
            </Link>
            <Link className="horizon-button" to="/benchmarks" viewTransition>
              去创建基准任务
            </Link>
          </>
        }
      />

      <div className="project-console__section-stack">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <MetricCard accent="blue" label="平台健康" value={platformApiStatus} hint="系统状态监测" />
            <MetricCard
              accent="violet"
              label="执行队列"
              value={systemQuery.data?.executor.pending_commands ?? 0}
              hint={
                systemQuery.data
                  ? systemQuery.data.executor.alive
                    ? '执行器在线'
                    : '执行器不在线'
                  : '等待执行器状态'
              }
            />
            <MetricCard
              accent="teal"
              label="在线设备"
              value={devicesWorkspace?.summary.online_device_count ?? 0}
              hint={`总计 ${systemQuery.data?.totals.gateways ?? 0} 个网关`}
            />
            <MetricCard
              accent="orange"
              label="运行中采集"
              value={
                devicesWorkspace?.summary.running_capture_count ??
                systemQuery.data?.capture_observability.running_capture_ids.length ??
                0
              }
              hint={latestPlatformCapture ? latestPlatformCapture.capture_id : '暂无采集'}
            />
            <MetricCard
              accent="rose"
              label="最近异常"
              value={recentIncidents.length}
              hint={recentIncidents[0]?.message ?? '当前无高优先级异常'}
            />
          </div>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_360px]">
          <Panel
            eyebrow="平台总览"
            subtitle="汇总平台健康、资源入口和异常排查线索。"
            title="全局状态概览"
            actions={
              <div className="flex flex-wrap gap-3">
                  <Link className="horizon-button-secondary" to="/devices" viewTransition>
                    查看设备中心
                  </Link>
                  <Link className="horizon-button-secondary" to="/executions" viewTransition>
                    查看执行中心
                  </Link>
              </div>
            }
          >
            <div className="flex flex-col gap-4">
              <div className="rounded-[24px] border border-border-glass bg-[var(--surface-glass)] px-5 py-5">
                <div className="flex flex-wrap items-center gap-3">
                  <StatusPill canonical status={executorHealthStatus} />
                  <span className="project-console__chip">API {platformApiStatus}</span>
                  <span className="project-console__chip project-console__chip--muted">
                    Pi 网关 {normalizeRuntimeStatus(systemQuery.data?.pi_gateway.status)}
                  </span>
                </div>
                <strong className="mt-4 block text-2xl font-extrabold tracking-[-0.04em] text-text">
                  平台健康、资源入口与异常线索集中呈现
                </strong>
                <p className="mt-2 text-sm leading-6 text-text-muted">
                  当前队列 {systemQuery.data?.executor.pending_commands ?? 0} 条命令，最近采集{' '}
                  {systemQuery.data?.capture_observability.latest_capture_id ?? '-'}，Pi 网关状态{' '}
                  {normalizeRuntimeStatus(systemQuery.data?.pi_gateway.status)}。
                </p>
                {systemQuery.data?.executor.warning ? (
                  <p className="mt-3 text-sm text-amber-300">{systemQuery.data.executor.warning}</p>
                ) : null}
              </div>

              <div className="grid gap-3 md:grid-cols-3">
                <Link
                  className="rounded-[18px] border border-border-glass bg-[var(--surface-glass)] px-4 py-4 transition hover:-translate-y-0.5 hover:border-[rgba(var(--accent-rgb),0.32)]"
                  to={latestPlatformCapture ? `/devices/${latestPlatformCapture.gateway_id}` : '/devices'}
                  viewTransition
                >
                  <span className="block text-xs font-extrabold uppercase tracking-[0.16em] text-text-muted">
                    最近采集
                  </span>
                  <strong className="mt-2 block text-sm text-text">
                    {latestPlatformCapture?.capture_id ?? '暂无采集任务'}
                  </strong>
                  <small className="mt-2 block text-text-muted">
                    {latestPlatformCapture
                      ? `${latestPlatformCapture.saved_frames} 帧 / ${latestPlatformCapture.gateway_id}`
                      : '设备中心会显示新的采集链路。'}
                  </small>
                </Link>

                <Link
                  className="rounded-[18px] border border-border-glass bg-[var(--surface-glass)] px-4 py-4 transition hover:-translate-y-0.5 hover:border-[rgba(var(--accent-rgb),0.32)]"
                  to={latestPlatformGateway ? `/devices/${latestPlatformGateway.gateway_id}` : '/devices'}
                  viewTransition
                >
                  <span className="block text-xs font-extrabold uppercase tracking-[0.16em] text-text-muted">
                    最近网关
                  </span>
                  <strong className="mt-2 block text-sm text-text">
                    {latestPlatformGateway?.name ?? '暂无设备'}
                  </strong>
                  <small className="mt-2 block text-text-muted">
                    {latestPlatformGateway
                      ? gatewaySummaryLabel(latestPlatformGateway)
                      : '等待网关心跳与链路遥测。'}
                  </small>
                </Link>

                <Link
                  className="rounded-[18px] border border-border-glass bg-[var(--surface-glass)] px-4 py-4 transition hover:-translate-y-0.5 hover:border-[rgba(var(--accent-rgb),0.32)]"
                  to="/executions"
                  viewTransition
                >
                  <span className="block text-xs font-extrabold uppercase tracking-[0.16em] text-text-muted">
                    执行器队列
                  </span>
                  <strong className="mt-2 block text-sm text-text">
                    {systemQuery.data?.executor.active_run_id
                      ? truncateMiddle(systemQuery.data.executor.active_run_id, 8)
                      : '当前没有活动执行'}
                  </strong>
                  <small className="mt-2 block text-text-muted">
                    最后命令 {systemQuery.data?.executor.last_command_run_id ?? '-'}
                  </small>
                </Link>
              </div>
            </div>
          </Panel>

          <Panel eyebrow="最近异常" subtitle="按运行、采集和网关统一排序最近异常。" title="优先排查队列">
            {recentIncidents.length === 0 ? (
              <EmptyState
                description="当前没有近期失败、离线或错误状态。后续有异常时，这里会直接给出去执行台或设备台的入口。"
                title="异常为空"
              />
            ) : (
              <div className="project-console__table">
                {recentIncidents.map((incident) => (
                  <Link className="project-console__table-row" key={`${incident.type}-${incident.id}`} to={incident.to} viewTransition>
                    <div>
                      <span>{incident.type}</span>
                      <strong>{truncateMiddle(incident.id, 10)}</strong>
                      <small>{incident.message}</small>
                    </div>
                    <small>{formatDateTime(incident.updated_at_utc ?? incident.created_at_utc ?? null)}</small>
                    <StatusPill status={incident.status} />
                  </Link>
                ))}
              </div>
            )}
          </Panel>
        </div>

        {systemQuery.data ? (
          <div className="grid gap-5 xl:grid-cols-3">
            <Panel className="h-full">
                <DonutStatusChart
                  title="运行状态分布"
                  subtitle="查看调度是否集中在运行态或排队态。"
                  items={Object.entries(systemQuery.data.counts.runs)
                    .filter(([, value]) => value > 0)
                    .map(([label, value]) => ({
                      label,
                      value,
                      color: chartColorForStatus(label)
                    }))}
                />
            </Panel>

            <Panel className="h-full">
                <DonutStatusChart
                  title="采集状态分布"
                  subtitle="直接确认采集链路是否稳定落盘。"
                  items={Object.entries(systemQuery.data.counts.captures)
                    .filter(([, value]) => value > 0)
                    .map(([label, value]) => ({
                      label,
                      value,
                      color: chartColorForStatus(label)
                    }))}
                />
            </Panel>

            <Panel className="h-full">
                <DonutStatusChart
                  title="网关状态分布"
                  subtitle="关注就绪、忙碌、降级和离线状态的变化。"
                  items={Object.entries(systemQuery.data.counts.gateways)
                    .filter(([, value]) => value > 0)
                    .map(([label, value]) => ({
                      label,
                      value,
                      color: chartColorForStatus(label)
                    }))}
                />
            </Panel>
          </div>
        ) : (
          <Panel>
            <EmptyState
              description={systemQuery.error instanceof Error ? systemQuery.error.message : '系统状态接口暂时不可用。'}
              title="全局状态概览不可用"
            />
          </Panel>
        )}
      </div>

      <div className="project-console__layout">
        <aside className="project-console__rail">
          <Panel eyebrow="项目入口" subtitle="选择项目后查看归档结果、运行状态和下一步操作入口。" title="项目列表">
            {projectsQuery.isLoading ? (
              <EmptyState description="正在同步项目目录。" title="项目加载中" />
            ) : projectsQuery.isError ? (
              <EmptyState
                description={
                  projectsQuery.error instanceof Error ? projectsQuery.error.message : '项目接口异常。'
                }
                title="项目加载失败"
              />
            ) : (
              <SelectionList
                emptyDescription="后端暂未返回项目记录。"
                emptyTitle="没有项目"
                expandLabel="展开项目"
                maxVisible={6}
                items={projects.map((project) => ({
                  id: project.project_id,
                  title: project.name,
                  subtitle: project.description,
                  meta: `${project.vendor} / ${project.processor}`,
                  status: project.status,
                  hint: project.project_id
                }))}
                onSelect={(id) =>
                  setWorkflowSelection({
                    projectId: id,
                    benchmarkDefinitionId: null,
                    scenarioId: null
                  })
                }
                selectedId={selectedProject?.project_id ?? null}
              />
            )}
          </Panel>
        </aside>

        <div className="project-console__main">
          {!selectedProject ? (
            <Panel bodyClassName="flex min-h-[320px] items-center">
              <EmptyState description="先从左侧选择一个项目，再查看该项目的归档结果和运行态。" title="未选择项目" />
            </Panel>
          ) : workspaceQuery.isLoading ? (
            <Panel bodyClassName="flex min-h-[320px] items-center">
              <EmptyState description="正在加载项目数据。" title="项目加载中" />
            </Panel>
          ) : workspaceQuery.isError || !workspace ? (
            <Panel bodyClassName="flex min-h-[320px] items-center">
              <EmptyState
                description={
                  workspaceQuery.error instanceof Error ? workspaceQuery.error.message : '项目接口异常。'
                }
                title="项目加载失败"
              />
            </Panel>
          ) : (
            <Panel
              eyebrow="项目只读结果"
              subtitle="聚合当前项目的归档报告、适用模板摘要和运行状态。"
              title={workspace.project.name}
              actions={
                <div className="project-console__toggle">
                    <button
                      className={
                        viewMode === 'overview'
                          ? 'project-console__toggle-item project-console__toggle-item--active'
                          : 'project-console__toggle-item'
                      }
                      onClick={() => setViewMode('overview')}
                      type="button"
                    >
                      总览
                    </button>
                    <button
                      className={
                        viewMode === 'reports'
                          ? 'project-console__toggle-item project-console__toggle-item--active'
                          : 'project-console__toggle-item'
                      }
                      onClick={() => setViewMode('reports')}
                      type="button"
                    >
                      报告归档
                    </button>
                    <button
                      className={
                        viewMode === 'runtime'
                          ? 'project-console__toggle-item project-console__toggle-item--active'
                          : 'project-console__toggle-item'
                      }
                      onClick={() => setViewMode('runtime')}
                      type="button"
                    >
                      运行态
                    </button>
                  </div>
              }
            >

                {viewMode === 'overview' && (
                  <div className="project-console__section-stack">
                    <div className="project-console__kv-grid">
                      <div className="project-console__kv">
                        <span>厂商 / 平台</span>
                        <strong>{workspace.project.vendor}</strong>
                        <small>{workspace.project.processor}</small>
                      </div>
                      <div className="project-console__kv">
                        <span>适用模板</span>
                        <strong>{workspace.summary.benchmark_definition_count}</strong>
                        <small>用于快速确认当前项目可用的测评模板。</small>
                      </div>
                      <div className="project-console__kv">
                        <span>归档报告</span>
                        <strong>{reports.length}</strong>
                        <small>{latestReport ? `最新 ${formatDateTime(latestReport.updated_at_utc)}` : '尚无报告'}</small>
                      </div>
                      <div className="project-console__kv">
                        <span>活跃任务</span>
                        <strong>{activeTaskCount}</strong>
                        <small>{workspace.summary.active_run_count} 个运行仍在更新</small>
                      </div>
                    </div>

                    <div className="project-console__chip-block">
                      <div className="project-console__summary-item">
                        <span>项目说明</span>
                        <strong>{workspace.project.name}</strong>
                        <small>{workspace.project.description}</small>
                      </div>
                      <div className="project-console__summary-item">
                        <span>评测关注</span>
                        <div className="project-console__chips">
                          {workspace.project.benchmark_focus.map((item) => (
                            <span className="project-console__chip" key={item}>
                              {item}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="project-console__summary-item">
                        <span>目标指标</span>
                        <div className="project-console__chips">
                          {workspace.project.target_metrics.map((item) => (
                            <span className="project-console__chip project-console__chip--muted" key={item}>
                              {item}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div className="project-console__table-split">
                      <div>
                        <div className="project-console__table-title">适用模板摘要</div>
                        <div className="project-console__table">
                          {workspace.benchmark_definitions.map((definition) => (
                            <div className="project-console__table-row" key={definition.benchmark_definition_id}>
                              <div>
                                <span>{definition.name}</span>
                                <strong>{definition.report_shape}</strong>
                                <small>
                                  {planningModeLabel(definition.planning_mode)} / {definition.cadence}
                                </small>
                              </div>
                              <small>{definition.default_project_id ?? workspace.project.project_id}</small>
                              <Link
                                className="horizon-button-secondary"
                                onClick={() =>
                                  setWorkflowSelection({
                                    benchmarkDefinitionId: definition.benchmark_definition_id
                                  })
                                }
                                to="/benchmarks"
                                viewTransition
                              >
                                去编排
                              </Link>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div>
                        <div className="project-console__table-title">最新归档</div>
                        <div className="project-console__table">
                          {reports.length === 0 ? (
                            <div className="project-console__table-empty">当前项目还没有导出的报告资产。</div>
                          ) : (
                            reports.slice(0, 4).map((report) => (
                              <div className="project-console__table-row" key={report.report_id}>
                                <div>
                                  <span>{report.title}</span>
                                  <strong>{report.benchmark_definition_id}</strong>
                                  <small>{formatDateTime(report.updated_at_utc)}</small>
                                </div>
                                <StatusPill canonical status={report.status} />
                                <div className="project-console__report-actions">
                                  <a
                                    className="horizon-button-secondary"
                                    href={`/reports/${report.report_id}/download?format=json`}
                                    rel="noreferrer"
                                    target="_blank"
                                  >
                                    JSON
                                  </a>
                                </div>
                              </div>
                            ))
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {viewMode === 'reports' && (
                  <div className="project-console__section-stack">
                    <div className="project-console__summary-grid">
                      <div className="project-console__summary-item">
                        <span>报告总数</span>
                        <strong>{reports.length}</strong>
                        <small>按更新时间倒序归档。</small>
                      </div>
                      <div className="project-console__summary-item">
                        <span>待补报告任务</span>
                        <strong>{pendingReportTasks.length}</strong>
                        <small>{archivableTaskCount} 个任务已具备归档条件。</small>
                      </div>
                      <div className="project-console__summary-item">
                        <span>最新报告</span>
                        <strong>{latestReport?.status ?? '无'}</strong>
                        <small>{latestReport ? latestReport.title : '还没有报告资产'}</small>
                      </div>
                      <div className="project-console__summary-item">
                        <span>最近导出时间</span>
                        <strong>{latestReport ? formatDateTime(latestReport.updated_at_utc) : '--'}</strong>
                        <small>进入报告页可查看完整分析与导出结果。</small>
                      </div>
                    </div>

                    <div className="project-console__table-split">
                      <div>
                        <div className="project-console__table-title">项目报告</div>
                        {reportsQuery.isLoading ? (
                          <EmptyState description="正在同步当前项目的报告资产。" title="报告加载中" />
                        ) : reports.length === 0 ? (
                          <EmptyState description="执行完成并导出后，当前项目的报告会汇总到这里。" title="暂无报告" />
                        ) : (
                          <div className="project-console__table">
                            {reports.map((report) => (
                              <div className="project-console__table-row" key={report.report_id}>
                                <div>
                                  <span>{report.title}</span>
                                  <strong>{report.benchmark_definition_id}</strong>
                                  <small>{formatDateTime(report.updated_at_utc)}</small>
                                </div>
                                <StatusPill canonical status={report.status} />
                                <div className="project-console__report-actions">
                                  <a
                                    className="horizon-button-secondary"
                                    href={`/reports/${report.report_id}/download?format=json`}
                                    rel="noreferrer"
                                    target="_blank"
                                  >
                                    JSON
                                  </a>
                                  <a
                                    className="horizon-button-secondary"
                                    href={`/reports/${report.report_id}/download?format=markdown`}
                                    rel="noreferrer"
                                    target="_blank"
                                  >
                                    MD
                                  </a>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      <div>
                        <div className="project-console__table-title">待补归档</div>
                        <div className="project-console__table">
                          {pendingReportTasks.length === 0 ? (
                            <div className="project-console__table-empty">当前终态任务都已经有报告，或者还没有可归档任务。</div>
                          ) : (
                            pendingReportTasks.map((task) => (
                              <div className="project-console__table-row" key={task.benchmark_task_id}>
                                <div>
                                  <span>{task.benchmark_name}</span>
                                  <strong>{task.status}</strong>
                                  <small>{formatDateTime(task.updated_at_utc)}</small>
                                </div>
                                <small>{task.planned_run_count} 个运行</small>
                                <Link className="horizon-button-secondary" to="/reports" viewTransition>
                                  去归档
                                </Link>
                              </div>
                            ))
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {viewMode === 'runtime' && (
                  <div className="project-console__section-stack">
                    <div className="project-console__summary-grid">
                      <div className="project-console__summary-item">
                        <span>执行器</span>
                        <strong>{systemQuery.data?.executor.status ?? '未知'}</strong>
                        <small>{systemQuery.data?.executor.warning ?? '无额外警告'}</small>
                      </div>
                      <div className="project-console__summary-item">
                        <span>在线设备</span>
                        <strong>{workspace.summary.online_gateway_count}</strong>
                        <small>总计 {workspace.summary.total_gateway_count}</small>
                      </div>
                      <div className="project-console__summary-item">
                        <span>最近运行</span>
                        <strong>{workspace.summary.recent_run_count}</strong>
                        <small>{latestRun ? latestRun.scenario_name : '暂无运行'}</small>
                      </div>
                      <div className="project-console__summary-item">
                        <span>最近任务</span>
                        <strong>{workspace.summary.benchmark_task_count}</strong>
                        <small>{latestTask ? latestTask.benchmark_name : '暂无任务'}</small>
                      </div>
                    </div>

                    <div className="project-console__table-split">
                      <div>
                        <div className="project-console__table-title">最近运行</div>
                        <div className="project-console__table">
                          {workspace.recent_runs.length === 0 ? (
                            <div className="project-console__table-empty">当前项目暂无运行记录。</div>
                          ) : (
                            workspace.recent_runs.slice(0, 6).map((run) => (
                              <div className="project-console__table-row" key={run.run_id}>
                                <div>
                                  <span>{run.scenario_name}</span>
                                  <strong>{run.status}</strong>
                                  <small>{truncateMiddle(run.run_id, 18)}</small>
                                </div>
                                <small>{run.execution_backend}</small>
                                <Link className="horizon-button-secondary" to="/executions" viewTransition>
                                  去查看
                                </Link>
                              </div>
                            ))
                          )}
                        </div>
                      </div>

                      <div>
                        <div className="project-console__table-title">设备状态</div>
                        <div className="project-console__table">
                          {workspace.gateways.length === 0 ? (
                            <div className="project-console__table-empty">当前没有设备状态。</div>
                          ) : (
                            workspace.gateways.map((gateway) => (
                              <div className="project-console__table-row" key={gateway.gateway_id}>
                                <div>
                                  <span>{gateway.name}</span>
                                  <strong>{gateway.status}</strong>
                                  <small>{gateway.address ?? gateway.gateway_id}</small>
                                </div>
                                <small>{gateway.current_run_id ? '忙碌' : '空闲'}</small>
                                <Link className="horizon-button-secondary" to="/devices" viewTransition>
                                  去设备页
                                </Link>
                              </div>
                            ))
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
            </Panel>
          )}
        </div>

        <aside className="project-console__summary">
          <Panel eyebrow="当前项目" subtitle="快速确认项目定位、平台对象和测评关注点。" title="项目定位">
            {workspace ? (
              <div className="project-console__summary-stack">
                <p>项目: {workspace.project.name}</p>
                <p>厂商: {workspace.project.vendor}</p>
                <p>平台: {workspace.project.processor}</p>
                <small>完整模板编排和场景配置可从基准任务与场景集继续进入。</small>
              </div>
            ) : (
              <EmptyState description="选择项目后显示项目定位。" title="没有项目定位" />
            )}
          </Panel>

          <Panel eyebrow="快速跳转" subtitle="从项目归档直接跳到下一步操作。" title="下一步入口">
            <div className="project-console__action-grid">
                <Link className="horizon-button project-console__action-link" to="/benchmarks" viewTransition>
                  基准任务
                </Link>
                <Link className="horizon-button-secondary project-console__action-link" to="/reports" viewTransition>
                  报告中心
                </Link>
                <Link className="horizon-button-secondary project-console__action-link" to="/executions" viewTransition>
                  执行中心
                </Link>
                <Link className="horizon-button-secondary project-console__action-link" to="/scenario-sets" viewTransition>
                  场景集
                </Link>
            </div>
          </Panel>

          <Panel eyebrow="最近归档" subtitle="优先显示最近导出的报告资产，没有报告时退回显示最近任务。" title="最新资产">
            {latestReport ? (
              <div className="project-console__summary-stack">
                <p>报告: {latestReport.title}</p>
                <p>状态: {latestReport.status}</p>
                <p>时间: {formatDateTime(latestReport.updated_at_utc)}</p>
                <div className="project-console__report-actions">
                    <a
                      className="horizon-button-secondary"
                      href={`/reports/${latestReport.report_id}/download?format=json`}
                      rel="noreferrer"
                      target="_blank"
                    >
                      JSON
                    </a>
                    <a
                      className="horizon-button-secondary"
                      href={`/reports/${latestReport.report_id}/download?format=markdown`}
                      rel="noreferrer"
                      target="_blank"
                    >
                      Markdown
                    </a>
                </div>
              </div>
            ) : latestTask ? (
              <div className="project-console__summary-stack">
                <p>最近任务: {latestTask.benchmark_name}</p>
                <p>状态: {latestTask.status}</p>
                <p>时间: {formatDateTime(latestTask.updated_at_utc)}</p>
                <small>当前还没有导出报告，可以到报告中心继续归档。</small>
                </div>
            ) : (
              <EmptyState description="当前项目还没有任务或报告资产。" title="没有归档内容" />
            )}
          </Panel>
        </aside>
      </div>
    </div>
  );
}
