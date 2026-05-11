import { createBrowserRouter, Navigate, RouterProvider, useParams } from 'react-router-dom';

import { AppShell } from '../components/layout/AppShell';
import { BenchmarksPage } from '../pages/benchmarks/BenchmarksPage';
import { DeviceDetailPage } from '../pages/devices/DeviceDetailPage';
import { DevicesPage } from '../pages/devices/DevicesPage';
import { ExecutionDetailPage } from '../pages/executions/ExecutionDetailPage';
import { ExecutionsPage } from '../pages/executions/ExecutionsPage';
import { ProjectsPage } from '../pages/projects/ProjectsPage';
import { ReportsPage } from '../pages/reports/ReportsPage';
import { ScenarioSetsPage } from '../pages/scenario-sets/ScenarioSetsPage';
import { SettingsPage } from '../pages/settings/SettingsPage';
import { StudioPage } from '../pages/studio/StudioPage';

function LegacyRunRedirect() {
  const { runId = '' } = useParams();
  return <Navigate to={runId ? `/executions/${runId}` : '/executions'} replace />;
}

function LegacyGatewayRedirect() {
  const { gatewayId = '' } = useParams();
  return <Navigate to={gatewayId ? `/devices/${gatewayId}` : '/devices'} replace />;
}

const router = createBrowserRouter(
  [
    {
      path: '/',
      element: <AppShell />,
      children: [
        { index: true, element: <Navigate to="/projects" replace /> },
        { path: 'overview', element: <Navigate to="/projects" replace /> },
        { path: 'projects', element: <ProjectsPage /> },
        { path: 'benchmarks', element: <BenchmarksPage /> },
        { path: 'scenario-sets', element: <ScenarioSetsPage /> },
        { path: 'runs', element: <Navigate to="/executions" replace /> },
        { path: 'runs/:runId', element: <LegacyRunRedirect /> },
        { path: 'executions', element: <ExecutionsPage /> },
        { path: 'executions/:runId', element: <ExecutionDetailPage /> },
        { path: 'reports', element: <ReportsPage /> },
        { path: 'gateways', element: <Navigate to="/devices" replace /> },
        { path: 'gateways/:gatewayId', element: <LegacyGatewayRedirect /> },
        { path: 'captures', element: <Navigate to="/devices" replace /> },
        { path: 'captures/:captureId', element: <Navigate to="/devices" replace /> },
        { path: 'devices', element: <DevicesPage /> },
        { path: 'devices/:gatewayId', element: <DeviceDetailPage /> },
        { path: 'studio', element: <StudioPage /> },
        { path: 'settings', element: <SettingsPage /> }
      ]
    }
  ],
  {
    basename: '/ui'
  }
);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
