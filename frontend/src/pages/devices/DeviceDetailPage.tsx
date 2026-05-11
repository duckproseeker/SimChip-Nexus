import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';

import { getDeviceWorkspace } from '../../api/devices';
import { EmptyState } from '../../components/common/EmptyState';
import { JsonBlock } from '../../components/common/JsonBlock';
import { KeyValueGrid } from '../../components/common/KeyValueGrid';
import { PageHeader } from '../../components/common/PageHeader';
import { Panel } from '../../components/common/Panel';
import { ProgressBar } from '../../components/common/ProgressBar';
import { StatusPill } from '../../components/common/StatusPill';
import { formatDateTime } from '../../lib/format';
import {
  deriveGatewayFrameDropRate,
  deriveGatewayInputFps,
  deriveGatewayLatencyMs,
  deriveGatewayOutputFps,
  deriveGatewayPowerW,
  deriveGatewayTemperatureC,
  formatMetric
} from '../../lib/platform';

export function DeviceDetailPage() {
  const { gatewayId = '' } = useParams();

  const workspaceQuery = useQuery({
    queryKey: ['devices', gatewayId, 'workspace'],
    queryFn: () => getDeviceWorkspace(gatewayId),
    enabled: Boolean(gatewayId),
    refetchInterval: 5000
  });
  const gateway = workspaceQuery.data?.gateway;
  const captures = workspaceQuery.data?.captures ?? [];
  const benchmarkTasks = workspaceQuery.data?.benchmark_tasks ?? [];
  const summary = workspaceQuery.data?.summary;

  if (!gatewayId) {
    return <EmptyState title="缺少设备 ID" description="路由参数里没有 gateway_id。" />;
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="设备详情"
        eyebrow="设备 / 详情"
        chips={['设备遥测', '采集证据链', '底层诊断']}
        description={gateway ? `${gateway.name} / ${gateway.gateway_id}` : gatewayId}
        actions={
          <div className="flex flex-wrap gap-3">
            <Link className="horizon-button-secondary" to="/devices">
              返回设备中心
            </Link>
            <Link className="horizon-button" to="/reports">
              查看报告中心
            </Link>
          </div>
        }
      />

      {workspaceQuery.isLoading ? (
        <Panel>
          <p>加载中...</p>
        </Panel>
      ) : workspaceQuery.isError ? (
        <Panel>
          <p>{workspaceQuery.error instanceof Error ? workspaceQuery.error.message : '设备工作台接口异常。'}</p>
        </Panel>
      ) : !gateway ? (
        <Panel>
          <p>未找到设备。</p>
        </Panel>
      ) : (
        <>
          <Panel title="基础信息">
            <KeyValueGrid
              items={[
                { label: '状态', value: <StatusPill status={gateway.status} /> },
                { label: '名称', value: gateway.name },
                { label: '设备 ID', value: gateway.gateway_id },
                { label: '地址', value: gateway.address ?? '-' },
                { label: '当前执行', value: gateway.current_run_id ?? '-' },
                { label: '最近心跳', value: formatDateTime(gateway.last_heartbeat_at_utc) },
                { label: '最近看到', value: formatDateTime(gateway.last_seen_at_utc) },
                { label: 'Agent 版本', value: gateway.agent_version ?? '-' }
              ]}
            />
          </Panel>

          <div className="grid gap-5 2xl:grid-cols-[minmax(0,1.3fr)_420px]">
            <div className="flex flex-col gap-5">
              <Panel title="关键遥测">
                <KeyValueGrid
                  items={[
                    { label: '输入 FPS', value: formatMetric(summary?.input_fps ?? deriveGatewayInputFps(gateway), 1) },
                    { label: '输出 FPS', value: formatMetric(summary?.output_fps ?? deriveGatewayOutputFps(gateway), 1) },
                    { label: '平均延迟', value: formatMetric(summary?.latency_ms ?? deriveGatewayLatencyMs(gateway), 1, ' ms') },
                    { label: '丢帧率', value: formatMetric(summary?.frame_drop_rate ?? deriveGatewayFrameDropRate(gateway), 3) },
                    { label: '功耗', value: formatMetric(summary?.power_w ?? deriveGatewayPowerW(gateway), 1, ' W') },
                    { label: '温度', value: formatMetric(summary?.temperature_c ?? deriveGatewayTemperatureC(gateway), 1, '°C') },
                    { label: 'HDMI 检测格式', value: String(gateway.metrics.hdmi_detected_format ?? '-') },
                    { label: '采集分辨率', value: String(gateway.metrics.capture_resolution ?? '-') },
                    { label: 'UDC 状态', value: String(gateway.metrics.udc_state ?? '-') },
                    { label: '最近错误', value: String(gateway.metrics.last_error ?? '-') }
                  ]}
                />
              </Panel>

              <Panel title="采集记录">
                {captures.length === 0 ? (
                  <EmptyState title="没有采集记录" description="该设备当前没有关联 capture 记录。" />
                ) : (
                  <div className="flex flex-col gap-4">
                    {captures.map((capture) => (
                      <div
                        key={capture.capture_id}
                        className="rounded-[20px] border border-border-glass bg-[var(--surface-glass)] px-4 py-4"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <strong className="block truncate text-sm font-bold text-text">{capture.capture_id}</strong>
                            <p className="mt-1 truncate text-xs text-text-muted">{capture.save_dir}</p>
                          </div>
                          <StatusPill status={capture.status} />
                        </div>
                        <div className="mt-3">
                          <ProgressBar
                            label={`${capture.saved_frames}/${capture.max_frames ?? 0}`}
                            max={capture.max_frames ?? Math.max(capture.saved_frames, 1)}
                            value={capture.saved_frames}
                          />
                        </div>
                        <p className="mt-3 text-xs text-text-muted">{formatDateTime(capture.updated_at_utc)}</p>
                      </div>
                    ))}
                  </div>
                )}
              </Panel>
            </div>

            <div className="flex flex-col gap-5">
              <Panel title="关联任务">
                {benchmarkTasks.length === 0 ? (
                  <EmptyState title="没有关联任务" description="该设备当前还没有绑定的基准任务。" />
                ) : (
                  <div className="flex flex-col gap-3">
                    {benchmarkTasks.map((task) => (
                      <div
                        key={task.benchmark_task_id}
                        className="rounded-[18px] border border-border-glass bg-[var(--surface-glass)] px-4 py-4"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <strong className="text-sm font-bold text-text">{task.benchmark_name}</strong>
                          <StatusPill status={task.status} />
                        </div>
                        <p className="mt-2 text-xs text-text-muted">
                          {task.dut_model ?? '未登记待测端'} / {task.project_name}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </Panel>

              <Panel title="能力声明">
                <JsonBlock value={gateway.capabilities} />
              </Panel>

              <Panel title="原始指标">
                <JsonBlock compact value={gateway.metrics} />
              </Panel>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
