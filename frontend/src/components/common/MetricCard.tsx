import type { ReactNode } from 'react';

import clsx from 'clsx';

interface MetricCardProps {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  accent?: 'blue' | 'violet' | 'teal' | 'orange' | 'rose';
}

const accentClasses: Record<NonNullable<MetricCardProps['accent']>, string> = {
  blue: 'from-brand-500 to-accent-500',
  violet: 'from-violet-500 to-indigo-500',
  teal: 'from-emerald-500 to-cyan-400',
  orange: 'from-amber-400 to-orange-500',
  rose: 'from-rose-400 to-rose-500'
};

export function MetricCard({ label, value, hint, accent = 'blue' }: MetricCardProps) {
  return (
    <div className="metric-card horizon-card">
      <div className={clsx('metric-card__accent bg-gradient-to-r', accentClasses[accent])} />
      <p className="metric-card__label">{label}</p>
      <strong className="metric-card__value">{value}</strong>
      {hint && <span className="metric-card__hint">{hint}</span>}
    </div>
  );
}
