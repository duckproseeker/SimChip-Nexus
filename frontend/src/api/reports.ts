import { apiRequest, postJson } from './client';
import type { ReportListSchema } from './generated/contracts';
import type { ReportExportPayload, ReportRecord, ReportsWorkspace } from './types';

export function listReports(filters: { benchmarkTaskId?: string; projectId?: string } = {}) {
  return apiRequest<ReportListSchema>('/reports', {
    query: {
      benchmark_task_id: filters.benchmarkTaskId,
      project_id: filters.projectId
    }
  }).then((data) => (data.reports ?? []) as ReportRecord[]);
}

export function getReport(reportId: string) {
  return apiRequest<ReportRecord>(`/reports/${reportId}`);
}

export function getReportsWorkspace() {
  return apiRequest<ReportsWorkspace>('/reports/workspace');
}

export function exportReport(benchmarkTaskId: string) {
  const payload: ReportExportPayload = { benchmark_task_id: benchmarkTaskId };
  return postJson<ReportRecord>('/reports/export', payload);
}
