import { useSyncExternalStore } from 'react';

export interface WorkflowSelectionState {
  projectId: string | null;
  benchmarkDefinitionId: string | null;
  scenarioId: string | null;
  gatewayId: string | null;
  runId: string | null;
}

const STORAGE_KEY = 'simchip-nexus.workflow.selection';
const CHANGE_EVENT = 'simchip-nexus:workflow-selection-change';

const defaultState: WorkflowSelectionState = {
  projectId: null,
  benchmarkDefinitionId: null,
  scenarioId: null,
  gatewayId: null,
  runId: null
};
const defaultStateSerialized = JSON.stringify(defaultState);

let cachedSerialized = defaultStateSerialized;
let cachedSnapshot = defaultState;

function normalizeValue(value: unknown) {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function normalizeState(value: unknown): WorkflowSelectionState {
  if (!value || typeof value !== 'object') {
    return defaultState;
  }

  const input = value as Partial<Record<keyof WorkflowSelectionState, unknown>>;

  return {
    projectId: normalizeValue(input.projectId),
    benchmarkDefinitionId: normalizeValue(input.benchmarkDefinitionId),
    scenarioId: normalizeValue(input.scenarioId),
    gatewayId: normalizeValue(input.gatewayId),
    runId: normalizeValue(input.runId)
  };
}

function readSnapshot() {
  if (typeof window === 'undefined') {
    return defaultState;
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY) ?? defaultStateSerialized;
    if (raw === cachedSerialized) {
      return cachedSnapshot;
    }

    cachedSerialized = raw;
    cachedSnapshot = normalizeState(JSON.parse(raw));
    return cachedSnapshot;
  } catch {
    cachedSerialized = defaultStateSerialized;
    cachedSnapshot = defaultState;
    return defaultState;
  }
}

function emitChange() {
  if (typeof window === 'undefined') {
    return;
  }

  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function writeSnapshot(next: WorkflowSelectionState) {
  const serialized = JSON.stringify(next);
  if (serialized === cachedSerialized) {
    return;
  }

  cachedSerialized = serialized;
  cachedSnapshot = next;

  if (typeof window === 'undefined') {
    return;
  }

  window.localStorage.setItem(STORAGE_KEY, serialized);
  emitChange();
}

export function setWorkflowSelection(partial: Partial<WorkflowSelectionState>) {
  const current = readSnapshot();
  const next = { ...current };

  for (const key of Object.keys(partial) as Array<keyof WorkflowSelectionState>) {
    next[key] = normalizeValue(partial[key]);
  }

  writeSnapshot(next);
}

export function useWorkflowSelection() {
  return useSyncExternalStore(
    (callback) => {
      if (typeof window === 'undefined') {
        return () => undefined;
      }

      const handleChange = () => callback();
      window.addEventListener('storage', handleChange);
      window.addEventListener(CHANGE_EVENT, handleChange);

      return () => {
        window.removeEventListener('storage', handleChange);
        window.removeEventListener(CHANGE_EVENT, handleChange);
      };
    },
    readSnapshot,
    () => defaultState
  );
}
