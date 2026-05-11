import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { getDevicesWorkspace } from '../../api/devices';
import { EmptyState } from '../../components/common/EmptyState';
import { MetricCard } from '../../components/common/MetricCard';
import { PageHeader } from '../../components/common/PageHeader';
import { Panel } from '../../components/common/Panel';
import { StatusPill } from '../../components/common/StatusPill';
import { TelemetryDashboard } from '../../components/common/TelemetryDashboard';
import { formatDateTime, sortByActivity } from '../../lib/format';

export function DevicesPage() {
  const workspaceQuery = useQuery({
    queryKey: ['devices', 'workspace'],
    queryFn: getDevicesWorkspace,
    refetchInterval: 5000
  });

  const gateways = sortByActivity(workspaceQuery.data?.gateways ?? []);
  const tasks = sortByActivity(workspaceQuery.data?.benchmark_tasks ?? []);
  const workspace = workspaceQuery.data;
  const activeTaskCount = tasks.filter((task) =>
    ['RUNNING', 'STARTING', 'CREATED'].includes(task.status)
  ).length;
  const latestGateway = gateways[0] ?? null;

  return (
    <div className="page-stack">
      <PageHeader
        title="设备台 / 待测端运行观测"
        eyebrow="设备 / 遥测与链路"
        chips={['网关心跳', '待测端遥测', '采集链路']}
        description="按网关查看待测端型号、当前任务、最新心跳和时间序列遥测，快速定位设备是否在线、是否正在回传结果。"
        actions={
          <>
            <Link className="horizon-button-secondary" to="/executions" viewTransition>
              打开执行台
            </Link>
            <Link className="horizon-button" to="/studio" viewTransition>
              打开运维台
            </Link>
          </>
        }
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          accent="blue"
          label="在线网关"
          value={workspace?.summary.online_device_count ?? 0}
          hint={`总计 ${gateways.length} 个观测节点`}
        />
        <MetricCard
          accent="teal"
          label="运行中采集"
          value={workspace?.summary.running_capture_count ?? 0}
          hint="采集链仍在写入中的任务数量"
        />
        <MetricCard
          accent="orange"
          label="活动任务"
          value={activeTaskCount}
          hint="绑定到网关且仍处于创建/启动/运行态的任务"
        />
        <MetricCard
          accent="violet"
          label="最近心跳"
          value={latestGateway ? formatDateTime(latestGateway.last_heartbeat_at_utc) : '--'}
          hint={latestGateway ? latestGateway.name : '等待首个网关上线'}
        />
      </div>

      <div className="grid gap-5">
        {workspaceQuery.isLoading ? (
          <EmptyState
            title="设备台加载中"
            description="正在同步网关心跳、当前任务和遥测快照。"
          />
        ) : workspaceQuery.isError ? (
          <EmptyState
            title="设备台加载失败"
            description={workspaceQuery.error instanceof Error ? workspaceQuery.error.message : '接口异常。'}
          />
        ) : gateways.length === 0 ? (
          <EmptyState
            title="当前没有连入的设备"
            description="还没有任何网关持续上报心跳。先检查 Pi gateway_agent、网关登记和当前任务绑定，再回到这里查看遥测。"
            action={
              <Link className="horizon-button-secondary" to="/studio" viewTransition>
                去检查运维配置
              </Link>
            }
          />
        ) : (
          <div className="flex flex-col gap-6">
            {gateways.map((gateway) => {
              const activeTask = tasks.find(
                (t) => t.hil_config?.gateway_id === gateway.gateway_id && ['RUNNING', 'STARTING', 'CREATED'].includes(t.status)
              );

              return (
                <Panel
                  key={gateway.gateway_id}
                  eyebrow="设备观测"
                  title={`观测节点：${gateway.name}`}
                  subtitle="统一查看网关状态、待测端型号、当前任务和遥测趋势。"
                  actions={
                    <Link className="horizon-button" to={`/devices/${gateway.gateway_id}`} viewTransition>
                      查看完整日志
                    </Link>
                  }
                >
                  <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between mb-6 border-b border-border-glass pb-6">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-3">
                        <StatusPill status={gateway.status} />
                        <span className="rounded-full bg-[var(--surface-glass)] border border-[var(--border-glass)] px-3 py-1 text-xs font-semibold text-text-muted">
                          网关: {gateway.gateway_id}
                        </span>
                      </div>
                      {gateway.status_detail ? (
                        <p className="mt-3 text-sm text-text-muted">
                          {gateway.status_detail}
                        </p>
                      ) : null}

                      <div className="mt-4 flex flex-col gap-2">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-text-muted w-20">待测端:</span>
                          <span className="text-sm font-extrabold text-text">
                            {gateway.metrics?.dut_model_name ? String(gateway.metrics.dut_model_name) : '未登记'}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-text-muted w-20">当前任务:</span>
                          {activeTask ? (
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-sm text-text">{activeTask.benchmark_name}</span>
                              <StatusPill status={activeTask.status} />
                            </div>
                          ) : (
                            <span className="text-sm text-text-muted">无运行中的测试</span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>

                  <TelemetryDashboard
                    deviceMetrics={gateway.metrics}
                    runActive={['READY', 'BUSY'].includes(gateway.status)}
                    sampleTimestampUtc={gateway.last_heartbeat_at_utc}
                  />
                </Panel>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
