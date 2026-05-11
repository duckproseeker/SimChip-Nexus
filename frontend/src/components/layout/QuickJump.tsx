import { useEffect, useMemo, useState, type FormEvent } from 'react';

import { useLocation, useNavigate } from 'react-router-dom';
import { HiMiniArrowUpRight, HiMiniMagnifyingGlass, HiMiniRocketLaunch } from 'react-icons/hi2';

import type { NavigationItem } from './navigation';

interface QuickJumpProps {
  navigationItems: NavigationItem[];
}

function normalizeText(value: string) {
  return value.trim().toLowerCase();
}

export function QuickJump({ navigationItems }: QuickJumpProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');

  useEffect(() => {
    setOpen(false);
    setQuery('');
  }, [location.pathname]);

  const normalizedQuery = normalizeText(query);
  const matches = useMemo(() => {
    if (!normalizedQuery) {
      return navigationItems.slice(0, 5);
    }

    return navigationItems.filter((item) => {
      const haystack = [item.label, item.caption, ...item.keywords].join(' ').toLowerCase();
      return haystack.includes(normalizedQuery);
    });
  }, [navigationItems, normalizedQuery]);

  function goToPath(path: string) {
    void navigate(path, { viewTransition: true });
    setOpen(false);
    setQuery('');
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (matches[0]) {
      goToPath(matches[0].to);
      return;
    }

    if (query.trim()) {
      goToPath(`/executions/${encodeURIComponent(query.trim())}`);
    }
  }

  return (
    <div className="relative">
      <button
        className="flex min-h-11 items-center gap-2 rounded-full border border-secondaryGray-200 bg-white/92 px-4 py-2 text-sm font-semibold text-secondaryGray-700 shadow-card transition hover:-translate-y-0.5 hover:border-brand-200 hover:text-brand-700"
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        <HiMiniMagnifyingGlass className="h-4 w-4" />
        全局快速跳转
      </button>

      {open && (
        <div className="absolute right-0 top-[calc(100%+0.75rem)] z-40 w-[min(92vw,420px)] rounded-[28px] border border-white/90 bg-white/96 p-4 shadow-panel backdrop-blur">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-secondaryGray-500">
                Quick Jump
              </p>
              <strong className="mt-2 block text-lg font-extrabold tracking-[-0.03em] text-navy-900">
                模块或执行 ID
              </strong>
              <p className="mt-2 text-sm leading-6 text-secondaryGray-600">
                这里是真正可交互的快速跳转。输入模块关键词，或直接粘贴执行 ID。
              </p>
            </div>
            <button
              className="rounded-full border border-secondaryGray-200 px-3 py-1 text-xs font-bold text-secondaryGray-500 transition hover:border-secondaryGray-300 hover:text-secondaryGray-700"
              onClick={() => setOpen(false)}
              type="button"
            >
              关闭
            </button>
          </div>

          <form className="mt-4 flex gap-3" onSubmit={handleSubmit}>
            <input
              autoFocus
              className="min-w-0 flex-1 rounded-[18px] border border-secondaryGray-200 bg-secondaryGray-50/80 px-4 py-3 text-sm text-navy-900 outline-none transition focus:border-brand-300 focus:bg-white focus:shadow-card"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="输入页面关键词或执行 ID"
              value={query}
            />
            <button className="horizon-button px-5" type="submit">
              跳转
            </button>
          </form>

          <div className="mt-4 grid gap-2">
            {matches.map((item) => (
              <button
                key={item.to}
                className="flex items-center justify-between rounded-[20px] border border-secondaryGray-200 bg-secondaryGray-50/70 px-4 py-3 text-left transition hover:-translate-y-0.5 hover:border-brand-200 hover:bg-brand-50/60"
                onClick={() => goToPath(item.to)}
                type="button"
              >
                <div>
                  <span className="block text-sm font-bold text-navy-900">{item.label}</span>
                  <span className="mt-1 block text-xs text-secondaryGray-500">{item.caption}</span>
                </div>
                <HiMiniArrowUpRight className="h-4 w-4 text-brand-500" />
              </button>
            ))}

            {!matches.length && query.trim() && (
              <button
                className="flex items-center justify-between rounded-[20px] border border-brand-100 bg-brand-50/60 px-4 py-3 text-left transition hover:-translate-y-0.5 hover:shadow-card"
                onClick={() => goToPath(`/executions/${encodeURIComponent(query.trim())}`)}
                type="button"
              >
                <div>
                  <span className="block text-sm font-bold text-navy-900">打开执行详情</span>
                  <span className="mt-1 block text-xs text-secondaryGray-500">{query.trim()}</span>
                </div>
                <HiMiniRocketLaunch className="h-4 w-4 text-brand-500" />
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
