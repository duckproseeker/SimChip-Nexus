import { useEffect, useMemo, useState } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import { Link, useNavigate } from 'react-router-dom';

import {
  launchScenarioSourceRecording,
  listScenarioSources,
  rescanScenarioSources
} from '../../api/scenarioSources';
import type { ScenarioSource, ScenarioSourceLaunchRecordingPayload } from '../../api/types';
import { EmptyState } from '../../components/common/EmptyState';
import { KeyValueGrid } from '../../components/common/KeyValueGrid';
import { PageHeader } from '../../components/common/PageHeader';
import { Panel } from '../../components/common/Panel';
import { StatusPill } from '../../components/common/StatusPill';
import { formatDateTime } from '../../lib/format';

const defaultLaunchPayload: ScenarioSourceLaunchRecordingPayload = {
  sensor_profile_name: 'front_rgb',
  fixed_delta_seconds: 0.05,
  auto_start: true,
  materialization_agent_type: 'route_follower',
  metadata: {
    tags: ['scenario_source_materialization'],
    description: 'Public scenario source materialization'
  }
};

const materializationLabels: Record<string, string> = {
  never_recorded: '未录制',
  recording_running: '录制中',
  recorded_unpublished: '待发布',
  published_asset_available: '已有资产',
  failed_last_materialization: '上次失败',
  incompatible: '不兼容'
};

function textFromUnknown(value: unknown) {
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  return String(value);
}

