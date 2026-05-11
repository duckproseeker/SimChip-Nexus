export function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return '-';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'short',
    timeStyle: 'medium'
  }).format(date);
}

export function formatRelativeDuration(start: string | null | undefined, end?: string | null) {
  if (!start) {
    return '-';
  }

  const startDate = new Date(start).getTime();
  const endDate = end ? new Date(end).getTime() : Date.now();
  if (Number.isNaN(startDate) || Number.isNaN(endDate)) {
    return '-';
  }

  const totalSeconds = Math.max(0, Math.floor((endDate - startDate) / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return `${hours}h ${minutes}m ${seconds}s`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
}

export function formatNumber(value: number | null | undefined, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '-';
  }
  return value.toFixed(digits);
}

export function formatBytes(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '-';
  }

  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function terminalStatus(status: string) {
  return new Set(['COMPLETED', 'FAILED', 'CANCELED', 'STOPPED']).has(status);
}

export function sortByActivity<T extends { status: string; updated_at_utc?: string | null; created_at_utc?: string | null }>(
  items: T[]
) {
  const activeRank = (status: string) => {
    if (['RUNNING', 'STARTING', 'QUEUED', 'STOPPING', 'BUSY'].includes(status)) {
      return 0;
    }
    if (['CREATED', 'READY', 'DEGRADED'].includes(status)) {
      return 1;
    }
    if (['FAILED', 'ERROR'].includes(status)) {
      return 2;
    }
    return 3;
  };

  return [...items].sort((left, right) => {
    const rankGap = activeRank(left.status) - activeRank(right.status);
    if (rankGap !== 0) {
      return rankGap;
    }

    const leftTime = new Date(left.updated_at_utc ?? left.created_at_utc ?? 0).getTime();
    const rightTime = new Date(right.updated_at_utc ?? right.created_at_utc ?? 0).getTime();
    return rightTime - leftTime;
  });
}

export function truncateMiddle(value: string, keep = 10) {
  if (value.length <= keep * 2 + 3) {
    return value;
  }
  return `${value.slice(0, keep)}...${value.slice(-keep)}`;
}
