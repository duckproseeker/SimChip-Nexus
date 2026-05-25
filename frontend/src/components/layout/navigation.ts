import type { IconType } from 'react-icons';
import { HiOutlineSquares2X2 } from 'react-icons/hi2';

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
];

export const navigationGroups: NavigationGroup[] = [
  {
    id: 'pipeline',
    label: '流程',
    items: navigation,
  },
];

export const workflowSteps: { to: string; label: string; caption: string }[] = [];
