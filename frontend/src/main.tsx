import React from 'react';
import ReactDOM from 'react-dom/client';

import { AppProviders } from './app/providers';
import { AppRouter } from './app/router';
import LandingPage from './pages/landing/LandingPage';
import './styles/tailwind.css';
import './styles/globals.css';

function isConsoleRoute(pathname: string) {
  return pathname === '/ui' || pathname.startsWith('/ui/');
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {isConsoleRoute(window.location.pathname) ? (
      <AppProviders>
        <AppRouter />
      </AppProviders>
    ) : (
      <LandingPage />
    )}
  </React.StrictMode>
);
