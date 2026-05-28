interface Props {
  nodeType: string;
  data: Record<string, unknown>;
  onChange: (data: Record<string, unknown>) => void;
}

export function OutputForm({ nodeType, data, onChange }: Props) {
  if (nodeType === 'rtp_output') {
    return (
      <div className="space-y-3">
        <label className="block text-xs font-medium text-zinc-500">RTP 地址</label>
        <input
          className="w-full rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1.5 text-sm"
          placeholder="rtp://192.168.1.100:5004"
          value={(data.address as string) || ''}
          onChange={(e) => onChange({ ...data, address: e.target.value })}
        />
        <label className="block text-xs font-medium text-zinc-500">编码格式</label>
        <select
          className="w-full rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1.5 text-sm"
          value={(data.codec as string) || 'h264'}
          onChange={(e) => onChange({ ...data, codec: e.target.value })}
        >
          <option value="h264">H.264</option>
          <option value="h265">H.265</option>
          <option value="raw">Raw</option>
        </select>
      </div>
    );
  }
  if (nodeType === 'pointcloud_output') {
    return (
      <div className="space-y-3">
        <label className="block text-xs font-medium text-zinc-500">输出格式</label>
        <select
          className="w-full rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1.5 text-sm"
          value={(data.format as string) || 'pcd'}
          onChange={(e) => onChange({ ...data, format: e.target.value })}
        >
          <option value="pcd">PCD</option>
          <option value="ply">PLY</option>
          <option value="bin">BIN (KITTI)</option>
        </select>
        <label className="block text-xs font-medium text-zinc-500">目标地址</label>
        <input
          className="w-full rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1.5 text-sm"
          placeholder="udp://192.168.1.100:6000"
          value={(data.address as string) || ''}
          onChange={(e) => onChange({ ...data, address: e.target.value })}
        />
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <label className="block text-xs font-medium text-zinc-500">输出路径</label>
      <input
        className="w-full rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1.5 text-sm"
        placeholder="/data/output/"
        value={(data.path as string) || ''}
        onChange={(e) => onChange({ ...data, path: e.target.value })}
      />
    </div>
  );
}
