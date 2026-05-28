import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { datasetsApi, type Dataset } from '../../api/datasets';

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [scenarioNames, setScenarioNames] = useState<Record<string, string>>({});
  const navigate = useNavigate();

  const reload = useCallback(() => {
    datasetsApi.list().then((res) => {
      setDatasets(res);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  useEffect(() => { reload(); }, [reload]);

  useEffect(() => {
    const hasRendering = datasets.some((d) => d.status === 'RENDERING');
    if (!hasRendering) return;
    const timer = setInterval(reload, 2000);
    return () => clearInterval(timer);
  }, [datasets, reload]);

  useEffect(() => {
    const ids = [...new Set(datasets.map((d) => d.scenario_id).filter(Boolean))];
    const missing = ids.filter((id) => !scenarioNames[id]);
    if (missing.length === 0) return;
    fetch('/scenario-assets')
      .then((r) => r.json())
      .then((assets: any[]) => {
        const map: Record<string, string> = { ...scenarioNames };
        for (const a of assets) map[a.id] = a.name;
        setScenarioNames(map);
      })
      .catch(() => {});
  }, [datasets]);

  const handleDelete = async (id: string) => {
    if (!confirm('确认删除该数据集及其所有渲染文件？')) return;
    await datasetsApi.delete(id);
    setDatasets((prev) => prev.filter((d) => d.dataset_id !== id));
  };

  const statusLabel: Record<string, { text: string; color: string }> = {
    PENDING: { text: '等待中', color: '#888' },
    RENDERING: { text: '渲染中', color: '#f59e0b' },
    COMPLETED: { text: '已完成', color: '#10b981' },
    FAILED: { text: '失败', color: '#ef4444' },
  };

  return (
    <div style={{ padding: '2rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <h2 style={{ margin: 0 }}>数据集管理</h2>
        <span style={{ color: '#888', fontSize: '0.875rem' }}>共 {datasets.length} 个数据集</span>
      </div>

      {loading ? (
        <p style={{ color: '#888' }}>加载中...</p>
      ) : datasets.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '4rem 2rem', border: '1px dashed #444', borderRadius: '0.75rem' }}>
          <p style={{ fontSize: '1.1rem', marginBottom: '0.5rem' }}>暂无数据集</p>
          <p style={{ color: '#888', fontSize: '0.875rem' }}>在流程编排中点击"离线生成"来创建传感器数据集</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: '1rem' }}>
          {datasets.map((ds) => {
            const st = statusLabel[ds.status] || statusLabel.PENDING;
            return (
              <DatasetCard
                key={ds.dataset_id}
                dataset={ds}
                status={st}
                scenarioName={scenarioNames[ds.scenario_id] || ds.scenario_id}
                onDelete={handleDelete}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

function DatasetCard({ dataset, status, scenarioName, onDelete }: {
  dataset: Dataset;
  status: { text: string; color: string };
  scenarioName: string;
  onDelete: (id: string) => void;
}) {
  const [playing, setPlaying] = useState(false);
  const sensors = dataset.sensor_configs.map((s) => s.sensor_id).join(', ') || '-';
  const isRendering = dataset.status === 'RENDERING';
  const hasCamera = dataset.sensor_configs.some((s) => s.sensor_type.includes('camera'));
  const expectedFrames = dataset.duration_seconds > 0 && dataset.delta_seconds > 0
    ? Math.round(dataset.duration_seconds / dataset.delta_seconds)
    : dataset.total_frames || 0;
  const currentFrames = dataset.rendered_frames || 0;
  const progressPct = expectedFrames > 0 ? Math.min(100, Math.round((currentFrames / expectedFrames) * 100)) : 0;

  const handlePlay = async () => {
    try {
      const res = await fetch(`/datasets/${dataset.dataset_id}/play`, { method: 'POST' });
      const data = await res.json();
      if (data.status === 'playing' || data.status === 'already_playing') {
        setPlaying(true);
      }
    } catch { /* ignore */ }
  };

  const handleStop = async () => {
    await fetch(`/datasets/${dataset.dataset_id}/stop`, { method: 'POST' });
    setPlaying(false);
  };

  return (
    <div style={{ border: '1px solid #333', borderRadius: '0.75rem', padding: '1.25rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
            <strong style={{ fontSize: '1rem' }}>{dataset.name}</strong>
            <span style={{
              fontSize: '0.75rem', padding: '0.125rem 0.5rem',
              borderRadius: '999px', background: status.color + '22', color: status.color, fontWeight: 500,
            }}>{status.text}</span>
          </div>
          <div style={{ fontSize: '0.8rem', color: '#aaa', marginBottom: '0.25rem' }}>
            场景: {scenarioName}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#666' }}>
            ID: {dataset.dataset_id}
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {dataset.status === 'COMPLETED' && hasCamera && !playing && (
            <button
              onClick={handlePlay}
              style={{ padding: '0.375rem 0.75rem', borderRadius: '0.375rem', border: '1px solid #555', background: 'transparent', color: '#10b981', cursor: 'pointer', fontSize: '0.8rem' }}
            >在线播放</button>
          )}
          {playing && (
            <button
              onClick={handleStop}
              style={{ padding: '0.375rem 0.75rem', borderRadius: '0.375rem', border: '1px solid #555', background: 'transparent', color: '#f59e0b', cursor: 'pointer', fontSize: '0.8rem' }}
            >停止播放</button>
          )}
          <button
            onClick={() => onDelete(dataset.dataset_id)}
            style={{ padding: '0.375rem 0.75rem', borderRadius: '0.375rem', border: '1px solid #555', background: 'transparent', color: '#ef4444', cursor: 'pointer', fontSize: '0.8rem' }}
          >删除</button>
        </div>
      </div>

      {isRendering && (
        <div style={{ marginBottom: '0.75rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: '#aaa', marginBottom: '0.25rem' }}>
            <span>渲染进度</span>
            <span>{currentFrames}/{expectedFrames} 帧 ({progressPct}%)</span>
          </div>
          <div style={{ height: '6px', borderRadius: '3px', background: '#333', overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${progressPct}%`, background: '#f59e0b', borderRadius: '3px', transition: 'width 0.3s' }} />
          </div>
        </div>
      )}

      <div style={{ display: 'flex', gap: '1.5rem', fontSize: '0.8rem', color: '#aaa' }}>
        <span>传感器: {sensors}</span>
        {!isRendering && <span>帧数: {dataset.total_frames > 0 ? `${dataset.rendered_frames}/${dataset.total_frames}` : '-'}</span>}
        <span>时长: {dataset.duration_seconds > 0 ? dataset.duration_seconds.toFixed(1) + 's' : '-'}</span>
        <span>步长: {dataset.delta_seconds}s</span>
      </div>

      {dataset.error_message && (
        <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: '#ef4444' }}>
          {dataset.error_message.split('\n').pop()}
        </div>
      )}
    </div>
  );
}
