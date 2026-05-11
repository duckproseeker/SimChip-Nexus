interface ProgressBarProps {
  value: number;
  max: number;
  label?: string;
}

export function ProgressBar({ value, max, label }: ProgressBarProps) {
  const safeMax = max > 0 ? max : 1;
  const ratio = Math.max(0, Math.min(100, (value / safeMax) * 100));

  return (
    <div className="flex flex-col gap-2">
      {label && <span className="text-xs font-semibold text-secondaryGray-600">{label}</span>}
      <div className="h-2.5 overflow-hidden rounded-full bg-secondaryGray-200">
        <div
          className="h-2.5 rounded-full bg-gradient-to-r from-brand-500 via-brand-400 to-accent-500"
          style={{ width: `${ratio}%` }}
        />
      </div>
    </div>
  );
}
