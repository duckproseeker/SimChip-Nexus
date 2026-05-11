import { useEffect, useMemo, useRef, useState } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams, useSearchParams } from 'react-router-dom';

import { listBenchmarkDefinitions } from '../../api/benchmarks';
import { listProjects } from '../../api/projects';
import {
  cancelRun,
  getRun,
  getRunEnvironment,
  getRunEvents,
  getRunViewer,
  startRunSensorCapture,
  startRun,
  stopRunSensorCapture,
  stopRun,
  updateRunEnvironment
} from '../../api/runs';
import { listEnvironmentPresets } from '../../api/scenarios';
import type { WeatherConfig } from '../../api/types';
import { EmptyState } from '../../components/common/EmptyState';
import { JsonBlock } from '../../components/common/JsonBlock';
import { KeyValueGrid } from '../../components/common/KeyValueGrid';
import { MetricCard } from '../../components/common/MetricCard';
import { PageHeader } from '../../components/common/PageHeader';
import { Panel } from '../../components/common/Panel';
import { StatusPill } from '../../components/common/StatusPill';
import { formatDateTime, formatRelativeDuration, terminalStatus } from '../../lib/format';
import {
  deriveRunFps,
  findBenchmarkDefinition,
  findProjectRecord,
  getRunBenchmarkId,
  getRunDutModel,
  getRunProjectId,
  metricNumber
} from '../../lib/platform';
import { buildViewerSocketUrl } from '../../lib/viewer';

const defaultWeather: WeatherConfig = {
  preset: 'ClearNoon'
};

