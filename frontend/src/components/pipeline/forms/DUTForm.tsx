interface Props {
  data: Record<string, unknown>;
  onChange: (data: Record<string, unknown>) => void;
}

export function DUTForm({ data, onChange }: Props) {
  return (
    <div className="space-y-3">
      <label className="block text-xs font-medium text-zinc-500">设备名称</label>
      <input
        className="w-full rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1.5 text-sm"
        placeholder="Jetson Orin"
        value={(data.device_name as string) || ''}
        onChange={(e) => onChange({ ...data, device_name: e.target.value })}
      />
      <label className="block text-xs font-medium text-zinc-500">连接地址</label>
      <input
        className="w-full rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1.5 text-sm"
        placeholder="192.168.1.200"
        value={(data.host as string) || ''}
        onChange={(e) => onChange({ ...data, host: e.target.value })}
      />
    </div>
  );
}
