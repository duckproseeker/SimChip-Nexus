import { Link } from 'react-router-dom';
import clsx from 'clsx';
import { HiMiniCheckBadge, HiMiniChevronRight } from 'react-icons/hi2';

interface WorkflowProgressItem {
  to: string;
  label: string;
  caption: string;
  state: 'current' | 'complete' | 'upcoming';
  detail?: string | null;
}

interface WorkflowContextBadge {
  label: string;
  value: string;
}

interface WorkflowProgressProps {
  items: WorkflowProgressItem[];
  contextBadges: WorkflowContextBadge[];
}

export function WorkflowProgress({ items, contextBadges }: WorkflowProgressProps) {
  return (
    <section className="overflow-hidden rounded-[30px] border border-white/90 bg-white/92 px-4 py-4 shadow-card backdrop-blur md:px-5">
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[11px] font-extrabold uppercase tracking-[0.2em] text-secondaryGray-500">
              Workflow
            </p>
            <h3 className="mt-2 text-lg font-extrabold tracking-[-0.03em] text-navy-900">
              项目到报告的单一路径
            </h3>
          </div>
          <span className="rounded-full border border-brand-100 bg-brand-50/80 px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.14em] text-brand-700">
            当前链路
          </span>
        </div>

        <div className="flex gap-2 overflow-x-auto pb-1">
          {items.map((item, index) => (
            <div key={item.to} className="flex min-w-[220px] flex-1 items-stretch gap-2">
              <Link
                className={clsx(
                  'group flex min-w-0 flex-1 items-start gap-3 rounded-[24px] border px-4 py-4 transition',
                  item.state === 'current' && 'border-brand-200 bg-brand-50/80 shadow-card',
                  item.state === 'complete' && 'border-emerald-100 bg-emerald-50/80',
                  item.state === 'upcoming' && 'border-secondaryGray-200 bg-secondaryGray-50/70 hover:border-brand-100 hover:bg-white'
                )}
                to={item.to}
                viewTransition
              >
                <div
                  className={clsx(
                    'flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl text-sm font-extrabold',
                    item.state === 'current' && 'bg-brand-600 text-white shadow-glow',
                    item.state === 'complete' && 'bg-emerald-500 text-white',
                    item.state === 'upcoming' && 'bg-white text-secondaryGray-600'
                  )}
                >
                  {item.state === 'complete' ? <HiMiniCheckBadge className="h-5 w-5" /> : index + 1}
                </div>
                <div className="min-w-0">
                  <span className="block text-sm font-bold text-navy-900">{item.label}</span>
                  <span className="mt-1 block text-xs leading-5 text-secondaryGray-500">{item.caption}</span>
                  <span
                    className={clsx(
                      'mt-2 block truncate text-xs font-semibold',
                      item.state === 'current' && 'text-brand-700',
                      item.state === 'complete' && 'text-emerald-700',
                      item.state === 'upcoming' && 'text-secondaryGray-500'
                    )}
                  >
                    {item.detail ?? '等待选择'}
                  </span>
                </div>
              </Link>

              {index < items.length - 1 && (
                <div className="hidden items-center justify-center lg:flex">
                  <HiMiniChevronRight className="h-4 w-4 text-secondaryGray-400" />
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-2">
          {contextBadges.map((badge) => (
            <div
              key={badge.label}
              className="rounded-full border border-secondaryGray-200 bg-secondaryGray-50/80 px-3 py-2 text-xs text-secondaryGray-600"
            >
              <span className="font-extrabold uppercase tracking-[0.14em] text-secondaryGray-500">
                {badge.label}
              </span>
              <span className="ml-2 font-semibold text-navy-900">{badge.value}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
