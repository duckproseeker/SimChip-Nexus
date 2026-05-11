import type { PropsWithChildren, ReactNode } from 'react';

import clsx from 'clsx';

interface PanelProps extends PropsWithChildren {
  eyebrow?: string;
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  className?: string;
  bodyClassName?: string;
}

export function Panel({
  eyebrow,
  title,
  subtitle,
  actions,
  className,
  bodyClassName,
  children
}: PanelProps) {
  return (
    <section className={clsx('panel horizon-card', className)}>
      {(eyebrow || title || subtitle || actions) && (
        <header className="panel__header">
          <div className="panel__copy">
            {eyebrow && <span className="panel__eyebrow">{eyebrow}</span>}
            {title && <h2 className="panel__title">{title}</h2>}
            {subtitle && <p className="panel__subtitle">{subtitle}</p>}
          </div>
          {actions && <div className="panel__actions">{actions}</div>}
        </header>
      )}
      <div className={clsx('panel__body', bodyClassName)}>{children}</div>
    </section>
  );
}
