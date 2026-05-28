import type { IconType } from 'react-icons';
import { HiOutlineSquares2X2, HiOutlineFilm, HiOutlineCircleStack } from 'react-icons/hi2';

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
    to: '/pipelines',
    label: '流程编排',
    caption: '节点式工作流',
    keywords: ['pipeline', 'workflow', 'node', '流程', '编排'],
    icon: HiOutlineSquares2X2,
  },
  {
    to: '/scenarios',
    label: '场景库',
    caption: '场景资产管理',
    keywords: ['scenario', 'recording', '场景', '录制', '回放'],
    icon: HiOutlineFilm,
  },
  {
    to: '/datasets',
    label: '数据集',
    caption: '传感器渲染数据',
    keywords: ['dataset', 'render', 'sensor', '数据集', '渲染', '传感器'],
    icon: HiOutlineCircleStack,
  },
];

export const navigationGroups: NavigationGroup[] = [
  {
    id: 'pipeline',
    label: '流程',
    items: navigation,
  },
];

export const workflowSteps: { to: string; label: string; caption: string }[] = [];
