import type { IconType } from 'react-icons';
import {
  HiOutlineBookOpen,
  HiOutlineChartBarSquare,
  HiOutlineCircleStack,
  HiOutlineDocumentChartBar,
  HiOutlinePlayCircle,
  HiOutlineRadio,
  HiOutlineSquares2X2,
  HiOutlineAdjustmentsHorizontal
} from 'react-icons/hi2';

export interface NavigationItem {
  to: string;
  label: string;
  caption: string;
  keywords: string[];
  icon: IconType;
}

export interface NavigationGroup {
  id: string;
  label: string;
  items: NavigationItem[];
}

export const navigation: NavigationItem[] = [
  {
    to: '/projects',
    label: '项目',
    caption: '项目基线与目标',
    keywords: ['projects', 'project', 'dashboard', '项目', '首页'],
    icon: HiOutlineSquares2X2
  },
  {
    to: '/benchmarks',
    label: '基准任务',
    caption: '模板与协议',
    keywords: ['benchmarks', 'benchmark', '模板', '任务', '基准'],
    icon: HiOutlineChartBarSquare
  },
  {
    to: '/scenario-sets',
    label: '场景集',
    caption: '参数编排',
    keywords: ['scenario', 'preset', '场景', '预设'],
    icon: HiOutlineBookOpen
  },
  {
    to: '/scenario-recordings',
    label: '场景资产库',
    caption: '可复现回放',
    keywords: ['scenario recordings', 'recorder', 'replay', 'asset', '场景资产', '回放'],
    icon: HiOutlineCircleStack
  },
  {
    to: '/sensor-profiles',
    label: '传感器库',
    caption: 'Profile 与 hash',
    keywords: ['sensor profiles', 'sensor', 'profile', '传感器库', '传感器'],
    icon: HiOutlineAdjustmentsHorizontal
  },
  {
    to: '/executions',
    label: '回放执行',
    caption: 'Replay runs',
    keywords: ['execution', 'run', 'monitor', 'replay', '执行台', '执行', '运行', '回放'],
    icon: HiOutlinePlayCircle
  },
  {
    to: '/reports',
    label: '报告',
    caption: '结果复盘',
    keywords: ['report', 'reports', '分析', '报告'],
    icon: HiOutlineDocumentChartBar
  },
  {
    to: '/devices',
    label: '设备台',
    caption: '待测端观测',
    keywords: ['device', 'gateway', 'capture', '设备台', '设备', '网关'],
    icon: HiOutlineRadio
  },
  {
    to: '/studio',
    label: '运维台',
    caption: '车型与传感器',
    keywords: ['studio', 'ops', 'sensor', 'profile', '运维台', '运维', '传感器', '车型'],
    icon: HiOutlineSquares2X2
  }
];

export const navigationGroups: NavigationGroup[] = [
  {
    id: 'workflow',
    label: '流程',
    items: navigation.slice(0, 6)
  },
  {
    id: 'operations',
    label: '运维',
    items: navigation.slice(6)
  }
];

export const workflowSteps = [
  { to: '/projects', label: '项目', caption: '选择业务项目' },
  { to: '/benchmarks', label: '基准任务', caption: '选择评测模板' },
  { to: '/scenario-sets', label: '场景集', caption: '选择执行预设' },
  { to: '/scenario-recordings', label: '资产库', caption: '选择回放资产' },
  { to: '/sensor-profiles', label: '传感器库', caption: '选择 profile' },
  { to: '/executions', label: '回放执行', caption: '启动并监控运行' },
  { to: '/reports', label: '报告', caption: '复盘并导出结果' }
];
