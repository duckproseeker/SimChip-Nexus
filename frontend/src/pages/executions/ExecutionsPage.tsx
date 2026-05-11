import { useEffect, useMemo, useRef, useState } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { listBenchmarkTasks, rerunBenchmarkTask, stopBenchmarkTask } from '../../api/benchmarks';
import { getRunEvents, getRunViewer, listRuns, stopRun } from '../../api/runs';
import { getSystemStatus, updateCarlaWeather } from '../../api/system';
import type { BenchmarkTaskRecord, RunRecord, WeatherConfig } from '../../api/types';
import { CompactPageHeader } from '../../components/common/CompactPageHeader';
import { DetailPanel } from '../../components/common/DetailPanel';
import { EmptyState } from '../../components/common/EmptyState';
import { EventTimeline } from '../../components/common/EventTimeline';
import { MetricCard } from '../../components/common/MetricCard';
import { MonitorCanvas } from '../../components/common/MonitorCanvas';
import { SelectionList } from '../../components/common/SelectionList';
import { StatusPanel } from '../../components/common/StatusPanel';
import { TelemetryPanel } from '../../components/common/TelemetryPanel';
import { setWorkflowSelection } from '../../features/workflow/state';
import { formatDateTime, sortByActivity, truncateMiddle } from '../../lib/format';
import { deriveRunFps } from '../../lib/platform';
import { buildViewerSocketUrl } from '../../lib/viewer';

type ExecutionViewMode = 'current' | 'archive';
type ViewerState = 'no-run' | 'loading' | 'error' | 'no-viewer' | 'ready';

const runningRunStatuses = ['STARTING', 'RUNNING', 'PAUSED', 'STOPPING'];
const activeTaskStatuses = ['CREATED', 'RUNNING'];
const archivedTaskStatuses = ['COMPLETED', 'PARTIAL_FAILED', 'FAILED', 'CANCELED'];
const weatherPresetStorageKey = 'carla-web.execution-monitor.weather-preset-id';
const officialWeatherCycle: Array<{ id: string; label: string; weather: WeatherConfig }> = [
  { id: 'ClearNoon', label: 'Clear Noon', weather: { preset: 'ClearNoon' } },
  { id: 'ClearSunset', label: 'Clear Sunset', weather: { preset: 'ClearSunset' } },
  { id: 'CloudyNoon', label: 'Cloudy Noon', weather: { preset: 'CloudyNoon' } },
  { id: 'CloudySunset', label: 'Cloudy Sunset', weather: { preset: 'CloudySunset' } },
  { id: 'HardRainNoon', label: 'Hard Rain Noon', weather: { preset: 'HardRainNoon' } },
  { id: 'HardRainSunset', label: 'Hard Rain Sunset', weather: { preset: 'HardRainSunset' } },
  { id: 'MidRainSunset', label: 'Mid Rain Sunset', weather: { preset: 'MidRainSunset' } },
  { id: 'MidRainyNoon', label: 'Mid Rainy Noon', weather: { preset: 'MidRainyNoon' } },
  { id: 'SoftRainNoon', label: 'Soft Rain Noon', weather: { preset: 'SoftRainNoon' } },
  { id: 'SoftRainSunset', label: 'Soft Rain Sunset', weather: { preset: 'SoftRainSunset' } },
  { id: 'WetCloudyNoon', label: 'Wet Cloudy Noon', weather: { preset: 'WetCloudyNoon' } },
  { id: 'WetCloudySunset', label: 'Wet Cloudy Sunset', weather: { preset: 'WetCloudySunset' } },
  { id: 'WetNoon', label: 'Wet Noon', weather: { preset: 'WetNoon' } },
  { id: 'WetSunset', label: 'Wet Sunset', weather: { preset: 'WetSunset' } }
];

function pickPreferredTask(tasks: BenchmarkTaskRecord[]) {
  return (
    tasks.find((task) => task.status === 'RUNNING') ??
    tasks.find((task) => task.status === 'CREATED') ??
    tasks[0] ??
    null
  );
}

function queueEntries(task: BenchmarkTaskRecord | null) {
  return task?.summary.execution_queue?.ordered_runs ?? [];
}

function activeQueueEntry(task: BenchmarkTaskRecord | null) {
  const entries = queueEntries(task);
  return (
    entries.find((entry) => entry.is_active) ??
    entries.find((entry) => ['STARTING', 'RUNNING', 'PAUSED', 'STOPPING'].includes(entry.status)) ??
    null
  );
}

function nextQueueEntry(task: BenchmarkTaskRecord | null) {
  const entries = queueEntries(task);
  return (
    entries.find((entry) => entry.is_next) ??
    entries.find((entry) => ['CREATED', 'QUEUED'].includes(entry.status)) ??
    null
  );
}

function pickPreferredRunId(task: BenchmarkTaskRecord | null) {
  if (!task) {
    return null;
  }

  const activeEntry = activeQueueEntry(task);
  if (activeEntry) {
    return activeEntry.run_id;
  }

  const nextEntry = nextQueueEntry(task);
  if (nextEntry) {
    return nextEntry.run_id;
  }

  return task.run_ids[0] ?? null;
}

function displayQueueStatus(status: string | null | undefined) {
  if (!status) {
    return 'UNKNOWN';
  }
  if (status === 'CREATED' || status === 'QUEUED') {
    return 'QUEUED';
  }
  return status;
}

