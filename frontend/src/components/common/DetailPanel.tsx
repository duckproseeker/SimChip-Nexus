import type { PropsWithChildren, ReactNode } from 'react';
import clsx from 'clsx';

interface DetailPanelProps extends PropsWithChildren {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  className?: string;
  bodyClassName?: string;
}

export function DetailPanel({
  eyebrow,
  title,
  subtitle,
  actions,
  className,
  bodyClassName,
  children
}: DetailPanelProps) {
  return (
    <section className={clsx('detail-panel', className)}>
      <header className="detail-panel__header">
        <div>
          {eyebrow && <span className="detail-panel__eyebrow">{eyebrow}</span>}
          <h2 className="detail-panel__title">{title}</h2>
          {subtitle && <p className="detail-panel__subtitle">{subtitle}</p>}
        </div>
        {actions && <div className="detail-panel__actions">{actions}</div>}
      </header>
      <div className={clsx('detail-panel__body', bodyClassName)}>{children}</div>
    </section>
  );
}
