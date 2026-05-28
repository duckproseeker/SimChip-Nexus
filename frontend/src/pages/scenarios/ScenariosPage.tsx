import { useEffect, useState } from 'react';

import {
  listScenarioAssets,
  deleteScenarioAsset,
  type ScenarioAsset,
} from '../../api/scenarioAssets';

export default function ScenariosPage() {
  const [scenarios, setScenarios] = useState<ScenarioAsset[]>([]);
  const [tagFilter, setTagFilter] = useState('');

  const load = () => {
    listScenarioAssets(tagFilter ? { tag: tagFilter } : undefined).then(
      setScenarios
    );
  };
  useEffect(load, [tagFilter]);

  const allTags = [...new Set(scenarios.flatMap((s) => s.tags))];

  return (
    <div className="flex-1 p-6 overflow-y-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-zinc-800 dark:text-zinc-100">
          场景库
        </h1>
        <button className="px-4 py-2 bg-blue-600 text-white text-sm rounded-md hover:bg-blue-700">
          导入场景
        </button>
      </div>

      <div className="flex gap-2 mb-4 flex-wrap">
        <button
          onClick={() => setTagFilter('')}
          className={`px-3 py-1 text-xs rounded-full border ${
            !tagFilter
              ? 'bg-blue-100 border-blue-300 text-blue-700'
              : 'border-zinc-300 text-zinc-600'
          }`}
        >
          全部
        </button>
        {allTags.map((tag) => (
          <button
            key={tag}
            onClick={() => setTagFilter(tag)}
            className={`px-3 py-1 text-xs rounded-full border ${
              tagFilter === tag
                ? 'bg-blue-100 border-blue-300 text-blue-700'
                : 'border-zinc-300 text-zinc-600'
            }`}
          >
            {tag}
          </button>
        ))}
      </div>

      <div className="grid gap-3">
        {scenarios.map((s) => (
          <div
            key={s.id}
            className="p-4 bg-white dark:bg-zinc-800 rounded-lg border border-zinc-200 dark:border-zinc-700 flex justify-between items-center"
          >
            <div>
              <div className="font-medium text-zinc-800 dark:text-zinc-100">
                {s.name}
              </div>
              <div className="text-xs text-zinc-400 mt-1">
                {s.map_name || '未解析'} · {s.duration_seconds.toFixed(1)}s ·{' '}
                {(s.file_size_bytes / 1048576).toFixed(1)} MB
              </div>
              <div className="flex gap-1 mt-2">
                {s.tags.map((t) => (
                  <span
                    key={t}
                    className="px-2 py-0.5 text-xs bg-zinc-100 dark:bg-zinc-700 rounded"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>
            <button
              onClick={() => {
                deleteScenarioAsset(s.id).then(load);
              }}
              className="text-xs text-red-500 hover:text-red-700"
            >
              删除
            </button>
          </div>
        ))}
        {scenarios.length === 0 && (
          <p className="text-sm text-zinc-400 text-center py-8">
            暂无场景，点击"导入场景"添加
          </p>
        )}
      </div>
    </div>
  );
}
