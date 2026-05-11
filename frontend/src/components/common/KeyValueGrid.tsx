import type { ReactNode } from 'react';

interface KeyValueItem {
  label: string;
  value: ReactNode;
}

interface KeyValueGridProps {
  items: KeyValueItem[];
}

export function KeyValueGrid({ items }: KeyValueGridProps) {
  return (
    <dl className="key-value-grid">
      {items.map((item) => (
        <div key={item.label} className="key-value-grid__item">
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
