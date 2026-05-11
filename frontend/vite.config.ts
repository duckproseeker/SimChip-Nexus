import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  const backendTarget = env.DEV_API_TARGET || env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
  const apiProxyPaths = [
    '/healthz',
    '/runs',
    '/gateways',
    '/captures',
    '/system',
    '/scenarios',
    '/maps',
    '/evaluation-profiles',
    '/projects',
    '/benchmark-definitions',
    '/benchmark-tasks',
    '/reports',
    '/devices'
  ];
  const httpProxyEntries = apiProxyPaths.reduce<Record<string, any>>((accumulator, path) => {
    accumulator[path] = {
      target: backendTarget,
      changeOrigin: true
    };
    return accumulator;
  }, {});

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      proxy: {
        ...httpProxyEntries,
        '/ws': {
          target: backendTarget,
          ws: true
        }
      }
    },
    preview: {
      host: '0.0.0.0',
      port: 4173
    }
  };
});
