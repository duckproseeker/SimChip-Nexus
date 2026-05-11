import { motion } from 'framer-motion';
import clsx from 'clsx';

interface SkeletonProps {
  className?: string;
  style?: React.CSSProperties;
}

export function Skeleton({ className, style }: SkeletonProps) {
  return (
    <motion.div
      initial={{ opacity: 0.5 }}
      animate={{ opacity: [0.3, 0.7, 0.3] }}
      transition={{
        duration: 1.8,
        ease: 'easeInOut',
        repeat: Infinity
      }}
      className={clsx('bg-secondaryGray-200/50 dark:bg-navy-700/50 shadow-inner rounded-md', className)}
      style={style}
    />
  );
}

export function SkeletonLine({ className, ...props }: SkeletonProps) {
  return <Skeleton className={clsx('h-4 w-full rounded', className)} {...props} />;
}

export function SkeletonCircle({ size = 40, className, ...props }: SkeletonProps & { size?: number }) {
  return (
    <Skeleton
      className={clsx('rounded-full', className)}
      style={{ width: size, height: size, ...props.style }}
      {...props}
    />
  );
}
