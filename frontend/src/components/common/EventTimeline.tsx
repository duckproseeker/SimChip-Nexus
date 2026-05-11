import type { RunEvent } from '../../api/types';
import { formatDateTime } from '../../lib/format';
import { StatusPill } from './StatusPill';

interface EventTimelineProps {
  events: RunEvent[];
  emptyTitle: string;
  emptyDescription: string;
}

export function EventTimeline({ events, emptyTitle, emptyDescription }: EventTimelineProps) {
  if (events.length === 0) {
    return (
      <div className="timeline-empty">
        <strong>{emptyTitle}</strong>
        <p>{emptyDescription}</p>
      </div>
    );
  }

  return (
    <div className="event-timeline">
      {events.map((event, index) => (
        <article key={`${event.timestamp}-${index}`} className="event-timeline__item">
          <div className="event-timeline__marker" />
          <div className="event-timeline__content">
            <div className="event-timeline__header">
              <strong>{event.event_type}</strong>
              <StatusPill canonical status={event.level} />
            </div>
            <p>{event.message}</p>
            <small>{formatDateTime(event.timestamp)}</small>
          </div>
        </article>
      ))}
    </div>
  );
}
