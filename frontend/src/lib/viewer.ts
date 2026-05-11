export function buildViewerSocketUrl(streamWsPath: string, viewId: string) {
  const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL;
  const httpBase = configuredApiBaseUrl
    ? new URL(configuredApiBaseUrl, window.location.origin)
    : new URL(window.location.origin);
  const websocketBase = new URL(httpBase.toString());
  websocketBase.protocol = websocketBase.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = new URL(streamWsPath, websocketBase);
  url.searchParams.set('view', viewId);
  return url.toString();
}
