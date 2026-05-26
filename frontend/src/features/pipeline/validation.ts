import type { Edge, Node } from '@xyflow/react';

export interface ValidationError {
  code: string;
  message: string;
}

export function validateGraph(nodes: Node[], edges: Edge[]): ValidationError[] {
  const errors: ValidationError[] = [];

  const projectNodes = nodes.filter((n) => n.type === 'project');
  if (projectNodes.length === 0) {
    errors.push({ code: 'NO_PROJECT', message: '请添加一个项目节点' });
  } else if (projectNodes.length > 1) {
    errors.push({ code: 'MULTIPLE_PROJECTS', message: '只允许一个项目节点' });
  }

  const liveRunNodes = nodes.filter((n) => n.type === 'live_run');
  for (const run of liveRunNodes) {
    const handles = new Set(edges.filter((e) => e.target === run.id).map((e) => e.targetHandle));
    if (!handles.has('project'))  errors.push({ code: 'MISSING_PROJECT',  message: '实时仿真节点缺少项目连接' });
    if (!handles.has('scenario')) errors.push({ code: 'MISSING_SCENARIO', message: '实时仿真节点缺少场景连接' });
    if (!handles.has('map'))      errors.push({ code: 'MISSING_MAP',      message: '实时仿真节点缺少地图连接' });
    if (!handles.has('weather'))  errors.push({ code: 'MISSING_WEATHER',  message: '实时仿真节点缺少天气连接' });
    if (!handles.has('sensor'))   errors.push({ code: 'MISSING_SENSOR',   message: '实时仿真节点至少需要一个传感器' });
  }

  const replayRunNodes = nodes.filter((n) => n.type === 'replay_run');
  for (const run of replayRunNodes) {
    const handles = new Set(edges.filter((e) => e.target === run.id).map((e) => e.targetHandle));
    if (!handles.has('project'))   errors.push({ code: 'MISSING_PROJECT',   message: '录制回放节点缺少项目连接' });
    if (!handles.has('recording')) errors.push({ code: 'MISSING_RECORDING', message: '录制回放节点缺少场景录制连接' });
    if (!handles.has('sensor'))    errors.push({ code: 'MISSING_SENSOR',    message: '录制回放节点至少需要一个传感器' });
  }

  return errors;
}
