import { NODE_SPECS } from '../../components/pipeline/nodes';

interface NodeDef { node_id: string; type: string; }
interface EdgeDef { source: string; source_handle: string; target: string; target_handle: string; }

export function validateGraph(nodes: NodeDef[], edges: EdgeDef[]): string[] {
  const errors: string[] = [];
  const nodeMap = new Map(nodes.map(n => [n.node_id, n]));

  if (!nodes.some(n => n.type === 'scene_replay')) {
    errors.push('需要至少一个场景回放节点');
  }

  for (const e of edges) {
    const src = nodeMap.get(e.source);
    const tgt = nodeMap.get(e.target);
    if (!src || !tgt) continue;
    const srcSpec = NODE_SPECS[src.type];
    const tgtSpec = NODE_SPECS[tgt.type];
    if (!srcSpec || !tgtSpec) continue;
    if (e.source_handle !== e.target_handle) {
      errors.push(`端口类型不匹配: ${srcSpec.label} → ${tgtSpec.label}`);
    }
  }

  const inDegree = new Map<string, number>(nodes.map(n => [n.node_id, 0]));
  const adj = new Map<string, string[]>(nodes.map(n => [n.node_id, []]));
  for (const e of edges) {
    adj.get(e.source)?.push(e.target);
    inDegree.set(e.target, (inDegree.get(e.target) ?? 0) + 1);
  }
  const queue = [...inDegree.entries()].filter(([, d]) => d === 0).map(([id]) => id);
  let visited = 0;
  while (queue.length > 0) {
    const nid = queue.shift()!;
    visited++;
    for (const neighbor of adj.get(nid) ?? []) {
      const deg = (inDegree.get(neighbor) ?? 1) - 1;
      inDegree.set(neighbor, deg);
      if (deg === 0) queue.push(neighbor);
    }
  }
  if (visited < nodes.length) {
    errors.push('检测到环路');
  }

  return errors;
}
