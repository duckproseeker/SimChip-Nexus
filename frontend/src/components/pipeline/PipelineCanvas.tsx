import { useCallback } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  useReactFlow,
  type Connection,
  type EdgeChange,
  type NodeChange,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { usePipelineStore } from '../../features/pipeline/store';
import { ProjectNode } from './nodes/ProjectNode';
import { ReportNode } from './nodes/ReportNode';
import { ScenarioNode } from './nodes/ScenarioNode';
import { MapNode } from './nodes/MapNode';
import { WeatherNode } from './nodes/WeatherNode';
import { RecordingNode } from './nodes/RecordingNode';
import { SensorCameraNode } from './nodes/SensorCameraNode';
import { SensorLidarNode } from './nodes/SensorLidarNode';
import { SensorRadarNode } from './nodes/SensorRadarNode';
import { SensorGnssNode } from './nodes/SensorGnssNode';
import { SensorImuNode } from './nodes/SensorImuNode';
import { LiveRunNode } from './nodes/LiveRunNode';
import { ReplayRunNode } from './nodes/ReplayRunNode';

const NODE_TYPE_MAP = {
  project: ProjectNode,
  scenario: ScenarioNode,
  map: MapNode,
  weather: WeatherNode,
  recording: RecordingNode,
  sensor_camera: SensorCameraNode,
  sensor_lidar: SensorLidarNode,
  sensor_radar: SensorRadarNode,
  sensor_gnss: SensorGnssNode,
  sensor_imu: SensorImuNode,
  live_run: LiveRunNode,
  replay_run: ReplayRunNode,
  report: ReportNode,
} as const;

let _nodeIdCounter = 1;

export function PipelineCanvas() {
  const { nodes, edges, setNodes, setEdges, setSelectedNodeId } = usePipelineStore();
  const { screenToFlowPosition } = useReactFlow();

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => setNodes(applyNodeChanges(changes, nodes)),
    [nodes, setNodes]
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => setEdges(applyEdgeChanges(changes, edges)),
    [edges, setEdges]
  );

  const onConnect = useCallback(
    (connection: Connection) =>
      setEdges(addEdge({ ...connection, id: `e-${Date.now()}` }, edges)),
    [edges, setEdges]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const type = e.dataTransfer.getData('application/reactflow');
      if (!type) return;
      const position = screenToFlowPosition({ x: e.clientX, y: e.clientY });
      setNodes([
        ...nodes,
        { id: `${type}-${_nodeIdCounter++}`, type, position, data: {} },
      ]);
    },
    [nodes, setNodes, screenToFlowPosition]
  );

  return (
    <div
      className="flex-1 h-full"
      onDrop={onDrop}
      onDragOver={(e) => e.preventDefault()}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPE_MAP}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={(_, node) => setSelectedNodeId(node.id)}
        onPaneClick={() => setSelectedNodeId(null)}
        fitView
      >
        <Background />
        <Controls />
        <MiniMap />
      </ReactFlow>
    </div>
  );
}
