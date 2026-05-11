import { Link } from 'react-router-dom';
import clsx from 'clsx';
import { HiCheck } from 'react-icons/hi2';

interface WorkflowStepperItem {
  to: string;
  label: string;
  state: 'current' | 'complete' | 'upcoming';
  detail?: string | null;
}

interface WorkflowStepperProps {
  items: WorkflowStepperItem[];
  compact?: boolean;
}

export function WorkflowStepper({ items, compact = false }: WorkflowStepperProps) {
  return (
    <nav className={clsx('workflow-stepper', compact && 'workflow-stepper--compact')} aria-label="Workflow">
      {items.map((item, index) => (
        <div key={item.to} className="workflow-stepper__row">
          <Link className={clsx('workflow-stepper__item', `workflow-stepper__item--${item.state}`)} to={item.to} viewTransition>
            <span className="workflow-stepper__index">
              {item.state === 'complete' ? <HiCheck className="h-3.5 w-3.5" /> : index + 1}
            </span>
            <span className="workflow-stepper__copy">
              <strong>{item.label}</strong>
              {!compact && <small>{item.detail ?? '待选择'}</small>}
            </span>
          </Link>
          {index < items.length - 1 && <span className="workflow-stepper__connector" />}
        </div>
      ))}
    </nav>
  );
}
