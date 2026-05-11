import { useEffect, useState } from 'react';
import clsx from 'clsx';

import { StatusPill } from './StatusPill';

export interface SelectionListItem {
  id: string;
  title: string;
  subtitle?: string;
  meta?: string;
  status?: string | null;
  hint?: string;
}

interface SelectionListProps {
  items: SelectionListItem[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  emptyTitle: string;
  emptyDescription: string;
  canonicalStatus?: boolean;
  maxVisible?: number;
  expandLabel?: string;
  collapseLabel?: string;
}

export function SelectionList({
  items,
  selectedId,
  onSelect,
  emptyTitle,
  emptyDescription,
  canonicalStatus = true,
  maxVisible,
  expandLabel = '展开更多',
  collapseLabel = '收起'
}: SelectionListProps) {
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!maxVisible || items.length <= maxVisible) {
      setExpanded(false);
    }
  }, [items.length, maxVisible]);

  if (items.length === 0) {
    return (
      <div className="selection-list__empty">
        <strong>{emptyTitle}</strong>
        <p>{emptyDescription}</p>
      </div>
    );
  }

  const shouldClamp = Boolean(maxVisible && items.length > maxVisible && !expanded);
  let visibleItems = items;
  if (shouldClamp && maxVisible) {
    visibleItems = items.slice(0, maxVisible);
    if (selectedId && !visibleItems.some((item) => item.id === selectedId)) {
      const selectedItem = items.find((item) => item.id === selectedId);
      if (selectedItem) {
        visibleItems = [...visibleItems.slice(0, maxVisible - 1), selectedItem];
      }
    }
  }

  return (
    <div className="selection-list">
      {visibleItems.map((item) => {
        const active = selectedId === item.id;
        return (
          <button
            key={item.id}
            className={clsx('selection-list__item', active && 'selection-list__item--active')}
            onClick={() => onSelect(item.id)}
            type="button"
          >
            <div className="selection-list__header">
              <strong>{item.title}</strong>
              {item.status && <StatusPill canonical={canonicalStatus} status={item.status} />}
            </div>
            {item.subtitle && <p className="selection-list__subtitle">{item.subtitle}</p>}
            <div className="selection-list__footer">
              {item.meta && <span>{item.meta}</span>}
              {item.hint && <small>{item.hint}</small>}
            </div>
          </button>
        );
      })}

      {maxVisible && items.length > maxVisible && (
        <button
          className="selection-list__toggle"
          onClick={() => setExpanded((value) => !value)}
          type="button"
        >
          {expanded ? collapseLabel : `${expandLabel} (${items.length - maxVisible})`}
        </button>
      )}
    </div>
  );
}
