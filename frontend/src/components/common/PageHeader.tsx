import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  description: string;
  actions?: ReactNode;
  eyebrow?: string;
  chips?: string[];
}

const defaultChips = ['芯片测评平台', 'CARLA 场景仿真', '工程报告'];

export function PageHeader({
  title,
  description,
  actions,
  eyebrow = '芯片评测工作台',
  chips = defaultChips
}: PageHeaderProps) {
  return (
    <header className="page-header">
      <div className="page-header__main">
        <div className="page-header__chips">
          {chips.map((chip) => (
            <span key={chip} className="page-header__chip">
              {chip}
            </span>
          ))}
        </div>
        <span className="page-header__eyebrow">{eyebrow}</span>
        <h1 className="page-header__title" style={{ viewTransitionName: 'page-title' }}>
          {title}
        </h1>
        <p className="page-header__description">{description}</p>
      </div>

      {actions && <div className="page-header__actions">{actions}</div>}
    </header>
  );
}