export function ExecutionDetailPage() {
  const { runId = '' } = useParams();
  const [searchParams] = useSearchParams();
  const monitorMode = searchParams.get('mode') === 'monitor';
  const queryClient = useQueryClient();

  const [weatherDraft, setWeatherDraft] = useState<WeatherConfig>(defaultWeather);
  const [viewerFriendly, setViewerFriendly] = useState(false);
  const [selectedViewerView, setSelectedViewerView] = useState('first_person');
  const [viewerSnapshotSeed, setViewerSnapshotSeed] = useState(() => Date.now());
  const [streamFrameUrl, setStreamFrameUrl] = useState<string | null>(null);
  const [streamMessage, setStreamMessage] = useState<string | null>(null);
  const [streamConnected, setStreamConnected] = useState(false);
  const [streamBufferDepth, setStreamBufferDepth] = useState(0);
  const [streamBuffering, setStreamBuffering] = useState(false);
  const streamFrameQueueRef = useRef<string[]>([]);
  const streamPlaybackPrimedRef = useRef(false);

  const runQuery = useQuery({
    queryKey: ['runs', runId],
    queryFn: () => getRun(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && terminalStatus(status) ? false : 3000;
    }
  });

  const eventsQuery = useQuery({
    queryKey: ['runs', runId, 'events'],
    queryFn: () => getRunEvents(runId),
    enabled: Boolean(runId),
    refetchInterval: 3000
  });

  const environmentQuery = useQuery({
    queryKey: ['runs', runId, 'environment'],
    queryFn: () => getRunEnvironment(runId),
    enabled: Boolean(runId),
    refetchInterval: 3000
  });

  const viewerQuery = useQuery({
    queryKey: ['runs', runId, 'viewer'],
    queryFn: () => getRunViewer(runId),
    enabled: Boolean(runId),
    refetchInterval: 5000
  });

  const environmentPresetsQuery = useQuery({
    queryKey: ['environment-presets'],
    queryFn: listEnvironmentPresets
  });
  const projectsQuery = useQuery({ queryKey: ['projects'], queryFn: listProjects });
  const benchmarkDefinitionsQuery = useQuery({
    queryKey: ['benchmark-definitions'],
    queryFn: listBenchmarkDefinitions
  });

  useEffect(() => {
    if (environmentQuery.data?.descriptor_weather) {
      setWeatherDraft(
        environmentQuery.data.runtime_control.weather ??
          environmentQuery.data.descriptor_weather
      );
      setViewerFriendly(
        Boolean(
          environmentQuery.data.runtime_control.debug?.viewer_friendly ??
            environmentQuery.data.descriptor_debug?.viewer_friendly
        )
      );
    }
  }, [environmentQuery.data]);

  useEffect(() => {
    const nextView = viewerQuery.data?.views?.[0]?.view_id;
    if (!nextView) {
      return;
    }
    setSelectedViewerView((current) => {
      if (viewerQuery.data?.views.some((item) => item.view_id === current)) {
        return current;
      }
      return nextView;
    });
  }, [viewerQuery.data]);

  useEffect(() => {
    streamFrameQueueRef.current = [];
    streamPlaybackPrimedRef.current = false;
    setStreamFrameUrl(null);
    setStreamMessage(null);
    setStreamConnected(false);
    setStreamBufferDepth(0);
    setStreamBuffering(false);

    if (!viewerQuery.data?.available || !viewerQuery.data.stream_ws_path) {
      return undefined;
    }

    const playbackIntervalMs = Math.max(
      viewerQuery.data.playback_interval_ms ?? viewerQuery.data.stream_interval_ms,
      80
    );
    const streamBufferMinFrames = Math.max(
      1,
      viewerQuery.data.stream_buffer_min_frames ?? 2
    );
    const streamBufferMaxFrames = Math.max(
      streamBufferMinFrames + 1,
      viewerQuery.data.stream_buffer_max_frames ?? 8
    );
    const playbackTimer = window.setInterval(() => {
      const queue = streamFrameQueueRef.current;
      if (!streamPlaybackPrimedRef.current) {
        setStreamBuffering(true);
        setStreamBufferDepth(queue.length);
        if (queue.length < streamBufferMinFrames) {
          return;
        }
        streamPlaybackPrimedRef.current = true;
      }

      const nextFrameUrl = queue.shift();
      if (!nextFrameUrl) {
        streamPlaybackPrimedRef.current = false;
        setStreamBuffering(true);
        setStreamBufferDepth(0);
        return;
      }

      setStreamFrameUrl(nextFrameUrl);
      setStreamBufferDepth(queue.length);
      setStreamBuffering(queue.length < streamBufferMinFrames);
    }, playbackIntervalMs);

    const socket = new WebSocket(
      buildViewerSocketUrl(viewerQuery.data.stream_ws_path, selectedViewerView)
    );

    socket.onopen = () => {
      setStreamConnected(true);
      setStreamMessage(null);
    };

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as
          | {
              type: 'frame';
              mime: string;
              image_base64: string;
            }
          | {
              type: 'unavailable' | 'error';
              reason?: string;
              message?: string;
            };

        if (payload.type === 'frame') {
          const queue = streamFrameQueueRef.current;
          queue.push(`data:${payload.mime};base64,${payload.image_base64}`);
          while (queue.length > streamBufferMaxFrames) {
            queue.shift();
          }
          setStreamBufferDepth(queue.length);
          setStreamMessage(null);
          return;
        }

        streamPlaybackPrimedRef.current = false;
        setStreamMessage(payload.reason ?? payload.message ?? '流式画面暂不可用');
      } catch {
        streamPlaybackPrimedRef.current = false;
        setStreamMessage('流式画面消息解析失败');
      }
    };

    socket.onerror = () => {
      streamPlaybackPrimedRef.current = false;
      setStreamMessage('流式画面连接失败');
    };

    socket.onclose = () => {
      setStreamConnected(false);
    };

    return () => {
      window.clearInterval(playbackTimer);
      streamFrameQueueRef.current = [];
      streamPlaybackPrimedRef.current = false;
      socket.close();
    };
  }, [
    runId,
    selectedViewerView,
    viewerQuery.data?.available,
    viewerQuery.data?.stream_ws_path,
    viewerQuery.data?.playback_interval_ms,
    viewerQuery.data?.stream_buffer_max_frames,
    viewerQuery.data?.stream_buffer_min_frames,
    viewerQuery.data?.stream_interval_ms
  ]);

  const stopMutation = useMutation({
    mutationFn: () => stopRun(runId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['runs', runId] });
      void queryClient.invalidateQueries({ queryKey: ['runs'] });
    }
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelRun(runId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['runs', runId] });
      void queryClient.invalidateQueries({ queryKey: ['runs'] });
    }
  });

  const startMutation = useMutation({
    mutationFn: () => startRun(runId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['runs', runId] });
      void queryClient.invalidateQueries({ queryKey: ['runs'] });
      void queryClient.invalidateQueries({ queryKey: ['system-status'] });
    }
  });

  const updateEnvironmentMutation = useMutation({
    mutationFn: () =>
      updateRunEnvironment(runId, {
        weather: weatherDraft,
        debug: { viewer_friendly: viewerFriendly }
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['runs', runId, 'environment'] });
      void queryClient.invalidateQueries({ queryKey: ['runs', runId] });
      setViewerSnapshotSeed(Date.now());
    }
  });

  const startSensorCaptureMutation = useMutation({
    mutationFn: () => startRunSensorCapture(runId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['runs', runId, 'environment'] });
      void queryClient.invalidateQueries({ queryKey: ['runs', runId, 'events'] });
    }
  });

  const stopSensorCaptureMutation = useMutation({
    mutationFn: () => stopRunSensorCapture(runId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['runs', runId, 'environment'] });
      void queryClient.invalidateQueries({ queryKey: ['runs', runId, 'events'] });
    }
  });

  const run = runQuery.data;
  const project = run ? findProjectRecord(projectsQuery.data ?? [], getRunProjectId(run)) : null;
  const benchmark = run
    ? findBenchmarkDefinition(
        benchmarkDefinitionsQuery.data ?? [],
        getRunBenchmarkId(run)
      )
    : null;
  const dutModel = run ? getRunDutModel(run) : null;
  const fps = run ? deriveRunFps(run) : null;
  const deviceMetrics = run?.device_metrics ?? null;
  const deviceOutputFps = metricNumber(deviceMetrics, ['output_fps', 'inference_fps', 'render_fps']);
  const deviceLatencyMs = metricNumber(deviceMetrics, ['avg_latency_ms', 'latency_ms', 'p95_latency_ms']);
  const devicePowerW = metricNumber(deviceMetrics, ['power_w', 'soc_power_w', 'board_power_w', 'total_power_w']);
  const deviceTemperatureC = metricNumber(deviceMetrics, ['temperature_c', 'soc_temp_c', 'cpu_temp_c', 'board_temp_c']);
  const deviceProcessedFrames = metricNumber(deviceMetrics, ['processed_frames']);
  const deviceDetectionCount = metricNumber(deviceMetrics, ['detection_count']);
  const events = eventsQuery.data ?? [];
  const runtimeControl = environmentQuery.data?.runtime_control ?? null;
  const sensorCaptureControl = runtimeControl?.sensor_capture ?? null;
  const recorderControl = runtimeControl?.recorder ?? null;
  const sensorOutputSummaries = sensorCaptureControl?.sensor_outputs ?? [];
  const sensorCaptureManifest = sensorCaptureControl?.manifest ?? null;
  const sensorCaptureDownloadUrl = sensorCaptureControl?.download_url ?? null;
  const runActive = ['STARTING', 'RUNNING', 'PAUSED', 'STOPPING'].includes(run?.status ?? '');
  const sensorCaptureStatus =
    sensorCaptureControl?.status ?? (run?.sensors?.enabled ? 'STOPPED' : 'DISABLED');
  const canStartSensorCapture =
    runActive &&
    Boolean(sensorCaptureControl?.enabled ?? run?.sensors?.enabled) &&
    !['RUNNING', 'STARTING'].includes(sensorCaptureStatus);
  const canStopSensorCapture =
    runActive &&
    Boolean(sensorCaptureControl?.enabled ?? run?.sensors?.enabled) &&
    ['RUNNING', 'STARTING', 'STOPPING'].includes(sensorCaptureStatus);

  const viewerSnapshotUrl =
    viewerQuery.data?.snapshot_url && selectedViewerView
      ? `${viewerQuery.data.snapshot_url}?view=${selectedViewerView}&ts=${viewerSnapshotSeed}`
      : null;
  const viewerImageUrl = streamFrameUrl ?? viewerSnapshotUrl;
  const streamStatusLabel = streamBuffering
    ? '预览缓冲中'
    : streamConnected
      ? '流式连接中'
      : '等待画面';
  const streamHealthLabel =
    streamMessage ??
    (streamBuffering
      ? `缓冲 ${streamBufferDepth}/${viewerQuery.data?.stream_buffer_min_frames ?? 0} 帧`
      : '画面正常');

  const summaryItems = useMemo(() => {
    if (!run) {
      return [];
    }

    return [
      { label: '状态', value: <StatusPill status={run.status} /> },
      { label: '执行 ID', value: run.run_id },
      { label: '所属项目', value: project?.name ?? '未标记' },
      { label: '待测端型号', value: dutModel ?? '未登记' },
      { label: '基准任务', value: benchmark?.name ?? '未标记' },
      { label: '场景', value: run.scenario_name },
      { label: '地图', value: run.map_name },
      { label: '执行后端', value: run.execution_backend },
      { label: '绑定设备', value: run.hil_config?.gateway_id ?? '-' },
      { label: '天气预设', value: run.weather?.preset ?? '-' },
      { label: '传感器模板', value: run.sensors?.profile_name ?? '-' },
      {
        label: '传感器采集',
        value: run.sensors?.enabled
          ? run.sensors?.auto_start
            ? '自动开始'
            : '手动开始'
          : '未启用'
      },
      {
        label: 'CARLA recorder',
        value: run.recorder?.enabled ? '默认开启' : '未启用'
      },
      { label: '创建时间', value: formatDateTime(run.created_at_utc) },
      { label: '开始时间', value: formatDateTime(run.started_at_utc) },
      { label: '结束时间', value: formatDateTime(run.ended_at_utc) },
      {
        label: '运行时长',
        value: formatRelativeDuration(run.started_at_utc, run.ended_at_utc)
      },
      { label: '失败原因', value: run.error_reason ?? '-' }
    ];
  }, [benchmark?.name, dutModel, project?.name, run]);

  if (!runId) {
    return <EmptyState title="缺少执行 ID" description="路由参数里没有 run_id。" />;
  }

  return (
    <div className="page-stack">
      <PageHeader
        title={monitorMode ? '执行监控' : '执行详情'}
        eyebrow="执行 / 详情"
        chips={
          monitorMode
            ? ['自动跳转', '流式监控', run?.execution_backend === 'scenario_runner' ? '官方 runner' : '天气热更新']
            : ['执行剖面', '事件时间线', run?.execution_backend === 'scenario_runner' ? '官方 runner' : '环境热更新']
        }
        description={run ? `${run.scenario_name} / ${run.map_name}` : runId}
        actions={
          <div className="flex flex-wrap gap-3">
            <Link className="horizon-button-secondary" to="/executions">
              返回执行中心
            </Link>
            {monitorMode && (
              <Link className="horizon-button-secondary" to={`/executions/${runId}`}>
                打开完整详情
              </Link>
            )}
            {run?.status === 'CREATED' && (
              <button
                className="horizon-button"
                disabled={startMutation.isPending}
                onClick={() => startMutation.mutate()}
                type="button"
              >
                启动执行
              </button>
            )}
            {['STARTING', 'RUNNING', 'PAUSED', 'STOPPING'].includes(run?.status ?? '') && (
              <>
                <button
                  className="horizon-button-secondary"
                  disabled={stopMutation.isPending}
                  onClick={() => stopMutation.mutate()}
                  type="button"
                >
                  停止
                </button>
                <button
                  className="inline-flex min-h-11 items-center justify-center rounded-2xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-600 transition hover:-translate-y-0.5"
                  disabled={cancelMutation.isPending}
                  onClick={() => cancelMutation.mutate()}
                  type="button"
                >
                  取消
                </button>
              </>
            )}
          </div>
        }
      />

      {!run ? (
        <Panel>
          <p>加载中...</p>
        </Panel>
      ) : (
        <>
          <Panel
            title="运行时监控"
            subtitle="这里优先展示连续流式画面；如果流式通道短暂不可用，会回退到快照画面。"
          >
            {!viewerQuery.data?.available ? (
              <EmptyState
                title="画面暂不可用"
                description={
                  viewerQuery.data?.reason ??
                  '启动 run 后，这里会显示与 ego_viewer.py 类似的运行时画面。'
                }
              />
            ) : (
              <div className="space-y-4">
                <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_200px_200px]">
                  <label className="field">
                    <span>监视视角</span>
                    <select
                      value={selectedViewerView}
                      onChange={(event) => setSelectedViewerView(event.target.value)}
                    >
                      {viewerQuery.data.views.map((item) => (
                        <option key={item.view_id} value={item.view_id}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <div className="rounded-[18px] border border-secondaryGray-200 bg-secondaryGray-50/70 px-4 py-4">
                    <span className="block text-[11px] font-extrabold uppercase tracking-[0.16em] text-secondaryGray-500">
                      传输状态
                    </span>
                    <strong className="mt-2 block text-sm text-navy-900">
                      {streamStatusLabel}
                    </strong>
                    <span className="mt-2 block text-xs text-secondaryGray-600">
                      目标缓冲 {viewerQuery.data?.stream_buffer_min_frames ?? 0} 帧
                    </span>
                  </div>

                  <div className="field">
                    <span>回退快照</span>
                    <button
                      className="horizon-button-secondary"
                      onClick={() => setViewerSnapshotSeed(Date.now())}
                      type="button"
                    >
                      手动刷新
                    </button>
                  </div>
                </div>

                {viewerImageUrl ? (
                  <div className="overflow-hidden rounded-[28px] border border-secondaryGray-200 bg-secondaryGray-900">
                    <img
                      alt="CARLA 运行时画面"
                      className="h-auto w-full object-cover"
                      src={viewerImageUrl}
                    />
                  </div>
                ) : (
                  <EmptyState
                    title="正在等待首帧"
                    description={streamMessage ?? '执行刚进入运行态时，首帧会有短暂延迟。'}
                  />
                )}

                <div className="grid gap-3 xl:grid-cols-4">
                  <div className="rounded-[18px] border border-secondaryGray-200 bg-secondaryGray-50/70 px-4 py-4">
                    <span className="block text-[11px] font-extrabold uppercase tracking-[0.16em] text-secondaryGray-500">
                      监控模式
                    </span>
                    <strong className="mt-2 block text-sm text-navy-900">
                      {monitorMode ? '自动跳转进入' : '手动打开'}
                    </strong>
                  </div>
                  <div className="rounded-[18px] border border-secondaryGray-200 bg-secondaryGray-50/70 px-4 py-4">
                    <span className="block text-[11px] font-extrabold uppercase tracking-[0.16em] text-secondaryGray-500">
                      主车角色名
                    </span>
                    <strong className="mt-2 block text-sm text-navy-900">
                      {run.execution_backend === 'scenario_runner' ? 'hero / 官方定义' : 'ego_vehicle'}
                    </strong>
                  </div>
                  <div className="rounded-[18px] border border-secondaryGray-200 bg-secondaryGray-50/70 px-4 py-4">
                    <span className="block text-[11px] font-extrabold uppercase tracking-[0.16em] text-secondaryGray-500">
                      流状态
                    </span>
                    <strong className="mt-2 block text-sm text-navy-900">
                      {streamHealthLabel}
                    </strong>
                  </div>
                  <div className="rounded-[18px] border border-secondaryGray-200 bg-secondaryGray-50/70 px-4 py-4">
                    <span className="block text-[11px] font-extrabold uppercase tracking-[0.16em] text-secondaryGray-500">
                      缓冲深度
                    </span>
                    <strong className="mt-2 block text-sm text-navy-900">
                      {streamBufferDepth} / {viewerQuery.data?.stream_buffer_max_frames ?? 0}
                    </strong>
                  </div>
                </div>
              </div>
            )}
          </Panel>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              accent="blue"
              label="执行推进率"
              value={fps ? fps.toFixed(1) : '待接入'}
              hint="run-local tick / wall time"
            />
            <MetricCard
              accent="violet"
              label="当前 Tick"
              value={run.current_tick ?? '-'}
              hint="执行推进深度"
            />
            <MetricCard
              accent="teal"
              label="仿真时间"
              value={run.sim_time ?? '-'}
              hint="sim_time 秒"
            />
            <MetricCard
              accent="orange"
              label="墙钟耗时"
              value={
                run.wall_elapsed_seconds
                  ? `${run.wall_elapsed_seconds.toFixed(1)} s`
                  : '-'
              }
              hint="真实运行耗时"
            />
          </div>

          {(run.hil_config || deviceMetrics) && (
            <Panel
              title="待测端推理快照"
              subtitle="优先展示归档到当前运行的待测端指标，避免设备最新态串到历史执行。"
            >
              {deviceMetrics ? (
                <div className="space-y-4">
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                    <MetricCard
                      accent="orange"
                      label="输出 FPS"
                      value={deviceOutputFps !== null ? deviceOutputFps.toFixed(1) : '待接入'}
                      hint="推理输出吞吐"
                    />
                    <MetricCard
                      accent="violet"
                      label="平均延迟"
                      value={deviceLatencyMs !== null ? `${deviceLatencyMs.toFixed(1)} ms` : '待接入'}
                      hint="端到端平均延迟"
                    />
                    <MetricCard
                      accent="teal"
                      label="功耗"
                      value={devicePowerW !== null ? `${devicePowerW.toFixed(1)} W` : '待接入'}
                      hint="板端功耗"
                    />
                    <MetricCard
                      accent="blue"
                      label="温度"
                      value={
                        deviceTemperatureC !== null
                          ? `${deviceTemperatureC.toFixed(1)} °C`
                          : '待接入'
                      }
                      hint="板端温度"
                    />
                  </div>

                  <KeyValueGrid
                    items={[
                      { label: '处理帧数', value: deviceProcessedFrames ?? '-' },
                      { label: '检测目标数', value: deviceDetectionCount ?? '-' },
                      { label: '网关 ID', value: String(deviceMetrics.gateway_id ?? '-') },
                      { label: '网关状态', value: String(deviceMetrics.gateway_status ?? '-') },
                      {
                        label: '最近心跳',
                        value:
                          typeof deviceMetrics.gateway_last_heartbeat_at_utc === 'string'
                            ? formatDateTime(deviceMetrics.gateway_last_heartbeat_at_utc)
                            : '-'
                      },
                      { label: '待测端状态', value: String(deviceMetrics.dut_status ?? '-') },
                      { label: '模型名称', value: String(deviceMetrics.dut_model_name ?? deviceMetrics.model_name ?? '-') },
                      { label: '输入源', value: String(deviceMetrics.dut_input_topic ?? deviceMetrics.dut_camera_device ?? '-') }
                    ]}
                  />
                </div>
              ) : (
                <EmptyState
                  title="等待待测端指标"
                  description="当前运行已绑定 HIL 设备，但还没有归档到该运行的待测端推理快照。"
                />
              )}
            </Panel>
          )}

          <div className="grid gap-5 2xl:grid-cols-[minmax(0,1.35fr)_420px]">
            <div className="flex flex-col gap-5">
              <Panel title="执行摘要">
                <KeyValueGrid items={summaryItems} />
              </Panel>

              {!monitorMode && (
                <div className="grid gap-5 xl:grid-cols-2">
                  <Panel title="执行标签">
                    <JsonBlock value={run.metadata} />
                  </Panel>
                  <Panel title="评测协议">
                    <JsonBlock
                      value={
                        run.evaluation_profile ?? {
                          message: '当前执行未绑定评测协议。'
                        }
                      }
                    />
                  </Panel>
                </div>
              )}

              <Panel
                title="事件时间线"
                subtitle="直接读取 executor 写入的事件流，适合定位失败和状态切换。"
              >
                {events.length === 0 ? (
                  <EmptyState title="没有事件" description="该执行还没有写入 events.jsonl。" />
                ) : (
                  <div className="timeline">
                    {events.map((event, index) => (
                      <div key={`${event.timestamp}-${index}`} className="timeline__item">
                        <div className="timeline__stamp">
                          <span>{formatDateTime(event.timestamp)}</span>
                          <StatusPill status={event.level} />
                        </div>
                        <div className="timeline__content">
                          <strong>{event.event_type}</strong>
                          <p>{event.message}</p>
                          {Object.keys(event.payload).length > 0 && (
                            <JsonBlock compact value={event.payload} />
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Panel>
            </div>

            <div className="flex flex-col gap-5">
              <Panel
                title="运行环境热更新"
                subtitle={
                  run.runtime_capabilities.weather_update
                    ? '预设场景保持地图和事件固定，只开放天气与 viewer 模式的运行时修改。'
                    : '当前 run 由官方 ScenarioRunner 执行，天气和 viewer 控制由官方场景脚本管理。'
                }
              >
                {run.runtime_capabilities.weather_update ? (
                  <>
                    <div className="form-grid">
                      <label className="field">
                        <span>天气预设</span>
                        <select
                          value={weatherDraft.preset}
                          onChange={(event) =>
                            setWeatherDraft((current) => ({
                              ...current,
                              preset: event.target.value
                            }))
                          }
                        >
                          {environmentPresetsQuery.data?.map((item) => (
                            <option key={item.preset_id} value={item.weather.preset}>
                              {item.display_name}
                            </option>
                          )) ?? <option value="ClearNoon">Clear Noon</option>}
                        </select>
                      </label>

                      <label className="field">
                        <span>Cloudiness</span>
                        <input
                          type="number"
                          value={weatherDraft.cloudiness ?? 0}
                          onChange={(event) =>
                            setWeatherDraft((current) => ({
                              ...current,
                              cloudiness: Number(event.target.value)
                            }))
                          }
                        />
                      </label>

                      <label className="field">
                        <span>Precipitation</span>
                        <input
                          type="number"
                          value={weatherDraft.precipitation ?? 0}
                          onChange={(event) =>
                            setWeatherDraft((current) => ({
                              ...current,
                              precipitation: Number(event.target.value)
                            }))
                          }
                        />
                      </label>

                      <label className="field">
                        <span>Fog Density</span>
                        <input
                          type="number"
                          value={weatherDraft.fog_density ?? 0}
                          onChange={(event) =>
                            setWeatherDraft((current) => ({
                              ...current,
                              fog_density: Number(event.target.value)
                            }))
                          }
                        />
                      </label>

                      <label className="field">
                        <span>Wetness</span>
                        <input
                          type="number"
                          value={weatherDraft.wetness ?? 0}
                          onChange={(event) =>
                            setWeatherDraft((current) => ({
                              ...current,
                              wetness: Number(event.target.value)
                            }))
                          }
                        />
                      </label>

                      <label className="field field--checkbox">
                        <input
                          checked={viewerFriendly}
                          onChange={(event) => setViewerFriendly(event.target.checked)}
                          type="checkbox"
                        />
                        <span>viewer_friendly</span>
                      </label>
                    </div>

                    <div className="mt-5 flex flex-wrap gap-3">
                      <button
                        className="horizon-button"
                        disabled={updateEnvironmentMutation.isPending}
                        onClick={() => updateEnvironmentMutation.mutate()}
                        type="button"
                      >
                        {updateEnvironmentMutation.isPending ? '更新中...' : '应用环境更新'}
                      </button>
                    </div>

                    {updateEnvironmentMutation.error && (
                      <p className="mt-4 text-sm text-rose-600">
                        {updateEnvironmentMutation.error.message}
                      </p>
                    )}
                  </>
                ) : (
                  <div className="rounded-[20px] border border-secondaryGray-200 bg-secondaryGray-50/70 px-4 py-4 text-sm leading-6 text-secondaryGray-600">
                    <p>1. 当前场景由官方 ScenarioRunner / OpenSCENARIO 驱动执行。</p>
                    <p>2. 平台不会在运行中覆盖天气、传感器或 viewer_friendly。</p>
                    <p>3. 如果需要改天气，应修改对应 `.xosc` 或其参数声明。</p>
                  </div>
                )}
              </Panel>

              <Panel title="当前环境状态">
                <JsonBlock
                  compact
                  value={
                    environmentQuery.data ?? {
                      descriptor_weather: run.weather,
                      descriptor_debug: run.debug,
                      runtime_control: {}
                    }
                  }
                />
              </Panel>

              <Panel
                title="数据记录控制"
                subtitle="CARLA recorder 默认用于轻量复现；真实传感器采集需要在运行中手动开始和停止。"
              >
                <div className="space-y-4">
                  <div className="grid gap-4 xl:grid-cols-2">
                    <div className="rounded-[20px] border border-secondaryGray-200 bg-secondaryGray-50/70 px-4 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <span className="block text-[11px] font-extrabold uppercase tracking-[0.16em] text-secondaryGray-500">
                            CARLA Recorder
                          </span>
                          <strong className="mt-2 block text-sm text-navy-900">
                            {recorderControl?.enabled ? '轻量复现记录已启用' : '当前 run 未启用'}
                          </strong>
                        </div>
                        <StatusPill status={recorderControl?.status ?? 'DISABLED'} />
                      </div>
                      <p className="mt-3 text-sm leading-6 text-secondaryGray-600">
                        {recorderControl?.enabled
                          ? '默认记录世界关键状态，产物更轻，适合后续复现。'
                          : '当前运行没有启用 recorder。'}
                      </p>
                      <div className="mt-3 space-y-1 text-xs text-secondaryGray-600">
                        <p>输出路径: {recorderControl?.output_path ?? '-'}</p>
                        <p>最近错误: {recorderControl?.last_error ?? '-'}</p>
                      </div>
                    </div>

                    <div className="rounded-[20px] border border-secondaryGray-200 bg-secondaryGray-50/70 px-4 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <span className="block text-[11px] font-extrabold uppercase tracking-[0.16em] text-secondaryGray-500">
                            传感器采集
                          </span>
                          <strong className="mt-2 block text-sm text-navy-900">
                            {sensorCaptureControl?.enabled
                              ? '真实传感器数据按需落盘'
                              : '当前 run 未挂载可采集传感器'}
                          </strong>
                        </div>
                        <StatusPill status={sensorCaptureStatus} />
                      </div>
                      <div className="mt-3 space-y-1 text-xs text-secondaryGray-600">
                        <p>模板: {sensorCaptureControl?.profile_name ?? run.sensors?.profile_name ?? '-'}</p>
                        <p>传感器数量: {sensorCaptureControl?.sensor_count ?? run.sensors?.sensors?.length ?? 0}</p>
                        <p>输出目录: {sensorCaptureControl?.output_root ?? '-'}</p>
                        <p>已落盘帧数: {sensorCaptureControl?.saved_frames ?? 0}</p>
                        <p>已落盘样本: {sensorCaptureControl?.saved_samples ?? 0}</p>
                        <p>Manifest 路径: {sensorCaptureControl?.manifest_path ?? '-'}</p>
                        <p>Worker 日志尾巴: {sensorCaptureControl?.worker_log_tail ?? '-'}</p>
                        <p>最近错误: {sensorCaptureControl?.last_error ?? '-'}</p>
                      </div>
                      <div className="mt-4 flex flex-wrap gap-3">
                        <button
                          className="horizon-button"
                          disabled={!canStartSensorCapture || startSensorCaptureMutation.isPending}
                          onClick={() => startSensorCaptureMutation.mutate()}
                          type="button"
                        >
                          {startSensorCaptureMutation.isPending ? '请求中...' : '开始采集'}
                        </button>
                        <button
                          className="horizon-button-secondary"
                          disabled={!canStopSensorCapture || stopSensorCaptureMutation.isPending}
                          onClick={() => stopSensorCaptureMutation.mutate()}
                          type="button"
                        >
                          {stopSensorCaptureMutation.isPending ? '请求中...' : '停止采集'}
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-4 xl:grid-cols-2">
                    <div className="rounded-[20px] border border-secondaryGray-200 bg-white px-4 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <span className="block text-[11px] font-extrabold uppercase tracking-[0.16em] text-secondaryGray-500">
                            采集证据
                          </span>
                          <strong className="mt-2 block text-sm text-navy-900">
                            用目录和样本数确认传感器确实在录
                          </strong>
                        </div>
                        {sensorCaptureDownloadUrl ? (
                          <a
                            className="horizon-button-secondary"
                            href={sensorCaptureDownloadUrl}
                          >
                            下载目录
                          </a>
                        ) : null}
                      </div>

                      {sensorOutputSummaries.length > 0 ? (
                        <div className="mt-4 grid gap-3">
                          {sensorOutputSummaries.map((item) => (
                            <div
                              key={item.sensor_id}
                              className="rounded-[16px] border border-secondaryGray-200 bg-secondaryGray-50/70 px-4 py-3"
                            >
                              <div className="flex items-start justify-between gap-3">
                                <strong className="text-sm text-navy-900">{item.sensor_id}</strong>
                                <span className="text-xs font-semibold text-secondaryGray-500">
                                  {item.sample_count} 个样本
                                </span>
                              </div>
                              <div className="mt-2 space-y-1 text-xs text-secondaryGray-600">
                                <p>目录: {item.relative_dir}</p>
                                <p>文件数: {item.file_count}</p>
                                <p>帧文件: {item.frame_file_count}</p>
                                <p>记录行数: {item.record_count}</p>
                                <p>最新产物: {item.latest_artifact_path ?? '-'}</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="mt-4 text-sm leading-6 text-secondaryGray-600">
                          采集开始后，这里会显示各传感器目录、样本数和最新产物，用来判断“viewer 有画面但没数据”的误判。
                        </p>
                      )}
                    </div>

                    <div className="rounded-[20px] border border-secondaryGray-200 bg-white px-4 py-4">
                      <span className="block text-[11px] font-extrabold uppercase tracking-[0.16em] text-secondaryGray-500">
                        Manifest
                      </span>
                      <strong className="mt-2 block text-sm text-navy-900">
                        以 worker 实际写出的清单为准
                      </strong>
                      <div className="mt-3 space-y-1 text-xs text-secondaryGray-600">
                        <p>Manifest 路径: {sensorCaptureControl?.manifest_path ?? '-'}</p>
                        <p>Worker 状态文件: {sensorCaptureControl?.worker_state_path ?? '-'}</p>
                        <p>Worker 日志文件: {sensorCaptureControl?.worker_log_path ?? '-'}</p>
                      </div>
                      <div className="mt-4">
                        <JsonBlock
                          compact
                          value={
                            sensorCaptureManifest ?? {
                              message: 'manifest 尚未生成，通常说明采集还没真正开始或 worker 已提前失败。'
                            }
                          }
                        />
                      </div>
                    </div>
                  </div>

                  {(startSensorCaptureMutation.error || stopSensorCaptureMutation.error) && (
                    <p className="text-sm text-rose-600">
                      {startSensorCaptureMutation.error?.message ??
                        stopSensorCaptureMutation.error?.message}
                    </p>
                  )}
                </div>
              </Panel>

              {!monitorMode && (
                <Panel title="传感器配置">
                  <JsonBlock compact value={run.sensors ?? { enabled: false }} />
                </Panel>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
