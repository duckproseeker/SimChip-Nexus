import { StatusPill } from './StatusPill';

interface StatusPanelProps {
  label: string;
  status: string;
  note?: string;
}

export function StatusPanel({ label, status, note }: StatusPanelProps) {
  return (
    <div className="status-panel">
      <div className="status-panel__header">
        <span>{label}</span>
        <StatusPill status={status} />
      </div>
      {note && <p>{note}</p>}
    </div>
  );
}
