import type { Node, Edge } from '@xyflow/react';

export interface PipelineTemplate {
  id: string;
  name: string;
  description: string;
  nodes: Node[];
  edges: Edge[];
}

export const TEMPLATES: PipelineTemplate[] = [
  {
    id: 'empty',
    name: '空白画布',
    description: '从零开始自由搭建',
    nodes: [],
    edges: [],
  },
  {
    id: 'scene_only',
    name: '纯场景验证',
    description: '验证录制文件是否正常回放',
    nodes: [
      { id: 'scene-1', type: 'scene_replay', position: { x: 200, y: 200 }, data: {} },
    ],
    edges: [],
  },
  {
    id: 'single_camera',
    name: '单摄像头回放',
    description: '场景 → 摄像头 → RTP 输出',
    nodes: [
      { id: 'scene-1', type: 'scene_replay', position: { x: 100, y: 200 }, data: {} },
      { id: 'cam-1', type: 'camera', position: { x: 350, y: 200 }, data: { width: 1920, height: 1080, fov: 90 } },
      { id: 'rtp-1', type: 'rtp_output', position: { x: 600, y: 200 }, data: {} },
    ],
    edges: [
      { id: 'e1', source: 'scene-1', sourceHandle: 'scene', target: 'cam-1', targetHandle: 'scene' },
      { id: 'e2', source: 'cam-1', sourceHandle: 'sensor_data', target: 'rtp-1', targetHandle: 'sensor_data' },
    ],
  },
  {
    id: 'multi_sensor',
    name: '多传感器融合',
    description: '场景 → 多传感器 → 多输出 → DUT',
    nodes: [
      { id: 'scene-1', type: 'scene_replay', position: { x: 50, y: 250 }, data: {} },
      { id: 'cam-1', type: 'camera', position: { x: 300, y: 100 }, data: { width: 1920, height: 1080, fov: 90 } },
      { id: 'cam-2', type: 'camera', position: { x: 300, y: 250 }, data: { width: 1920, height: 1080, fov: 120 } },
      { id: 'lidar-1', type: 'lidar', position: { x: 300, y: 400 }, data: { channels: 64, range: 100 } },
      { id: 'rtp-1', type: 'rtp_output', position: { x: 550, y: 100 }, data: {} },
      { id: 'rtp-2', type: 'rtp_output', position: { x: 550, y: 250 }, data: {} },
      { id: 'pc-1', type: 'pointcloud_output', position: { x: 550, y: 400 }, data: {} },
      { id: 'dut-1', type: 'dut', position: { x: 800, y: 250 }, data: {} },
    ],
    edges: [
      { id: 'e1', source: 'scene-1', sourceHandle: 'scene', target: 'cam-1', targetHandle: 'scene' },
      { id: 'e2', source: 'scene-1', sourceHandle: 'scene', target: 'cam-2', targetHandle: 'scene' },
      { id: 'e3', source: 'scene-1', sourceHandle: 'scene', target: 'lidar-1', targetHandle: 'scene' },
      { id: 'e4', source: 'cam-1', sourceHandle: 'sensor_data', target: 'rtp-1', targetHandle: 'sensor_data' },
      { id: 'e5', source: 'cam-2', sourceHandle: 'sensor_data', target: 'rtp-2', targetHandle: 'sensor_data' },
      { id: 'e6', source: 'lidar-1', sourceHandle: 'sensor_data', target: 'pc-1', targetHandle: 'sensor_data' },
      { id: 'e7', source: 'rtp-1', sourceHandle: 'stream', target: 'dut-1', targetHandle: 'stream' },
      { id: 'e8', source: 'rtp-2', sourceHandle: 'stream', target: 'dut-1', targetHandle: 'stream' },
      { id: 'e9', source: 'pc-1', sourceHandle: 'stream', target: 'dut-1', targetHandle: 'stream' },
    ],
  },
];