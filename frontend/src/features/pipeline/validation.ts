import type { Edge, Node } from '@xyflow/react';

export interface ValidationError {
  code: string;
  message: string;
}

export function validateGraph(nodes: Node[], edges: Edge[]): ValidationError[] {
  const errors: ValidationError[] = [];

  const projectNodes = nodes.filter((n) => n.type === 'project');
  if (projectNodes.length === 0) {
    errors.push({ code: 'NO_PROJECT', message: 'Add a Project node to the canvas' });
  } else if (projectNodes.length > 1) {
    errors.push({ code: 'MULTIPLE_PROJECTS', message: 'Only one Project node is allowed' });
  }

  const runNodes = nodes.filter((n) => n.type === 'run');
  for (const runNode of runNodes) {
    const incomingHandles = new Set(
      edges.filter((e) => e.target === runNode.id).map((e) => e.targetHandle)
    );
    if (!incomingHandles.has('scenario_config')) {
      errors.push({ code: 'MISSING_SCENARIO', message: 'Run node needs a ScenarioConfig connection' });
    }
    if (!incomingHandles.has('sensor_profile_id')) {
      errors.push({ code: 'MISSING_SENSOR', message: 'Run node needs a SensorProfile connection' });
    }
  }

  return errors;
}