function currentTaskDisplayStatus(task: BenchmarkTaskRecord) {
  const currentScenario = activeQueueEntry(task);
  if (currentScenario) {
    return displayQueueStatus(currentScenario.status);
  }
  const nextScenario = nextQueueEntry(task);
  if (nextScenario) {
    return 'QUEUED';
  }
  return task.status;
}

export function ExecutionsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const taskIdFromQuery = searchParams.get('task')?.trim() || null;

  const [viewMode, setViewMode] = useState<ExecutionViewMode>('current');
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(taskIdFromQuery);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedViewerView, setSelectedViewerView] = useState('first_person');
  const [viewerRefreshSeed, setViewerRefreshSeed] = useState(() => Date.now());
  const [streamFrameUrl, setStreamFrameUrl] = useState<string | null>(null);
  const [streamMessage, setStreamMessage] = useState<string | null>(null);
  const [streamConnected, setStreamConnected] = useState(false);
  const [streamBufferDepth, setStreamBufferDepth] = useState(0);
  const [streamBuffering, setStreamBuffering] = useState(false);
  const [lastWeatherPresetId, setLastWeatherPresetId] = useState<string | null>(() =>
    typeof window === 'undefined' ? null : window.localStorage.getItem(weatherPresetStorageKey)
  );
  const streamFrameQueueRef = useRef<string[]>([]);
  const streamPlaybackPrimedRef = useRef(false);
  const pendingQueryTaskIdRef = useRef<string | null>(taskIdFromQuery);

  const tasksQuery = useQuery({
    queryKey: ['benchmark-tasks'],
    queryFn: () => listBenchmarkTasks(),
    refetchInterval: 5000
  });
  const runsQuery = useQuery({
    queryKey: ['runs'],
    queryFn: () => listRuns(),
    refetchInterval: 5000
  });
  const systemQuery = useQuery({
    queryKey: ['system-status'],
    queryFn: getSystemStatus,
    refetchInterval: 3000
  });
  const tasks = tasksQuery.data ?? [];
  const runs = sortByActivity(runsQuery.data ?? []);
  const activeTasks = tasks.filter((task) => activeTaskStatuses.includes(task.status));
  const archivedTasks = tasks.filter((task) => archivedTaskStatuses.includes(task.status));
  const visibleTasks = viewMode === 'current' ? activeTasks : archivedTasks;
  const standaloneRuns = runs.filter((run) => !run.benchmark_task_id);
  const standaloneRunningRuns = standaloneRuns.filter((run) =>
    runningRunStatuses.includes(run.status)
  );
  const standaloneQueuedRuns = standaloneRuns.filter((run) => run.status === 'QUEUED');
  const hasStandaloneCurrentActivity =
    standaloneRunningRuns.length > 0 || standaloneQueuedRuns.length > 0;
  const taskForQuery =
    taskIdFromQuery
      ? tasks.find((task) => task.benchmark_task_id === taskIdFromQuery) ?? null
      : null;

  useEffect(() => {
    if (!taskIdFromQuery) {
      pendingQueryTaskIdRef.current = null;
      if (
        viewMode === 'current' &&
        activeTasks.length === 0 &&
        !hasStandaloneCurrentActivity &&
        archivedTasks.length > 0
      ) {
        setViewMode('archive');
      }
      return;
    }

    if (activeTasks.some((task) => task.benchmark_task_id === taskIdFromQuery)) {
      if (viewMode !== 'archive') {
        setViewMode('current');
      }
      return;
    }

    if (archivedTasks.some((task) => task.benchmark_task_id === taskIdFromQuery)) {
      setViewMode('archive');
    }
  }, [activeTasks, archivedTasks, hasStandaloneCurrentActivity, taskIdFromQuery, viewMode]);

  useEffect(() => {
    if (viewMode === 'current' && taskIdFromQuery) {
      if (!taskForQuery) {
        pendingQueryTaskIdRef.current = taskIdFromQuery;
        return;
      }

      if (pendingQueryTaskIdRef.current === taskIdFromQuery && selectedTaskId !== taskForQuery.benchmark_task_id) {
        setSelectedTaskId(taskForQuery.benchmark_task_id);
      }
      pendingQueryTaskIdRef.current = null;
      return;
    }

    if (selectedTaskId && visibleTasks.some((task) => task.benchmark_task_id === selectedTaskId)) {
      return;
    }

    const nextTask = pickPreferredTask(visibleTasks);
    const nextTaskId = nextTask?.benchmark_task_id ?? null;
    if (selectedTaskId !== nextTaskId) {
      setSelectedTaskId(nextTaskId);
    }
  }, [selectedTaskId, taskForQuery, taskIdFromQuery, viewMode, visibleTasks]);

  const selectedTask = tasks.find((task) => task.benchmark_task_id === selectedTaskId) ?? null;
  const selectedTaskQueue = queueEntries(selectedTask);
  const currentEntry = activeQueueEntry(selectedTask);
  const nextEntry = nextQueueEntry(selectedTask);
  const waitingEntries = selectedTaskQueue.filter((entry) => ['CREATED', 'QUEUED'].includes(entry.status));
  const standaloneCurrentRun = standaloneRunningRuns[0] ?? null;
  const standaloneNextRun = standaloneQueuedRuns[0] ?? null;
  const standaloneMonitorActive =
    viewMode === 'current' &&
    activeTasks.length === 0 &&
    hasStandaloneCurrentActivity;

  useEffect(() => {
    if (viewMode !== 'current') {
      if (selectedRunId !== null) {
        setSelectedRunId(null);
      }
      return;
    }

    if (selectedTask) {
      const nextRunId = pickPreferredRunId(selectedTask);
      if (!nextRunId) {
        setSelectedRunId(null);
        return;
      }

      if (selectedRunId && selectedTask.run_ids.includes(selectedRunId)) {
        return;
      }
      setSelectedRunId(nextRunId);
      return;
    }

    const nextStandaloneRunId =
      standaloneCurrentRun?.run_id ?? standaloneNextRun?.run_id ?? null;
    if (selectedRunId !== nextStandaloneRunId) {
      setSelectedRunId(nextStandaloneRunId);
    }
  }, [
    selectedRunId,
    selectedTask,
    standaloneCurrentRun?.run_id,
    standaloneNextRun?.run_id,
    viewMode
  ]);

  useEffect(() => {
    setWorkflowSelection({ runId: selectedRunId });
  }, [selectedRunId]);

  const selectedRun = selectedRunId ? runs.find((run) => run.run_id === selectedRunId) ?? null : null;
  const nextWeatherPreset = useMemo(() => {
    if (officialWeatherCycle.length === 0) {
      return null;
    }

    const currentIndex = lastWeatherPresetId
      ? officialWeatherCycle.findIndex((item) => item.id === lastWeatherPresetId)
      : -1;
    const nextIndex = (currentIndex + 1 + officialWeatherCycle.length) % officialWeatherCycle.length;
    return officialWeatherCycle[nextIndex] ?? officialWeatherCycle[0];
  }, [lastWeatherPresetId]);
  const selectedRunEventsQuery = useQuery({
    queryKey: ['runs', selectedRunId, 'events'],
    queryFn: () => getRunEvents(selectedRunId ?? ''),
    enabled: viewMode === 'current' && Boolean(selectedRunId),
    refetchInterval: 3000
  });
  const selectedRunViewerQuery = useQuery({
    queryKey: ['runs', selectedRunId, 'viewer'],
    queryFn: () => getRunViewer(selectedRunId ?? ''),
    enabled: viewMode === 'current' && Boolean(selectedRunId),
    refetchInterval: 5000
  });
  const viewerViews = selectedRunViewerQuery.data?.views ?? [];
  const hasFirstPersonView = viewerViews.some((item) => item.view_id === 'first_person');
  const hasThirdPersonView = viewerViews.some((item) => item.view_id === 'third_person');

  useEffect(() => {
    const nextView = viewerViews.find((item) => item.view_id === 'first_person')?.view_id
      ?? viewerViews[0]?.view_id;
    if (!nextView) {
      return;
    }
    setSelectedViewerView((current) => {
      if (viewerViews.some((item) => item.view_id === current)) {
        return current;
      }
      return nextView;
    });
  }, [viewerViews]);

  useEffect(() => {
    streamFrameQueueRef.current = [];
    streamPlaybackPrimedRef.current = false;
    setStreamFrameUrl(null);
    setStreamMessage(null);
    setStreamConnected(false);
    setStreamBufferDepth(0);
    setStreamBuffering(false);

    if (
      viewMode !== 'current' ||
      !selectedRunId ||
      !selectedRunViewerQuery.data?.available ||
      !selectedRunViewerQuery.data.stream_ws_path
    ) {
      return undefined;
    }

    const playbackIntervalMs = Math.max(
      selectedRunViewerQuery.data.playback_interval_ms ?? selectedRunViewerQuery.data.stream_interval_ms,
      80
    );
    const streamBufferMinFrames = Math.max(
      1,
      selectedRunViewerQuery.data.stream_buffer_min_frames ?? 2
    );
    const streamBufferMaxFrames = Math.max(
      streamBufferMinFrames + 1,
      selectedRunViewerQuery.data.stream_buffer_max_frames ?? 8
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
      buildViewerSocketUrl(selectedRunViewerQuery.data.stream_ws_path, selectedViewerView)
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
    selectedRunId,
    selectedViewerView,
    selectedRunViewerQuery.data?.available,
    selectedRunViewerQuery.data?.playback_interval_ms,
    selectedRunViewerQuery.data?.stream_buffer_max_frames,
    selectedRunViewerQuery.data?.stream_buffer_min_frames,
    selectedRunViewerQuery.data?.stream_interval_ms,
    selectedRunViewerQuery.data?.stream_ws_path,
    viewMode
  ]);

  const rerunMutation = useMutation({
    mutationFn: (benchmarkTaskId: string) => rerunBenchmarkTask(benchmarkTaskId, true),
    onSuccess: (task) => {
      void queryClient.invalidateQueries({ queryKey: ['benchmark-tasks'] });
      void queryClient.invalidateQueries({ queryKey: ['runs'] });
      void queryClient.invalidateQueries({ queryKey: ['system-status'] });
      setViewMode('current');
      setSelectedTaskId(task.benchmark_task_id);
      setSelectedRunId(null);
      setWorkflowSelection({ runId: null });
      navigate(`/executions?task=${task.benchmark_task_id}`);
    }
  });

  const stopCurrentRunMutation = useMutation({
    mutationFn: (runId: string) => stopRun(runId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['benchmark-tasks'] });
      void queryClient.invalidateQueries({ queryKey: ['runs'] });
      void queryClient.invalidateQueries({ queryKey: ['system-status'] });
      if (selectedRunId) {
        void queryClient.invalidateQueries({ queryKey: ['runs', selectedRunId] });
        void queryClient.invalidateQueries({ queryKey: ['runs', selectedRunId, 'events'] });
        void queryClient.invalidateQueries({ queryKey: ['runs', selectedRunId, 'viewer'] });
      }
    }
  });

  const stopTaskMutation = useMutation({
    mutationFn: (benchmarkTaskId: string) => stopBenchmarkTask(benchmarkTaskId),
    onSuccess: (task) => {
      void queryClient.invalidateQueries({ queryKey: ['benchmark-tasks'] });
      void queryClient.invalidateQueries({ queryKey: ['runs'] });
      void queryClient.invalidateQueries({ queryKey: ['system-status'] });
      setSelectedTaskId(task.benchmark_task_id);
    }
  });
  const cycleWeatherMutation = useMutation({
    mutationFn: async () => {
      if (!nextWeatherPreset) {
        throw new Error('天气预设尚未加载完成。');
      }

      return updateCarlaWeather(nextWeatherPreset.weather);
    },
    onSuccess: () => {
      if (!nextWeatherPreset) {
        return;
      }

      setLastWeatherPresetId(nextWeatherPreset.id);
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(weatherPresetStorageKey, nextWeatherPreset.id);
      }
      void queryClient.invalidateQueries({ queryKey: ['system-status'] });
    }
  });

  const viewerState: ViewerState =
    viewMode !== 'current' || !selectedRun
      ? 'no-run'
      : selectedRunViewerQuery.isPending
        ? 'loading'
        : selectedRunViewerQuery.isError
          ? 'error'
          : selectedRunViewerQuery.data?.available
            ? 'ready'
            : 'no-viewer';

  const streamStatusLabel =
    streamBuffering
      ? '预览缓冲中'
      : streamConnected
        ? '流式连接中'
        : '等待画面';
  const streamHealthLabel =
    streamMessage ??
    (streamBuffering
      ? `缓冲 ${streamBufferDepth}/${selectedRunViewerQuery.data?.stream_buffer_min_frames ?? 0} 帧`
      : viewerState === 'ready'
        ? '画面正常'
        : '等待 viewer 可用');
  const viewerImageUrl =
    viewerState === 'ready'
      ? streamFrameUrl ??
        (selectedRunViewerQuery.data?.snapshot_url
          ? `${selectedRunViewerQuery.data.snapshot_url}?view=${selectedViewerView}&ts=${viewerRefreshSeed}`
          : null)
      : null;

  const activeRunCount = runs.filter((run) => runningRunStatuses.includes(run.status)).length;
  const queuedRunCount = runs.filter((run) => run.status === 'QUEUED').length;
  const archiveCount = archivedTasks.length;
  const executorStatus = systemQuery.data?.executor.status ?? 'UNKNOWN';

  const telemetryItems = [
    {
      label: '批量任务',
      value: selectedTask?.benchmark_name ?? (selectedRun ? '独立场景运行' : '未选择任务'),
      hint: selectedTask?.project_name ?? selectedRun?.project_name ?? '等待选择'
    },
    {
      label: '当前场景',
      value:
        currentEntry?.scenario_display_name ??
        standaloneCurrentRun?.scenario_name ??
        selectedRun?.scenario_name ??
        '当前无活动场景',
      hint:
        currentEntry?.display_map_name ??
        standaloneCurrentRun?.map_name ??
        selectedRun?.map_name ??
        '等待执行'
    },
    {
      label: '下一场景',
      value: nextEntry?.scenario_display_name ?? standaloneNextRun?.scenario_name ?? '无等待场景',
      hint: nextEntry?.display_map_name ?? standaloneNextRun?.map_name ?? '队列已空'
    },
    {
      label: '待测端',
      value: selectedTask?.dut_model ?? selectedRun?.dut_model ?? '未登记',
      hint: selectedRun?.hil_config?.gateway_id ?? '未绑定设备'
    },
    {
      label: '有效帧率',
      value: selectedRun ? (deriveRunFps(selectedRun)?.toFixed(1) ?? '待生成') : '-',
      hint: selectedRun ? selectedRun.execution_backend : '无活动运行'
    },
    {
      label: 'Viewer',
      value:
        viewerState === 'ready'
          ? streamStatusLabel
          : viewerState === 'loading'
            ? 'Viewer 加载中'
            : viewerState === 'error'
              ? 'Viewer 请求失败'
              : '当前无画面',
      hint:
        viewerState === 'no-viewer'
          ? selectedRunViewerQuery.data?.reason ?? '该 run 当前没有 viewer 通道'
          : viewerState === 'ready'
            ? streamHealthLabel
          : viewMode === 'archive'
            ? '归档任务不显示实时画面'
            : '只对当前活动 run 显示画面'
    }
  ];

  const monitorEmptyMessage = useMemo(() => {
    if (viewMode === 'archive') {
      return {
        title: '归档任务视图',
        description: '查看结果或再次执行。'
      };
    }
    if (!selectedRun) {
      if (standaloneMonitorActive) {
        return {
          title: '当前没有活动 run',
          description: '独立场景运行还在排队，或当前没有进入可监控状态的 run。'
        };
      }
      return {
        title: '没有活动任务',
        description: '当前没有活跃批量任务。你可以切到任务归档查看历史任务并再次执行。'
      };
    }
    if (viewerState === 'loading') {
      return { title: 'Viewer 加载中', description: '正在拉取当前运行场景的画面。' };
    }
    if (viewerState === 'error') {
      return {
        title: 'Viewer 请求失败',
        description:
          selectedRunViewerQuery.error instanceof Error
            ? selectedRunViewerQuery.error.message
            : 'viewer 接口请求失败。'
      };
    }
    return {
      title: '当前没有画面',
      description: selectedRunViewerQuery.data?.reason ?? '该 run 暂时没有可用 viewer。'
    };
  }, [
    selectedRun,
    selectedRunViewerQuery.data?.reason,
    selectedRunViewerQuery.error,
    standaloneMonitorActive,
    viewMode,
    viewerState
  ]);

  const switchToCurrentView = () => {
    const nextTask = taskIdFromQuery && activeTasks.some((task) => task.benchmark_task_id === taskIdFromQuery)
      ? taskIdFromQuery
      : pickPreferredTask(activeTasks)?.benchmark_task_id ?? null;
    pendingQueryTaskIdRef.current = nextTask;
    setViewMode('current');
    setSelectedTaskId(nextTask);
    setSelectedRunId(null);
    navigate(nextTask ? `/executions?task=${nextTask}` : '/executions', { replace: true });
  };

  const switchToArchiveView = () => {
    const nextTask =
      selectedTaskId && archivedTasks.some((task) => task.benchmark_task_id === selectedTaskId)
        ? selectedTaskId
        : pickPreferredTask(archivedTasks)?.benchmark_task_id ?? null;
    setViewMode('archive');
    setSelectedTaskId(nextTask);
    setSelectedRunId(null);
    navigate('/executions', { replace: true });
  };

  const handleSelectTask = (taskId: string | null) => {
    setSelectedTaskId(taskId);
    if (viewMode === 'current') {
      pendingQueryTaskIdRef.current = taskId;
      navigate(taskId ? `/executions?task=${taskId}` : '/executions', { replace: true });
    }
  };

  return (
    <div className="page-stack execution-page">
      <CompactPageHeader
        className="compact-page-header--execution"
        stepLabel="步骤 4 / 执行台"
        title="执行台 / 运行监控"
        description="统一查看当前运行、排队队列、历史任务和独立场景执行，避免在多个页面来回切换。"
        contextSummary={
          selectedTask
            ? `${selectedTask.benchmark_name} / ${selectedTask.dut_model ?? '未登记待测端'}`
            : selectedRun
              ? `${selectedRun.scenario_name} / 独立场景运行`
            : viewMode === 'archive'
              ? '查看历史任务归档'
              : '当前没有活跃批量任务'
        }
        actions={
          <>
            <Link className="horizon-button-secondary" to="/benchmarks" viewTransition>
              返回基准任务台
            </Link>
            <Link
              className="horizon-button-secondary"
              to={selectedRun ? `/executions/${selectedRun.run_id}` : '/executions'}
              viewTransition
            >
              打开完整执行详情
            </Link>
          </>
        }
      />

      <div className="grid gap-3 md:grid-cols-4">
        <MetricCard accent="blue" label="运行中任务" value={activeTasks.length} hint="只统计当前执行中的批量任务" />
        <MetricCard accent="teal" label="运行中场景" value={activeRunCount} hint="同一时刻理论上只应有 1 个运行中场景" />
        <MetricCard accent="orange" label="排队场景" value={queuedRunCount} hint="尚未进入当前执行的场景数量" />
        <MetricCard accent="violet" label="归档任务" value={archiveCount} hint="已完成 / 失败 / 取消任务" />
      </div>

      <div className="execution-workbench-grid">
        <div className="flex flex-col gap-3">
          <DetailPanel subtitle="切换当前执行和任务归档两种视图" title="任务视图">
            <div className="project-console__toggle">
              <button
                className={
                  viewMode === 'current'
                    ? 'project-console__toggle-item project-console__toggle-item--active'
                    : 'project-console__toggle-item'
                }
                onClick={switchToCurrentView}
                type="button"
              >
                当前执行
              </button>
              <button
                className={
                  viewMode === 'archive'
                    ? 'project-console__toggle-item project-console__toggle-item--active'
                    : 'project-console__toggle-item'
                }
                onClick={switchToArchiveView}
                type="button"
              >
                任务归档
              </button>
            </div>

            <div className="mt-3">
              {visibleTasks.length > 0 ? (
                <SelectionList
                  emptyDescription={
                    viewMode === 'current'
                      ? '当前没有活跃批量任务。可以先去基准任务台创建批量任务，或到场景集直接发起单次运行。'
                      : '当前还没有进入归档的批量任务。执行完成后这里会沉淀历史记录。'
                  }
                  emptyTitle={viewMode === 'current' ? '无活跃任务' : '无归档任务'}
                  items={visibleTasks.map((task) => {
                    const currentScenario = activeQueueEntry(task);
                    return {
                      id: task.benchmark_task_id,
                      title: task.benchmark_name,
                      subtitle:
                        viewMode === 'current'
                          ? currentScenario?.scenario_display_name ?? '等待进入首个场景'
                          : `${task.summary.counts?.completed_runs ?? 0} completed / ${task.summary.counts?.failed_runs ?? 0} failed`,
                      meta: formatDateTime(task.updated_at_utc),
                      status: viewMode === 'current' ? currentTaskDisplayStatus(task) : task.status,
                      hint: task.dut_model ?? '未登记待测端'
                    };
                  })}
                  canonicalStatus={false}
                  onSelect={handleSelectTask}
                  selectedId={selectedTask?.benchmark_task_id ?? null}
                />
              ) : standaloneMonitorActive ? (
                <div className="studio-copy-stack">
                  <div className="studio-note-card studio-note-card--highlight">
                    <span className="studio-section-label">独立场景运行</span>
                    <p>
                      {standaloneCurrentRun?.scenario_name ??
                        standaloneNextRun?.scenario_name ??
                        '等待场景进入执行'}
                    </p>
                    <small>
                      {standaloneCurrentRun
                        ? `${standaloneCurrentRun.map_name} / ${standaloneCurrentRun.status}`
                        : standaloneNextRun
                          ? `${standaloneNextRun.map_name} / 排队中`
                          : '当前没有活动场景'}
                    </small>
                  </div>
                  <div className="studio-note-card">
                    <span className="studio-section-label">等待队列</span>
                    {standaloneQueuedRuns.length > 0 ? (
                      standaloneQueuedRuns.slice(0, 6).map((run, index) => (
                        <p key={run.run_id}>
                          {index + 1}. {run.scenario_name} / {run.map_name}
                        </p>
                      ))
                    ) : (
                      <p>当前没有等待中的独立场景。</p>
                    )}
                  </div>
                </div>
              ) : (
                <SelectionList
                  emptyDescription={
                    viewMode === 'current'
                      ? '当前没有活跃批量任务，也没有独立场景运行。'
                      : '当前还没有进入归档的批量任务。'
                  }
                  emptyTitle={viewMode === 'current' ? '无活跃任务' : '无归档任务'}
                  items={[]}
                  canonicalStatus={false}
                  onSelect={handleSelectTask}
                  selectedId={selectedTask?.benchmark_task_id ?? null}
                />
              )}
            </div>
          </DetailPanel>

          {(selectedTask || standaloneMonitorActive) && (
            <DetailPanel
              subtitle={
                selectedTask
                  ? viewMode === 'current'
                    ? '当前任务状态。'
                    : '可重新执行已归档任务。'
                  : '当前独立场景状态。'
              }
              title={
                selectedTask
                  ? viewMode === 'current'
                    ? '当前任务摘要'
                    : '归档任务摘要'
                  : '独立场景摘要'
              }
            >
              {selectedTask ? (
                <div className="studio-copy-stack">
                  <div className="studio-note-card">
                    <span className="studio-section-label">任务信息</span>
                    <p>模板: {selectedTask.benchmark_name}</p>
                    <p>项目: {selectedTask.project_name}</p>
                    <p>待测端: {selectedTask.dut_model ?? '未登记'}</p>
                    <p>批量状态: {selectedTask.status}</p>
                    <p>当前场景状态: {viewMode === 'current' ? displayQueueStatus(currentEntry?.status ?? nextEntry?.status ?? 'QUEUED') : '-'}</p>
                  </div>

                  <div className="studio-two-column">
                    <div className="studio-note-card">
                      <span className="studio-section-label">进度统计</span>
                      <p>计划场景: {selectedTask.planned_run_count}</p>
                      <p>已完成: {selectedTask.summary.counts?.completed_runs ?? 0}</p>
                      <p>失败/取消: {(selectedTask.summary.counts?.failed_runs ?? 0) + (selectedTask.summary.counts?.canceled_runs ?? 0)}</p>
                    </div>

                    {viewMode === 'archive' && (
                      <div className="studio-note-card studio-note-card--highlight">
                        <span className="studio-section-label">再次执行</span>
                        <button
                          className="horizon-button"
                          disabled={rerunMutation.isPending}
                          onClick={() => rerunMutation.mutate(selectedTask.benchmark_task_id)}
                          type="button"
                        >
                          {rerunMutation.isPending ? '重新启动中...' : '再次执行这批任务'}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="studio-copy-stack">
                  <div className="studio-note-card">
                    <span className="studio-section-label">当前执行</span>
                    <p>场景: {standaloneCurrentRun?.scenario_name ?? '当前无活动场景'}</p>
                    <p>地图: {standaloneCurrentRun?.map_name ?? standaloneNextRun?.map_name ?? '等待执行'}</p>
                    <p>状态: {standaloneCurrentRun?.status ?? standaloneNextRun?.status ?? 'UNKNOWN'}</p>
                  </div>
                  <div className="studio-note-card">
                    <span className="studio-section-label">队列概览</span>
                    <p>活动场景: {activeRunCount}</p>
                    <p>等待场景: {queuedRunCount}</p>
                    <p>Executor: {executorStatus}</p>
                  </div>
                </div>
              )}
            </DetailPanel>
          )}
        </div>

        <div className="flex flex-col gap-3">
          <MonitorCanvas
            footer={
              selectedTask ? (
                <div className="grid gap-2 text-sm md:grid-cols-2">
                  <p>当前场景: {currentEntry?.scenario_display_name ?? '当前无活动场景'}</p>
                  <p>下一场景: {nextEntry?.scenario_display_name ?? '无等待场景'}</p>
                  <p>已完成: {selectedTask.summary.counts?.completed_runs ?? 0}</p>
                  <p>失败/取消: {(selectedTask.summary.counts?.failed_runs ?? 0) + (selectedTask.summary.counts?.canceled_runs ?? 0)}</p>
                  {viewMode === 'current' && (
                    <>
                      <p>Viewer 流状态: {streamStatusLabel}</p>
                      <p>画面健康: {streamHealthLabel}</p>
                    </>
                  )}
                </div>
              ) : selectedRun ? (
                <div className="grid gap-2 text-sm md:grid-cols-2">
                  <p>当前场景: {selectedRun.scenario_name}</p>
                  <p>地图: {selectedRun.map_name}</p>
                  <p>状态: {selectedRun.status}</p>
                  <p>等待队列: {standaloneQueuedRuns.length}</p>
                  {viewMode === 'current' && (
                    <>
                      <p>Viewer 流状态: {streamStatusLabel}</p>
                      <p>画面健康: {streamHealthLabel}</p>
                    </>
                  )}
                </div>
              ) : (
                <p className="text-sm">
                  {standaloneMonitorActive ? '独立场景仍在排队，等待当前 run 进入监控。' : '先在左侧选择一个批量任务。'}
                </p>
              )
            }
            media={
              viewerImageUrl ? (
                <img
                  alt="Execution Monitor Snapshot"
                  className="h-[560px] w-full object-cover"
                  src={viewerImageUrl}
                />
              ) : (
                <div className="flex h-[560px] items-center justify-center px-4">
                  <div className="studio-note-card max-w-[420px]">
                    <strong>{monitorEmptyMessage.title}</strong>
                    <p className="mt-1.5">{monitorEmptyMessage.description}</p>
                  </div>
                </div>
              )
            }
            overlay={
              viewMode === 'current' ? (
                <>
                  {(hasFirstPersonView || hasThirdPersonView) && (
                    <div className="project-console__toggle">
                      {hasFirstPersonView && (
                        <button
                          className={
                            selectedViewerView === 'first_person'
                              ? 'project-console__toggle-item project-console__toggle-item--active'
                              : 'project-console__toggle-item'
                          }
                          onClick={() => setSelectedViewerView('first_person')}
                          type="button"
                        >
                          第一视角
                        </button>
                      )}
                      {hasThirdPersonView && (
                        <button
                          className={
                            selectedViewerView === 'third_person'
                              ? 'project-console__toggle-item project-console__toggle-item--active'
                              : 'project-console__toggle-item'
                          }
                          onClick={() => setSelectedViewerView('third_person')}
                          type="button"
                        >
                          第三视角
                        </button>
                      )}
                    </div>
                  )}
                  <button
                    className="horizon-button-secondary"
                    disabled={!selectedRun || stopCurrentRunMutation.isPending}
                    onClick={() => selectedRun && stopCurrentRunMutation.mutate(selectedRun.run_id)}
                    type="button"
                  >
                    {stopCurrentRunMutation.isPending ? '停止中...' : '停止当前场景'}
                  </button>
                  <button
                    className="horizon-button-secondary"
                    disabled={!selectedTask || stopTaskMutation.isPending}
                    onClick={() => selectedTask && stopTaskMutation.mutate(selectedTask.benchmark_task_id)}
                    type="button"
                  >
                    {stopTaskMutation.isPending ? '批量停止中...' : '停止当前批量'}
                  </button>
                  <button
                    className="horizon-button-secondary"
                    disabled={!selectedRun || viewerState !== 'ready'}
                    onClick={() => setViewerRefreshSeed(Date.now())}
                    type="button"
                  >
                    抓取快照
                  </button>
                </>
              ) : undefined
            }
            subtitle={
              viewMode === 'current'
                ? currentEntry
                  ? `${currentEntry.scenario_display_name} / ${truncateMiddle(currentEntry.run_id, 28)}`
                  : selectedRun
                    ? `${selectedRun.scenario_name} / ${truncateMiddle(selectedRun.run_id, 28)}`
                  : '当前没有活动场景'
                : selectedTask
                  ? `${selectedTask.benchmark_name} / 归档视图`
                  : '任务归档'
            }
            title={viewMode === 'current' ? '当前执行画面' : '归档任务概览'}
          />

          {(selectedTask || standaloneMonitorActive) && (
            <DetailPanel
              subtitle={
                selectedTask
                  ? viewMode === 'current'
                    ? '当前场景和等待队列。'
                    : '历史场景执行结果。'
                  : '当前场景和等待队列。'
              }
              title={
                selectedTask
                  ? viewMode === 'current'
                    ? '顺序队列'
                    : '场景执行记录'
                  : '独立场景队列'
              }
            >
              {selectedTask ? (
                selectedTaskQueue.length === 0 ? (
                  <EmptyState description="当前任务还没有 run 队列。" title="无队列数据" />
                ) : viewMode === 'current' ? (
                  <div className="studio-copy-stack">
                    <div className="studio-note-card studio-note-card--highlight">
                      <span className="studio-section-label">当前执行</span>
                      <p>{currentEntry?.scenario_display_name ?? '当前无活动场景'}</p>
                      <small>{currentEntry?.display_map_name ?? '等待首个场景启动'}</small>
                    </div>

                    <div className="studio-note-card">
                      <span className="studio-section-label">等待队列</span>
                      {waitingEntries.length === 0 ? (
                        <p>当前没有等待中的场景。</p>
                      ) : (
                        waitingEntries.slice(0, 6).map((entry) => (
                          <p key={entry.run_id}>
                            {entry.position}. {entry.scenario_display_name} / {displayQueueStatus(entry.status)}
                          </p>
                        ))
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="project-console__table">
                    {selectedTaskQueue.map((entry) => (
                      <div className="project-console__table-row" key={entry.run_id}>
                        <div>
                          <span>{entry.position}. {entry.scenario_display_name}</span>
                          <strong>{entry.display_map_name}</strong>
                        </div>
                        <span>{displayQueueStatus(entry.status)}</span>
                        <small>{entry.error_reason ?? formatDateTime(entry.ended_at_utc)}</small>
                      </div>
                    ))}
                  </div>
                )
              ) : (
                <div className="studio-copy-stack">
                  <div className="studio-note-card studio-note-card--highlight">
                    <span className="studio-section-label">当前执行</span>
                    <p>{standaloneCurrentRun?.scenario_name ?? '当前无活动场景'}</p>
                    <small>{standaloneCurrentRun?.map_name ?? '等待首个场景启动'}</small>
                  </div>

                  <div className="studio-note-card">
                    <span className="studio-section-label">等待队列</span>
                    {standaloneQueuedRuns.length === 0 ? (
                      <p>当前没有等待中的独立场景。</p>
                    ) : (
                      standaloneQueuedRuns.slice(0, 6).map((run, index) => (
                        <p key={run.run_id}>
                          {index + 1}. {run.scenario_name} / {run.map_name}
                        </p>
                      ))
                    )}
                  </div>
                </div>
              )}
            </DetailPanel>
          )}
        </div>

        <div className="flex flex-col gap-3">
          <StatusPanel
            label="Executor"
            note={systemQuery.data?.executor.warning ?? '无额外警告'}
            status={executorStatus}
          />
          <StatusPanel
            label="任务范围"
            note={
              selectedTask
                ? `${selectedTask.planned_run_count} scenes / ${selectedTask.status}`
                : selectedRun
                  ? `${selectedRun.scenario_name} / 独立场景运行`
                : viewMode === 'current'
                  ? '当前未选中活跃任务'
                  : '当前未选中归档任务'
            }
            status={selectedTask?.status ?? selectedRun?.status ?? 'READY'}
          />
          <StatusPanel
            label="当前场景"
            note={currentEntry?.display_map_name ?? selectedRun?.map_name ?? '无活动场景'}
            status={currentEntry?.status ?? selectedRun?.status ?? 'UNKNOWN'}
          />
          <StatusPanel
            label="画面状态"
            note={telemetryItems[5]?.hint ?? '等待画面'}
            status={
              viewMode === 'archive'
                ? 'READY'
                : viewerState === 'error'
                  ? 'FAILED'
                  : viewerState === 'loading'
                    ? 'RUNNING'
                    : viewerState === 'ready'
                      ? 'READY'
                      : 'UNKNOWN'
            }
          />

          {viewMode === 'current' && (
            <DetailPanel
              subtitle="每次点击切到下一个天气预设。"
              title="CARLA Weather"
            >
              <div className="studio-copy-stack">
                <button
                  className="horizon-button"
                  disabled={
                    cycleWeatherMutation.isPending ||
                    !nextWeatherPreset
                  }
                  onClick={() => cycleWeatherMutation.mutate()}
                  type="button"
                >
                  {cycleWeatherMutation.isPending
                    ? '天气切换中...'
                    : `切换天气${nextWeatherPreset ? ` · ${nextWeatherPreset.label}` : ''}`}
                </button>

                <p>
                  {selectedRun
                    ? '会立即切换全局天气。'
                    : '当前没有活动场景，也可以切换全局天气。'}
                </p>

                {cycleWeatherMutation.error && (
                  <p className="text-sm text-rose-600">{cycleWeatherMutation.error.message}</p>
                )}

                {cycleWeatherMutation.data && (
                  <p className="text-sm text-emerald-600">{cycleWeatherMutation.data.message}</p>
                )}
              </div>
            </DetailPanel>
          )}

          <TelemetryPanel items={telemetryItems} subtitle="当前任务与当前场景状态" title="遥测面板" />

          {viewMode === 'current' ? (
            <DetailPanel subtitle="持续更新，优先定位当前活动场景的状态变化与异常" title="事件时间线">
              <EventTimeline
                emptyDescription={
                  selectedRun ? '该 run 还没有事件写入。' : '当前没有可查看事件的活动场景。'
                }
                emptyTitle={selectedRun ? '暂无事件' : '无活动场景'}
                events={selectedRunEventsQuery.data ?? []}
              />
            </DetailPanel>
          ) : (
            <DetailPanel subtitle="查看归档任务处理方式" title="归档说明">
              <div className="studio-copy-stack">
                <p>1. 归档任务会保留原始配置和结果。</p>
                <p>2. 点击“再次执行”会生成新的任务实例。</p>
                <p>3. 历史任务不会被覆盖。</p>
              </div>
            </DetailPanel>
          )}
        </div>
      </div>
    </div>
  );
}
