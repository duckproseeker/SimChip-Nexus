import clsx from 'clsx';
import { motion } from 'framer-motion';
import {
  LuCircleCheck,
  LuCircleX,
  LuLoader,
  LuClock,
  LuCirclePlay,
  LuBan,
  LuTriangleAlert
} from 'react-icons/lu';

import { StatusSemantic, statusToneClass, toStatusSemantic } from '../../lib/status';

interface StatusPillProps {
  status: string;
  canonical?: boolean;
}

const statusLabels: Record<string, string> = {
  READY: '就绪',
  RUNNING: '运行中',
  COMPLETED: '已完成',
  FAILED: '失败',
  DEGRADED: '降级',
  UNKNOWN: '未知',
  CREATED: '已创建',
  QUEUED: '排队中',
  STARTING: '启动中',
  STOPPING: '停止中',
  PAUSED: '已暂停',
  CANCELED: '已取消',
  STOPPED: '已停止',
  ERROR: '错误',
  BUSY: '忙碌',
  OFFLINE: '离线',
  IDLE: '空闲',
  DISABLED: '已禁用'
};

function localizeStatusLabel(status: string) {
  return statusLabels[status] ?? status;
}

function getIconForSemantic(semantic: StatusSemantic, className?: string, exactStatus?: string) {
  if (exactStatus === 'QUEUED') return <LuClock className={className} />;
  if (exactStatus === 'STARTING') return <LuCirclePlay className={className} />;
  if (exactStatus === 'CANCELED') return <LuBan className={className} />;

  switch (semantic) {
    case 'COMPLETED':
    case 'READY':
      return <LuCircleCheck className={className} />;
    case 'FAILED':
      return <LuCircleX className={className} />;
    case 'DEGRADED':
      return <LuTriangleAlert className={className} />;
    case 'RUNNING':
      return (
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1.5, repeat: Infinity, ease: 'linear' }}
        >
          <LuLoader className={className} />
        </motion.div>
      );
    default:
      return null;
  }
}

export function StatusPill({ status, canonical = false }: StatusPillProps) {
  const semantic = toStatusSemantic(status);
  const label = canonical ? localizeStatusLabel(semantic) : localizeStatusLabel(status);

  return (
    <motion.div
      initial={{ opacity: 0.8, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className={clsx(
        'status-badge inline-flex min-h-7 items-center justify-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.12em] shadow-sm backdrop-blur-md',
        statusToneClass(semantic)
      )}
      title={status}
    >
      {getIconForSemantic(semantic, 'h-3.5 w-3.5 flex-shrink-0', status)}
      <span>{label}</span>
      {semantic === 'RUNNING' && (
        <motion.div
          className="absolute inset-0 rounded-full border border-current opacity-30"
          animate={{ scale: [1, 1.15, 1], opacity: [0.2, 0, 0.2] }}
          transition={{ duration: 2, repeat: Infinity }}
        />
      )}
    </motion.div>
  );
}
