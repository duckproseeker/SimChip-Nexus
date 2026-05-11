import type { ReactNode } from 'react';
import clsx from 'clsx';

interface CompactPageHeaderProps {
  stepLabel: string;
  title: string;
  description: string;
  contextSummary?: string;
  actions?: ReactNode;
  className?: string;
}

export function CompactPageHeader({
  stepLabel,
  title,
  description,
  contextSummary,
  actions,
  className
}: CompactPageHeaderProps) {
  return (
    <header className={clsx('compact-page-header', className)}>
      <div className="compact-page-header__main">
        <span className="compact-page-header__step">{stepLabel}</span>
        <h1 className="compact-page-header__title" style={{ viewTransitionName: 'page-title' }}>
          {title}
        </h1>
        <p className="compact-page-header__description">{description}</p>
      </div>

      <div className="compact-page-header__side">
        {contextSummary && (
          <div className="compact-page-header__context-block">
            <span className="compact-page-header__context-label">当前上下文</span>
            <p className="compact-page-header__context">{contextSummary}</p>
          </div>
        )}
        {actions && <div className="compact-page-header__actions">{actions}</div>}
      </div>
    </header>
  );
}
