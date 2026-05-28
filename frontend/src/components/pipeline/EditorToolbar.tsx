import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePipelineStore } from '../../features/pipeline/store';
import { validateGraph } from '../../features/pipeline/validation';
import { updatePipeline, executePipeline } from '../../api/pipelines';
import type { ExecuteBody } from '../../api/pipelines';
import type { PipelineNodeDef, PipelineEdgeDef } from '../../api/types';

export function EditorToolbar() {
  const { pipelineId, pipelineName, nodes, edges, dirty, markClean, setExecutionId } =
    usePipelineStore();
  const navigate = useNavigate();
  const [errors, setErrors] = useState<string[]>([]);
  const [showRunMenu, setShowRunMenu] = useState(false);
  const [showDatasetInput, setShowDatasetInput] = useState(false);
  const [datasetId, setDatasetId] = useState('');
  const menuRef = useRef<HTMLDivElement>(null);

  const buildPatch = () => ({
    nodes: nodes.map((n) => ({
      node_id: n.id,
      type: n.type as PipelineNodeDef['type'],
      position: n.position as { x: number; y: number },
      data: (n.data ?? {}) as Record<string, unknown>,
    })),
    edges: edges.map((e) => ({
      edge_id: e.id,
      source: e.source,
      source_handle: e.sourceHandle ?? '',
      target: e.target,
      target_handle: e.targetHandle ?? '',
    })) as PipelineEdgeDef[],
  });

  const handleSave = async () => {
    if (!pipelineId) return;
    await updatePipeline(pipelineId, buildPatch());
    markClean();
  };

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as HTMLElement)) {
        setShowRunMenu(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleRun = async (body?: ExecuteBody) => {
    if (!pipelineId) return;

    const patch = buildPatch();
    const validationErrors = validateGraph(patch.nodes, patch.edges);
    if (validationErrors.length > 0) {
      setErrors(validationErrors);
      return;
    }
    setErrors([]);

    await handleSave();
    await executePipeline(pipelineId, body);
    navigate('/datasets');
  };

  const handleOnlinePlay = () => {
    setShowRunMenu(false);
    setShowDatasetInput(true);
  };

  const handleOnlinePlayConfirm = () => {
    setShowDatasetInput(false);
    handleRun({ mode: 'online_play', options: { dataset_id: datasetId } });
    setDatasetId('');
  };

  return (
    <header className="flex flex-col shrink-0">
      <div className="flex items-center gap-3 border-b border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-4 py-2 h-12">
        <span className="font-medium text-sm flex-1 truncate text-zinc-800 dark:text-zinc-100">
          {pipelineName ?? 'Untitled Pipeline'}
        </span>
        {dirty && <span className="text-xs text-zinc-400">Unsaved</span>}
        <button
          onClick={handleSave}
          className="px-3 py-1 text-sm rounded border border-zinc-200 dark:border-zinc-600 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-700 dark:text-zinc-200"
        >
          Save
        </button>
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setShowRunMenu((v) => !v)}
            className="px-3 py-1 text-sm rounded bg-blue-500 hover:bg-blue-600 text-white font-medium"
          >
            Run ▾
          </button>
          {showRunMenu && (
            <div className="absolute right-0 top-full mt-1 w-40 bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-600 rounded shadow-lg z-50">
              <button
                onClick={() => { setShowRunMenu(false); handleRun({ mode: 'offline_render' }); }}
                className="w-full text-left px-3 py-2 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-700 text-zinc-700 dark:text-zinc-200"
              >
                离线生成
              </button>
              <button
                onClick={handleOnlinePlay}
                className="w-full text-left px-3 py-2 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-700 text-zinc-700 dark:text-zinc-200"
              >
                在线播放
              </button>
              <button
                onClick={() => { setShowRunMenu(false); handleRun({ mode: 'legacy' }); }}
                className="w-full text-left px-3 py-2 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-700 text-zinc-700 dark:text-zinc-200"
              >
                执行
              </button>
            </div>
          )}
        </div>
      </div>
      {showDatasetInput && (
        <div className="px-4 py-2 border-b border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 flex items-center gap-2">
          <label className="text-xs text-zinc-600 dark:text-zinc-300">Dataset ID:</label>
          <input
            type="text"
            value={datasetId}
            onChange={(e) => setDatasetId(e.target.value)}
            className="flex-1 px-2 py-1 text-sm border border-zinc-300 dark:border-zinc-600 rounded bg-white dark:bg-zinc-900 text-zinc-800 dark:text-zinc-100"
            placeholder="输入数据集 ID"
            autoFocus
          />
          <button
            onClick={handleOnlinePlayConfirm}
            className="px-3 py-1 text-sm rounded bg-blue-500 hover:bg-blue-600 text-white"
          >
            确认
          </button>
          <button
            onClick={() => setShowDatasetInput(false)}
            className="px-3 py-1 text-sm rounded border border-zinc-200 dark:border-zinc-600 hover:bg-zinc-100 dark:hover:bg-zinc-700 text-zinc-700 dark:text-zinc-200"
          >
            取消
          </button>
        </div>
      )}
      {errors.length > 0 && (
        <div className="px-4 py-1 bg-red-50 dark:bg-red-900/20 border-b border-red-200 dark:border-red-800">
          {errors.map((err, i) => (
            <p key={i} className="text-xs text-red-600 dark:text-red-400">{err}</p>
          ))}
        </div>
      )}
    </header>
  );
}
