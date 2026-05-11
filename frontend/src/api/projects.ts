import { apiRequest } from './client';
import type { ProjectRecord, ProjectWorkspace } from './types';

export function listProjects() {
  return apiRequest<{ projects: ProjectRecord[] }>('/projects').then((data) => data.projects);
}

export function getProject(projectId: string) {
  return apiRequest<ProjectRecord>(`/projects/${projectId}`);
}

export function getProjectWorkspace(projectId: string) {
  return apiRequest<ProjectWorkspace>(`/projects/${projectId}/workspace`);
}
