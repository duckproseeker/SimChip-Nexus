import { useMemo, useState, type FormEvent } from 'react';

import { useNavigate } from 'react-router-dom';
import { HiMiniCommandLine, HiMiniMagnifyingGlass, HiMiniChevronDown, HiMiniChevronUp } from 'react-icons/hi2';
import clsx from 'clsx';

import type { NavigationItem } from './navigation';

interface ContextBadge {
  label: string;
  value: string;
}

interface ContextBarProps {
  badges: ContextBadge[];
  navigationItems: NavigationItem[];
  compact?: boolean;
}

function normalize(value: string) {
  return value.trim().toLowerCase();
}

export function ContextBar({ badges, navigationItems, compact = false }: ContextBarProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [searchExpanded, setSearchExpanded] = useState(!compact);

  const matches = useMemo(() => {
    const normalized = normalize(query);
    if (!normalized) {
      return navigationItems.slice(0, 5);
    }
    return navigationItems.filter((item) => {
      const haystack = [item.label, item.caption, ...item.keywords].join(' ').toLowerCase();
      return haystack.includes(normalized);
    });
  }, [navigationItems, query]);

  function goTo(path: string) {
    void navigate(path, { viewTransition: true });
    setQuery('');
    if (compact) {
      setSearchExpanded(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const normalized = normalize(query);
    if (!normalized) {
      return;
    }

    const firstMatch = matches[0];
    if (firstMatch) {
      goTo(firstMatch.to);
      return;
    }

    goTo(`/executions/${encodeURIComponent(query.trim())}`);
  }

  const visibleBadges = compact ? badges.slice(0, 4) : badges;

  return (
    <section className={clsx('context-bar', compact && 'context-bar--compact')}>
      <div className="context-bar__summary">
        {visibleBadges.map((badge) => (
          <div key={badge.label} className="context-bar__badge">
            <span>{badge.label}</span>
            <strong>{badge.value}</strong>
          </div>
        ))}
      </div>

      <div className="context-bar__search">
        {compact && (
          <button
            className="context-bar__compact-toggle"
            onClick={() => setSearchExpanded((value) => !value)}
            type="button"
          >
            <span>Command</span>
            {searchExpanded ? <HiMiniChevronUp /> : <HiMiniChevronDown />}
          </button>
        )}

        {searchExpanded && (
          <form className="context-bar__form" onSubmit={handleSubmit}>
            <HiMiniMagnifyingGlass className="context-bar__icon" />
            <input
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索模块，或输入执行 ID 直达"
              value={query}
            />
            <button type="submit">
              <HiMiniCommandLine />
              Command
            </button>
          </form>
        )}
        {searchExpanded && query.trim() && (
          <div className="context-bar__matches">
            {matches.length === 0 ? (
              <button onClick={() => goTo(`/executions/${encodeURIComponent(query.trim())}`)} type="button">
                打开执行 ID: {query.trim()}
              </button>
            ) : (
              matches.slice(0, 4).map((item) => (
                <button key={item.to} onClick={() => goTo(item.to)} type="button">
                  <strong>{item.label}</strong>
                  <span>{item.caption}</span>
                </button>
              ))
            )}
          </div>
        )}
      </div>
    </section>
  );
}
