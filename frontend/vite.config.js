var __assign = (this && this.__assign) || function () {
    __assign = Object.assign || function(t) {
        for (var s, i = 1, n = arguments.length; i < n; i++) {
            s = arguments[i];
            for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p))
                t[p] = s[p];
        }
        return t;
    };
    return __assign.apply(this, arguments);
};
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig(function (_a) {
    var mode = _a.mode;
    var env = loadEnv(mode, '.', '');
    var backendTarget = env.DEV_API_TARGET || env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
    var apiProxyPaths = [
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
    var httpProxyEntries = apiProxyPaths.reduce(function (accumulator, path) {
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
            proxy: __assign(__assign({}, httpProxyEntries), { '/ws': {
                    target: backendTarget,
                    ws: true
                } })
        },
        preview: {
            host: '0.0.0.0',
            port: 4173
        }
    };
});