export function ScenarioSourcesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [providerFilter, setProviderFilter] = useState('');
  const [mapFilter, setMapFilter] = useState('');
  const [scenarioTypeFilter, setScenarioTypeFilter] = useState('');
  const [cornerCaseFilter, setCornerCaseFilter] = useState('');
  const [compatibilityFilter, setCompatibilityFilter] = useState('');
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [launchDraft, setLaunchDraft] =
    useState<ScenarioSourceLaunchRecordingPayload>(defaultLaunchPayload);

  const sourcesQuery = useQuery({
    queryKey: [
      'scenario-sources',
      { providerFilter, mapFilter, scenarioTypeFilter, cornerCaseFilter, compatibilityFilter }
    ],
    queryFn: () =>
      listScenarioSources({
        provider: providerFilter,
        map_name: mapFilter,
        scenario_type: scenarioTypeFilter,
        corner_case_label: cornerCaseFilter,
        compatibility_status: compatibilityFilter
      })
  });

  const sources = sourcesQuery.data?.sources ?? [];
  const selectedSource =
    sources.find((item) => item.source_id === selectedSourceId) ?? sources[0] ?? null;

  useEffect(() => {
    if (!selectedSourceId && sources.length > 0) {
      setSelectedSourceId(sources[0].source_id);
    }
    if (
      selectedSourceId &&
      sources.length > 0 &&
      !sources.some((item) => item.source_id === selectedSourceId)
    ) {
      setSelectedSourceId(sources[0].source_id);
    }
  }, [sources, selectedSourceId]);

  const providerOptions = useMemo(
    () => Array.from(new Set(sources.map((item) => item.provider))).sort(),
    [sources]
  );
  const mapOptions = useMemo(
    () => Array.from(new Set(sources.map((item) => item.map_name))).sort(),
    [sources]
  );
  const scenarioTypeOptions = useMemo(
    () =>
      Array.from(
        new Set(
          sources
            .map((item) => item.scenario_type)
            .filter((type): type is string => Boolean(type))
        )
      ).sort(),
    [sources]
  );
  const cornerCaseOptions = useMemo(
    () => Array.from(new Set(sources.flatMap((item) => item.corner_case_labels))).sort(),
    [sources]
  );

  const rescanMutation = useMutation({
    mutationFn: () => rescanScenarioSources(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['scenario-sources'] });
    }
  });

  const launchMutation = useMutation({
    mutationFn: (source: ScenarioSource) =>
      launchScenarioSourceRecording(source.source_id, launchDraft),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ['scenario-sources'] });
      void queryClient.invalidateQueries({ queryKey: ['runs'] });
      navigate(`/executions/${result.run.run_id}`);
    }
  });

  const updateLaunchDraft = <Key extends keyof ScenarioSourceLaunchRecordingPayload>(
    key: Key,
    value: ScenarioSourceLaunchRecordingPayload[Key]
  ) => {
    setLaunchDraft((current) => ({ ...current, [key]: value }));
  };

  return (
    <div className="page-stack">
      <PageHeader
        title="公共场景源"
        eyebrow="场景 / Materialization"
        chips={['ScenarioRunner', 'Bench2Drive', 'Leaderboard']}
        description="把公开场景定义重物化为本平台 recorder 资产，保留 CARLA、sensor profile、fixed-delta 和 agent lineage。"
        actions={
          <>
            <button
              className="horizon-button-secondary"
              disabled={rescanMutation.isPending}
              onClick={() => rescanMutation.mutate()}
              type="button"
            >
              {rescanMutation.isPending ? '扫描中...' : '重新扫描'}
            </button>
            <Link className="horizon-button-secondary" to="/scenario-recordings">
              查看资产库
            </Link>
            {selectedSource && (
              <button
                className="horizon-button"
                disabled={
                  launchMutation.isPending || selectedSource.materialization.status === 'incompatible'
                }
                onClick={() => launchMutation.mutate(selectedSource)}
                type="button"
              >
                启动录制物化
              </button>
            )}
          </>
        }
      />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
        <div className="space-y-5">
          <Panel
            eyebrow="过滤"
            title="Source catalog"
            subtitle="按 provider、地图、scenario type、corner case 和兼容状态筛选公共场景源。"
          >
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              <label className="form-field">
                <span>Provider</span>
                <select value={providerFilter} onChange={(event) => setProviderFilter(event.target.value)}>
                  <option value="">全部来源</option>
                  {providerOptions.map((provider) => (
                    <option key={provider} value={provider}>
                      {provider}
                    </option>
                  ))}
                </select>
              </label>
              <label className="form-field">
                <span>地图</span>
                <select value={mapFilter} onChange={(event) => setMapFilter(event.target.value)}>
                  <option value="">全部地图</option>
                  {mapOptions.map((mapName) => (
                    <option key={mapName} value={mapName}>
                      {mapName}
                    </option>
                  ))}
                </select>
              </label>
              <label className="form-field">
                <span>Scenario type</span>
                <select
                  value={scenarioTypeFilter}
                  onChange={(event) => setScenarioTypeFilter(event.target.value)}
                >
                  <option value="">全部类型</option>
                  {scenarioTypeOptions.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
              </label>
              <label className="form-field">
                <span>Corner case</span>
                <select
                  value={cornerCaseFilter}
                  onChange={(event) => setCornerCaseFilter(event.target.value)}
                >
                  <option value="">全部标签</option>
                  {cornerCaseOptions.map((label) => (
                    <option key={label} value={label}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="form-field">
                <span>兼容性</span>
                <select
                  value={compatibilityFilter}
                  onChange={(event) => setCompatibilityFilter(event.target.value)}
                >
                  <option value="">全部状态</option>
                  <option value="ok">ok</option>
                  <option value="incompatible">incompatible</option>
                  <option value="missing_route">missing_route</option>
                  <option value="unsupported_openscenario_feature">
                    unsupported_openscenario_feature
                  </option>
                </select>
              </label>
            </div>
          </Panel>

          <Panel
            eyebrow="Sources"
            title="场景源列表"
            subtitle="source 是公开场景定义；只有完成 materialization 并发布后才会进入可回放场景资产库。"
          >
            {sourcesQuery.isLoading ? (
              <EmptyState title="场景源加载中" description="正在读取 SQLite source catalog。" />
            ) : sourcesQuery.isError ? (
              <EmptyState
                title="场景源加载失败"
                description={
                  sourcesQuery.error instanceof Error ? sourcesQuery.error.message : '接口异常。'
                }
              />
            ) : sources.length === 0 ? (
              <EmptyState
                title="还没有公共场景源"
                description="配置 SCENARIO_RUNNER_ROOT、BENCH2DRIVE_ROOT 或 LEADERBOARD_ROOT 后点击重新扫描。"
              />
            ) : (
              <div className="space-y-3">
                {sources.map((source) => (
                  <button
                    key={source.source_id}
                    className={clsx(
                      'w-full rounded-[20px] border px-4 py-4 text-left transition',
                      selectedSource?.source_id === source.source_id
                        ? 'border-brand-500 bg-brand-50/80 shadow-sm'
                        : 'border-secondaryGray-200 bg-white/80 hover:border-brand-200'
                    )}
                    onClick={() => setSelectedSourceId(source.source_id)}
                    type="button"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-extrabold text-navy-900">
                          {source.scenario_type ?? source.route_id ?? source.source_id}
                        </p>
                        <p className="mt-1 text-xs text-secondaryGray-500">
                          {source.provider} / {source.map_name} / {source.route_id ?? '-'}
                        </p>
                      </div>
                      <StatusPill
                        status={
                          materializationLabels[source.materialization.status] ??
                          source.materialization.status
                        }
                      />
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {source.corner_case_labels.map((label) => (
                        <span
                          key={label}
                          className="rounded-full bg-orange-50 px-2 py-1 text-xs font-bold text-orange-700"
                        >
                          {label}
                        </span>
                      ))}
                      <span className="rounded-full bg-secondaryGray-100 px-2 py-1 text-xs font-bold text-secondaryGray-600">
                        {source.compatibility_status}
                      </span>
                    </div>
                    <p className="mt-3 text-xs text-secondaryGray-500">
                      最近 run: {source.materialization.last_run_id ?? '-'} / 资产:{' '}
                      {source.materialization.last_recording_id ?? '-'}
                    </p>
                  </button>
                ))}
              </div>
            )}
          </Panel>
        </div>

        <aside className="space-y-5">
          <Panel
            eyebrow="Materialization"
            title="执行上下文"
            subtitle="创建前会做 CARLA/TM/sync/fixed-delta/sensor profile preflight；失败时不会创建 run。"
            actions={selectedSource ? <StatusPill status={selectedSource.compatibility_status} /> : undefined}
          >
            {selectedSource ? (
              <div className="space-y-5">
                <KeyValueGrid
                  items={[
                    { label: 'Source ID', value: selectedSource.source_id },
                    { label: 'Provider', value: selectedSource.provider },
                    { label: 'Route ID', value: selectedSource.route_id ?? '-' },
                    { label: '地图', value: selectedSource.map_name },
                    { label: '天气', value: textFromUnknown(selectedSource.weather['preset']) },
                    {
                      label: '建议时长',
                      value: selectedSource.recommended_duration_seconds
                        ? `${selectedSource.recommended_duration_seconds.toFixed(1)}s`
                        : '-'
                    },
                    {
                      label: '最近物化',
                      value: materializationLabels[selectedSource.materialization.status] ?? selectedSource.materialization.status
                    },
                    {
                      label: '更新时间',
                      value: formatDateTime(selectedSource.updated_at_utc)
                    }
                  ]}
                />

                {selectedSource.compatibility_message && (
                  <p className="rounded-[16px] border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-800">
                    {selectedSource.compatibility_message}
                  </p>
                )}

                <div className="space-y-3 border-t border-border-glass pt-4">
                  <label className="form-field">
                    <span>Sensor profile</span>
                    <input
                      value={launchDraft.sensor_profile_name}
                      onChange={(event) =>
                        updateLaunchDraft('sensor_profile_name', event.target.value)
                      }
                    />
                  </label>
                  <label className="form-field">
                    <span>Fixed delta</span>
                    <input
                      min={0.01}
                      max={0.2}
                      step={0.01}
                      type="number"
                      value={launchDraft.fixed_delta_seconds}
                      onChange={(event) =>
                        updateLaunchDraft('fixed_delta_seconds', Number(event.target.value))
                      }
                    />
                  </label>
                  <label className="form-field">
                    <span>Materialization agent</span>
                    <input readOnly value={launchDraft.materialization_agent_type} />
                  </label>
                  <label className="flex items-center gap-3 text-sm font-bold text-secondaryGray-700">
                    <input
                      checked={launchDraft.auto_start}
                      type="checkbox"
                      onChange={(event) => updateLaunchDraft('auto_start', event.target.checked)}
                    />
                    创建后自动启动
                  </label>
                  <button
                    className="horizon-button w-full"
                    disabled={
                      launchMutation.isPending ||
                      selectedSource.materialization.status === 'incompatible'
                    }
                    onClick={() => launchMutation.mutate(selectedSource)}
                    type="button"
                  >
                    {launchMutation.isPending ? '创建中...' : '启动录制物化'}
                  </button>
                  {launchMutation.error && (
                    <p className="text-sm text-rose-600">{launchMutation.error.message}</p>
                  )}
                </div>
              </div>
            ) : (
              <EmptyState title="未选择场景源" description="先从左侧选择一个公共场景源。" />
            )}
          </Panel>
        </aside>
      </div>
    </div>
  );
}
