import type { ReactNode } from 'react';

import clsx from 'clsx';

interface EmptyStateProps {
  title: string;
  description: string;
  icon?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ title, description, icon, action, className }: EmptyStateProps) {
  return (
    <div className={clsx('empty-state', className)}>
      {icon && <div className="empty-state__icon">{icon}</div>}
      <strong className="empty-state__title">{title}</strong>
      <p className="empty-state__description">{description}</p>
      {action && <div className="empty-state__action">{action}</div>}
    </div>
  );
}
