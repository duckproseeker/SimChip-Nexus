import { useState } from 'react';

import { NavLink, Outlet, useLocation } from 'react-router-dom';
import clsx from 'clsx';

import { navigation, navigationGroups } from './navigation';
import { ThemeModeSwitch } from './ThemeModeSwitch';

function isRouteActive(pathname: string, target: string) {
  return pathname === target || pathname.startsWith(`${target}/`);
}

export function AppShell() {
  const location = useLocation();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const currentItem =
    navigation.find((item) => isRouteActive(location.pathname, item.to)) ?? navigation[0];

  return (
    <div className={clsx('console-shell', sidebarCollapsed && 'console-shell--collapsed')}>
      <aside className="console-sidebar">
        <div className="console-sidebar__brand console-sidebar__brand--minimal">
          <div>
            <span className="console-sidebar__eyebrow">SimChip Nexus</span>
            <h1>芯境智测平台</h1>
          </div>
          <button
            className="console-sidebar__collapse"
            onClick={() => setSidebarCollapsed((value) => !value)}
            type="button"
          >
            {sidebarCollapsed ? '展开' : '收起'}
          </button>
        </div>

        <div className="console-sidebar__nav">
          {navigationGroups.map((group) => (
            <section key={group.id} className="console-nav-group">
              <p className="console-nav-group__label">{group.label}</p>
              <nav className="console-nav-group__items">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <NavLink
                      key={item.to}
                      className={({ isActive }) =>
                        ['console-nav-item', isActive ? 'console-nav-item--active' : ''].join(' ')
                      }
                      to={item.to}
                      viewTransition
                    >
                      <Icon className="console-nav-item__icon" />
                      <span className="console-nav-item__copy">
                        <strong>{item.label}</strong>
                        <small>{item.caption}</small>
                      </span>
                    </NavLink>
                  );
                })}
              </nav>
            </section>
          ))}
        </div>
      </aside>

      <div className="console-main">
        <header className="console-topbar console-topbar--minimal">
          <div className="console-topbar__headline">
            <span className="console-topbar__eyebrow">SimChip Nexus 控制台</span>
            <h2 style={{ viewTransitionName: 'shell-current-page' }}>{currentItem.label}</h2>
          </div>

          <div className="console-topbar__actions">
            <ThemeModeSwitch />
          </div>
        </header>

        <main className="console-main__content">
          <div className="route-stage" key={location.pathname}>
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
