import { lazy, Suspense } from 'react';

import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom';

import { ErrorBoundary } from '../components/common/ErrorBoundary';
import { AppShell } from '../components/layout/AppShell';

const PipelineListPage   = lazy(() => import('../pages/pipelines/PipelineListPage'));
const PipelineEditorPage = lazy(() => import('../pages/pipelines/PipelineEditorPage'));
const PipelineRunPage    = lazy(() => import('../pages/pipelines/PipelineRunPage'));
const ScenariosPage      = lazy(() => import('../pages/scenarios/ScenariosPage'));
const DatasetsPage       = lazy(() => import('../pages/datasets/DatasetsPage'));

function PageLoader() {
  return <div className="page-loader" aria-label="页面加载中" />;
}

const router = createBrowserRouter(
  [
    {
      path: '/',
      element: <AppShell />,
      children: [
        { index: true, element: <Navigate to="/pipelines" replace /> },
        { path: '*', element: <Navigate to="/pipelines" replace /> },
        {
          path: 'pipelines',
          element: (
            <ErrorBoundary>
              <Suspense fallback={<PageLoader />}>
                <PipelineListPage />
              </Suspense>
            </ErrorBoundary>
          ),
        },
        {
          path: 'pipelines/:id',
          element: (
            <ErrorBoundary>
              <Suspense fallback={<PageLoader />}>
                <PipelineEditorPage />
              </Suspense>
            </ErrorBoundary>
          ),
        },
        {
          path: 'pipelines/:id/run/:eid',
          element: (
            <ErrorBoundary>
              <Suspense fallback={<PageLoader />}>
                <PipelineRunPage />
              </Suspense>
            </ErrorBoundary>
          ),
        },
        {
          path: 'scenarios',
          element: (
            <ErrorBoundary>
              <Suspense fallback={<PageLoader />}>
                <ScenariosPage />
              </Suspense>
            </ErrorBoundary>
          ),
        },
        {
          path: 'datasets',
          element: (
            <ErrorBoundary>
              <Suspense fallback={<PageLoader />}>
                <DatasetsPage />
              </Suspense>
            </ErrorBoundary>
          ),
        },
      ],
    },
  ],
  {
    basename: '/ui',
  }
);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
