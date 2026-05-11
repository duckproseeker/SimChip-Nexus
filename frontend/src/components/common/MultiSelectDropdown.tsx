import { useEffect, useMemo, useRef, useState } from 'react';

export interface MultiSelectDropdownItem {
  id: string;
  label: string;
  note?: string;
}

interface MultiSelectDropdownProps {
  label: string;
  helperText?: string;
  items: MultiSelectDropdownItem[];
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
  emptyDescription?: string;
  maxPreviewItems?: number;
}

function summarizeSelection(items: MultiSelectDropdownItem[], values: string[], maxPreviewItems: number) {
  const selected = items.filter((item) => values.includes(item.id));
  if (selected.length === 0) {
    return null;
  }

  const labels = selected.slice(0, maxPreviewItems).map((item) => item.label);
  if (selected.length <= maxPreviewItems) {
    return labels.join(' / ');
  }

  return `${labels.join(' / ')} +${selected.length - maxPreviewItems}`;
}

export function MultiSelectDropdown({
  label,
  helperText,
  items,
  values,
  onChange,
  placeholder = '请选择',
  emptyDescription = '没有可选项',
  maxPreviewItems = 2
}: MultiSelectDropdownProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    function handlePointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    }

    window.addEventListener('mousedown', handlePointerDown);
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('mousedown', handlePointerDown);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [open]);

  const summary = useMemo(
    () => summarizeSelection(items, values, maxPreviewItems),
    [items, maxPreviewItems, values]
  );

  function handleToggle(value: string) {
    if (values.includes(value)) {
      onChange(values.filter((item) => item !== value));
      return;
    }
    onChange([...values, value]);
  }

  return (
    <div className="field" ref={rootRef}>
      <span>{label}</span>
      <div className="relative">
        <button
          className={[
            'flex min-h-[56px] w-full items-center justify-between gap-3 rounded-2xl border px-4 py-3 text-left transition',
            open
              ? 'border-brand-200 bg-white shadow-card'
              : 'border-secondaryGray-200 bg-secondaryGray-50/80 hover:-translate-y-0.5 hover:shadow-card'
          ].join(' ')}
          onClick={() => setOpen((current) => !current)}
          type="button"
        >
          <div className="min-w-0">
            <strong className="block truncate text-sm font-bold text-navy-900">{summary ?? placeholder}</strong>
            {helperText && <p className="mt-1 truncate text-xs text-secondaryGray-500">{helperText}</p>}
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-flex min-w-8 items-center justify-center rounded-full bg-white px-2 py-1 text-[11px] font-extrabold text-brand-600">
              {values.length}
            </span>
            <span className="text-sm font-bold text-secondaryGray-500">{open ? '收起' : '展开'}</span>
          </div>
        </button>

        {open && (
          <div className="absolute left-0 right-0 top-[calc(100%+10px)] z-20 rounded-[24px] border border-secondaryGray-200 bg-white p-3 shadow-card">
            <div className="mb-3 flex items-center justify-between gap-3 px-1">
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-secondaryGray-500">{label}</p>
              <div className="flex items-center gap-2">
                <button
                  className="rounded-full bg-secondaryGray-100 px-3 py-1 text-xs font-semibold text-secondaryGray-600"
                  onClick={() => onChange(items.map((item) => item.id))}
                  type="button"
                >
                  全选
                </button>
                <button
                  className="rounded-full bg-secondaryGray-100 px-3 py-1 text-xs font-semibold text-secondaryGray-600"
                  onClick={() => onChange([])}
                  type="button"
                >
                  清空
                </button>
              </div>
            </div>

            {items.length === 0 ? (
              <div className="rounded-[18px] border border-dashed border-secondaryGray-200 bg-secondaryGray-50/70 px-4 py-5 text-sm text-secondaryGray-500">
                {emptyDescription}
              </div>
            ) : (
              <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
                {items.map((item) => {
                  const checked = values.includes(item.id);
                  return (
                    <button
                      key={item.id}
                      className={[
                        'flex w-full items-start justify-between gap-3 rounded-[18px] border px-4 py-3 text-left transition',
                        checked
                          ? 'border-brand-200 bg-brand-50/80'
                          : 'border-secondaryGray-200 bg-secondaryGray-50/70 hover:-translate-y-0.5 hover:shadow-card'
                      ].join(' ')}
                      onClick={() => handleToggle(item.id)}
                      type="button"
                    >
                      <div className="min-w-0">
                        <strong className="block truncate text-sm font-bold text-navy-900">{item.label}</strong>
                        {item.note && <p className="mt-1 text-xs leading-5 text-secondaryGray-600">{item.note}</p>}
                      </div>
                      <span
                        className={[
                          'inline-flex h-6 min-w-6 items-center justify-center rounded-full px-2 text-[11px] font-extrabold',
                          checked ? 'bg-brand-500 text-white' : 'bg-white text-secondaryGray-500'
                        ].join(' ')}
                      >
                        {checked ? '已选' : '选择'}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
