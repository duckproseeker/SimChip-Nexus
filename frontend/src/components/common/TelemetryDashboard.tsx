import React, { useEffect, useMemo, useState } from 'react';
import Chart from 'react-apexcharts';
import { metricNumber } from '../../lib/platform';

interface TelemetryDashboardProps {
  deviceMetrics: any;
  runActive: boolean;
  sampleTimestampUtc?: string | null;
}

interface TelemetryPoint {
  time: number;
  fps: number | null;
  latency: number | null;
  temp: number | null;
}

interface MetricSeriesConfig {
  key: 'fps' | 'latency' | 'temp';
  name: string;
  color: string;
  axisTitle: string;
  formatter: (value: number) => string;
  min?: number;
  max?: number;
}

export function TelemetryDashboard({
  deviceMetrics,
  runActive,
  sampleTimestampUtc
}: TelemetryDashboardProps) {
  const [history, setHistory] = useState<TelemetryPoint[]>([]);

  const snapshot = useMemo(
    () => ({
      fps: metricNumber(deviceMetrics, ['output_fps', 'inference_fps', 'render_fps']),
      latency: metricNumber(deviceMetrics, ['avg_latency_ms', 'latency_ms', 'p95_latency_ms']),
      temp: metricNumber(deviceMetrics, ['temperature_c', 'soc_temp_c', 'cpu_temp_c', 'board_temp_c'])
    }),
    [deviceMetrics]
  );

  const hasTelemetry = snapshot.fps !== null || snapshot.latency !== null || snapshot.temp !== null;

  useEffect(() => {
    if (!deviceMetrics || !hasTelemetry) return;

    setHistory((prev) => {
      const ts = new Date(
        sampleTimestampUtc ||
          deviceMetrics.dut_received_at_utc ||
          deviceMetrics.timestamp_utc ||
          Date.now()
      ).getTime();
      const last = prev[prev.length - 1];
      if (last && last.time === ts) {
        return prev;
      }

      const point: TelemetryPoint = {
        time: ts,
        fps: snapshot.fps,
        latency: snapshot.latency,
        temp: snapshot.temp
      };

      const next = [...prev, point];
      if (next.length > 60) next.shift(); // 3 minutes window
      return next;
    });
  }, [deviceMetrics, hasTelemetry, sampleTimestampUtc, snapshot.fps, snapshot.latency, snapshot.temp]);

  const calcStats = (key: 'fps' | 'latency' | 'temp') => {
    const snapshotValue = snapshot[key];
    if (history.length === 0) {
      return {
        current: snapshotValue !== null ? snapshotValue.toFixed(1) : '--',
        avg: '--',
        range: '--',
        trend: runActive ? '采集中' : '快照'
      };
    }

    const current = history[history.length - 1][key] ?? snapshotValue;
    
    // Last 1 minute window (approx 12 points at 5s intervals)
    const window = history.slice(-12).map(h => h[key]).filter((v): v is number => v !== null);
    if (window.length < 2) {
      return { 
        current: current !== null ? current.toFixed(1) : '--', 
        avg: '--', 
        range: '--', 
        trend: runActive ? '采集中' : '快照'
      };
    }

    const avgNum = window.reduce((a,b) => a+b, 0) / window.length;
    const min = Math.min(...window);
    const max = Math.max(...window);
    
    const halfLen = Math.floor(window.length / 2);
    const oldWindow = window.slice(0, halfLen);
    const newWindow = window.slice(halfLen);
    
    const oldAvg = oldWindow.length ? oldWindow.reduce((a,b) => a+b, 0) / oldWindow.length : avgNum;
    const newAvg = newWindow.length ? newWindow.reduce((a,b) => a+b, 0) / newWindow.length : avgNum;
    
    let trend = '持平';
    // Use a small 3% threshold for trend to avoid jitter
    if (newAvg > oldAvg * 1.03) trend = '上升';
    else if (newAvg < oldAvg * 0.97) trend = '下降';

    return {
        current: current !== null ? current.toFixed(1) : '--',
        avg: avgNum.toFixed(1),
        range: `${min.toFixed(1)} ~ ${max.toFixed(1)}`,
        trend
    };
  };

  const fpsStats = calcStats('fps');
  const latStats = calcStats('latency');
  const tempStats = calcStats('temp');

  const seriesConfigs: MetricSeriesConfig[] = useMemo(
    () => [
      {
        key: 'fps',
        name: '推理 FPS',
        color: '#8b5cf6',
        axisTitle: 'FPS',
        formatter: (value) => value.toFixed(0),
        min: 0,
        max: 40
      },
      {
        key: 'latency',
        name: '延迟 (ms)',
        color: '#f97316',
        axisTitle: '延迟 (ms)',
        formatter: (value) => value.toFixed(0),
        min: 0
      },
      {
        key: 'temp',
        name: '芯片温度 (°C)',
        color: '#0ea5e9',
        axisTitle: '温度 (°C)',
        formatter: (value) => value.toFixed(0),
        min: 30,
        max: 85
      }
    ],
    []
  );

  const chartSeries = useMemo(() => {
    return seriesConfigs
      .map((config) => ({
        config,
        data: history
          .filter((point) => point[config.key] !== null)
          .map((point) => [point.time, point[config.key] as number] as [number, number])
      }))
      .filter((entry) => entry.data.length > 0);
  }, [history, seriesConfigs]);

  const unifiedOptions: ApexCharts.ApexOptions = useMemo(
    () => ({
      chart: {
        type: 'area',
        animations: { enabled: false },
        toolbar: { show: false },
        background: 'transparent'
      },
      theme: { mode: 'light' },
      xaxis: { type: 'datetime', labels: { datetimeUTC: false } },
      yaxis: chartSeries.map((entry, index) => ({
        seriesName: entry.config.name,
        min: entry.config.min,
        max: entry.config.max,
        opposite: index > 0,
        axisBorder: { show: true, color: entry.config.color },
        axisTicks: { show: true },
        title: { style: { color: entry.config.color }, text: entry.config.axisTitle },
        labels: {
          style: { colors: entry.config.color },
          formatter: (value) => entry.config.formatter(value)
        }
      })),
      dataLabels: { enabled: false },
      stroke: { curve: 'smooth', width: 3 },
      fill: {
        type: 'gradient',
        gradient: {
          shadeIntensity: 1,
          inverseColors: false,
          opacityFrom: 0.56,
          opacityTo: 0.16,
          stops: [0, 90, 100]
        }
      },
      colors: chartSeries.map((entry) => entry.config.color),
      tooltip: {
        shared: true,
        intersect: false,
        x: { format: 'HH:mm:ss' }
      },
      legend: { position: 'top' },
      noData: { text: '等待更多遥测点' }
    }),
    [chartSeries]
  );

  if (!deviceMetrics || !hasTelemetry) {
    return <div className="text-sm text-text-muted">此网关尚无遥测体征。</div>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-[18px] border border-border-glass bg-[var(--surface-glass)] px-5 py-4">
          <div className="flex justify-between items-center mb-3">
            <span className="text-sm font-bold text-text">推理 FPS</span>
            <span className="rounded-full border border-border-glass bg-[var(--surface-soft)] px-2 py-1 text-xs font-semibold text-text-muted">
              近 1 分钟趋势: {fpsStats.trend}
            </span>
          </div>
          <div className="flex flex-col gap-1 text-sm text-text-muted">
            <div className="flex justify-between"><span className="text-text-muted">当前值</span><strong className="text-text">{fpsStats.current}</strong></div>
            <div className="flex justify-between"><span className="text-text-muted">平均值</span><strong className="text-text">{fpsStats.avg}</strong></div>
            <div className="flex justify-between"><span className="text-text-muted">波动带</span><strong className="text-text">{fpsStats.range}</strong></div>
          </div>
        </div>

        <div className="rounded-[18px] border border-border-glass bg-[var(--surface-glass)] px-5 py-4">
          <div className="flex justify-between items-center mb-3">
            <span className="text-sm font-bold text-text">端到端延迟 (ms)</span>
            <span className="rounded-full border border-border-glass bg-[var(--surface-soft)] px-2 py-1 text-xs font-semibold text-text-muted">
              近 1 分钟趋势: {latStats.trend}
            </span>
          </div>
          <div className="flex flex-col gap-1 text-sm text-text-muted">
            <div className="flex justify-between"><span className="text-text-muted">当前值</span><strong className="text-text">{latStats.current}</strong></div>
            <div className="flex justify-between"><span className="text-text-muted">平均值</span><strong className="text-text">{latStats.avg}</strong></div>
            <div className="flex justify-between"><span className="text-text-muted">波动带</span><strong className="text-text">{latStats.range}</strong></div>
          </div>
        </div>

        <div className="rounded-[18px] border border-border-glass bg-[var(--surface-glass)] px-5 py-4">
          <div className="flex justify-between items-center mb-3">
            <span className="text-sm font-bold text-text">芯片温度 (°C)</span>
            <span className="rounded-full border border-border-glass bg-[var(--surface-soft)] px-2 py-1 text-xs font-semibold text-text-muted">
              近 1 分钟趋势: {tempStats.trend}
            </span>
          </div>
          <div className="flex flex-col gap-1 text-sm text-text-muted">
            <div className="flex justify-between"><span className="text-text-muted">当前值</span><strong className="text-text">{tempStats.current}</strong></div>
            <div className="flex justify-between"><span className="text-text-muted">平均值</span><strong className="text-text">{tempStats.avg}</strong></div>
            <div className="flex justify-between"><span className="text-text-muted">波动带</span><strong className="text-text">{tempStats.range}</strong></div>
          </div>
        </div>
      </div>

      <div className="rounded-[18px] border border-border-glass bg-[var(--surface-soft)] p-4">
        <h4 className="mb-2 text-sm font-bold text-text">统一时间序列观测</h4>
        <div style={{ height: '350px' }}>
          <Chart
            options={unifiedOptions}
            series={chartSeries.map((entry) => ({ name: entry.config.name, data: entry.data }))}
            type="area"
            height="100%"
          />
        </div>
      </div>
    </div>
  );
}
