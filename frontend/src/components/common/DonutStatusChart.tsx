import { Suspense, lazy } from 'react';

import type { ApexOptions } from 'apexcharts';
import { useTheme } from '../../features/theme/state';

const Chart = lazy(() => import('react-apexcharts'));

interface DonutStatusChartItem {
  label: string;
  value: number;
  color: string;
}

interface DonutStatusChartProps {
  title: string;
  subtitle?: string;
  items: DonutStatusChartItem[];
}

export function DonutStatusChart({ title, subtitle, items }: DonutStatusChartProps) {
  const { resolvedTheme } = useTheme();
  const filteredItems = items.filter((item) => item.value > 0);
  const labels = filteredItems.map((item) => item.label);
  const series = filteredItems.map((item) => item.value);
  const colors = filteredItems.map((item) => item.color);
  const total = series.reduce((sum, value) => sum + value, 0);

  const subtleColor = resolvedTheme === 'dark' ? '#9db0c8' : '#4f647f';
  const strongColor = resolvedTheme === 'dark' ? '#e2e8f0' : '#0f172a';

  const options: ApexOptions = {
    chart: {
      toolbar: { show: false },
      sparkline: { enabled: true },
      foreColor: subtleColor
    },
    stroke: {
      width: 0
    },
    labels,
    colors,
    legend: {
      show: false
    },
    dataLabels: {
      enabled: false
    },
    plotOptions: {
      pie: {
        donut: {
          size: '76%',
          labels: {
            show: true,
            name: {
              show: true,
              offsetY: 18,
              color: subtleColor,
              fontSize: '12px',
              fontWeight: 700
            },
            value: {
              show: true,
              offsetY: -16,
              color: strongColor,
              fontSize: '28px',
              fontWeight: 800,
              formatter: (value) => `${Math.round(Number(value))}`
            },
            total: {
              show: true,
              showAlways: true,
              label: '总量',
              color: subtleColor,
              fontSize: '12px',
              fontWeight: 700,
              formatter: () => `${total}`
            }
          }
        }
      }
    },
    tooltip: {
      theme: resolvedTheme,
      y: {
        formatter: (value) => `${value}`
      }
    }
  };

  return (
    <div className="flex h-full flex-col gap-4">
      <div>
        <h3 className="text-lg font-extrabold tracking-[-0.02em]" style={{ color: 'var(--text)' }}>
          {title}
        </h3>
        {subtitle && (
          <p className="mt-1 text-sm" style={{ color: 'var(--text-soft)' }}>
            {subtitle}
          </p>
        )}
      </div>
      <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)] lg:items-center">
        <div className="mx-auto w-full max-w-[220px]">
          <Suspense
            fallback={
              <div
                className="flex h-[220px] items-center justify-center rounded-[24px] border text-sm"
                style={{ borderColor: 'var(--border)', background: 'var(--surface-subtle)', color: 'var(--text-soft)' }}
              >
                加载图表...
              </div>
            }
          >
            <Chart options={options} series={series} type="donut" height={220} />
          </Suspense>
        </div>
        <div className="flex flex-col gap-3">
          {filteredItems.length === 0 ? (
            <div
              className="rounded-[20px] border p-4 text-sm"
              style={{ borderColor: 'var(--border)', background: 'var(--surface-subtle)', color: 'var(--text-soft)' }}
            >
              暂无状态数据
            </div>
          ) : (
            filteredItems.map((item) => (
              <div
                key={item.label}
                className="flex items-center justify-between rounded-[18px] border px-4 py-3"
                style={{ borderColor: 'var(--border)', background: 'var(--surface-subtle)' }}
              >
                <div className="flex items-center gap-3">
                  <span className="h-3 w-3 rounded-full" style={{ backgroundColor: item.color }} />
                  <span className="text-sm font-semibold" style={{ color: 'var(--text-soft)' }}>
                    {item.label}
                  </span>
                </div>
                <strong className="text-base font-extrabold" style={{ color: 'var(--text)' }}>
                  {item.value}
                </strong>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
