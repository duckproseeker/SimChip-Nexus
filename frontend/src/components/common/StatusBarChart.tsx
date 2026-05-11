interface StatusBarChartItem {
  label: string;
  value: number;
  tone: 'success' | 'warning' | 'danger' | 'neutral';
}

interface StatusBarChartProps {
  title: string;
  items: StatusBarChartItem[];
}

export function StatusBarChart({ title, items }: StatusBarChartProps) {
  const maxValue = Math.max(...items.map((item) => item.value), 1);

  return (
    <div className="status-chart">
      <strong>{title}</strong>
      <div className="status-chart__rows">
        {items.map((item) => (
          <div key={item.label} className="status-chart__row">
            <span className="status-chart__label">{item.label}</span>
            <div className="status-chart__track">
              <div
                className={`status-chart__fill status-chart__fill--${item.tone}`}
                style={{ width: `${(item.value / maxValue) * 100}%` }}
              />
            </div>
            <span className="status-chart__value">{item.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
