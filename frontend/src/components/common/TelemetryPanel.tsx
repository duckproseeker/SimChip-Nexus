import type { ReactNode } from 'react';

interface TelemetryItem {
  label: string;
  value: ReactNode;
  hint?: string;
}

interface TelemetryPanelProps {
  title: string;
  subtitle?: string;
  items: TelemetryItem[];
}

export function TelemetryPanel({ title, subtitle, items }: TelemetryPanelProps) {
  return (
    <section className="telemetry-panel">
      <header className="telemetry-panel__header">
        <h3>{title}</h3>
        {subtitle && <p>{subtitle}</p>}
      </header>
      <div className="telemetry-panel__body">
        {items.map((item) => (
          <div key={item.label} className="telemetry-panel__item">
            <span>{item.label}</span>
            <strong>{item.value}</strong>
            {item.hint && <small>{item.hint}</small>}
          </div>
        ))}
      </div>
    </section>
  );
}
