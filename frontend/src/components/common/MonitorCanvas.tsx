import type { ReactNode } from 'react';

interface MonitorCanvasProps {
  title: string;
  subtitle: string;
  media: ReactNode;
  footer?: ReactNode;
  overlay?: ReactNode;
}

export function MonitorCanvas({ title, subtitle, media, footer, overlay }: MonitorCanvasProps) {
  return (
    <section className="monitor-canvas">
      <header className="monitor-canvas__header">
        <div>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
        {overlay && <div className="monitor-canvas__overlay">{overlay}</div>}
      </header>
      <div className="monitor-canvas__media">{media}</div>
      {footer && <footer className="monitor-canvas__footer">{footer}</footer>}
    </section>
  );
}
