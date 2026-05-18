import { useEffect, useMemo, useState } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import { Link, useNavigate } from 'react-router-dom';

import {
  launchScenarioRecording,
  listScenarioRecordings
} from '../../api/scenarioRecordings';
import { listSensorProfiles } from '../../api/sensorProfiles';
import type { ScenarioRecording, ScenarioRecordingLaunchPayload, SensorProfile } from '../../api/types';
import { EmptyState } from '../../components/common/EmptyState';
import { KeyValueGrid } from '../../components/common/KeyValueGrid';
import { PageHeader } from '../../components/common/PageHeader';
import { Panel } from '../../components/common/Panel';
import { StatusPill } from '../../components/common/StatusPill';
import { formatDateTime } from '../../lib/format';

const determinismOptions = [
  'world_state_replay_with_carla_live_sensors',
  'world_state_only',
  'chip_hil_fixed_delta'
];

const defaultLaunchPayload: ScenarioRecordingLaunchPayload = {
  sensor_profile_id: '',
  preview_sensor_id: '',
  start_seconds: 0,
  duration_seconds: 20,
  sensor_mode: 'carla_live',
  fixed_delta_seconds: 0.05,
  sensor_warmup_seconds: 2,
  timebase: 'synchronous_fixed_delta',
  hil_clock_mode: 'fixed_delta',
  output_config_summary: {},
  report_config_summary: {},
  auto_start: true,
  metadata: {
    tags: ['scenario_recording_replay'],
    description: 'Corner case recorder replay'
  }
};

function formatFileSize(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return '0 B';
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function textFromUnknown(value: unknown) {
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  return String(value);
}

export function ScenarioRecordingsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [mapFilter, setMapFilter] = useState('');
  const [tagFilter, setTagFilter] = useState('');
  const [cornerCaseFilter, setCornerCaseFilter] = useState('');
  const [determinismFilter, setDeterminismFilter] = useState('');
  const [selectedRecordingId, setSelectedRecordingId] = useState<string | null>(null);
  const [launchDraft, setLaunchDraft] =
    useState<ScenarioRecordingLaunchPayload>(defaultLaunchPayload);

  const recordingsQuery = useQuery({
    queryKey: [
      'scenario-recordings',
      { mapFilter, tagFilter, cornerCaseFilter, determinismFilter }
    ],
    queryFn: () =>
      listScenarioRecordings({
        map_name: mapFilter,
        tag: tagFilter,
        corner_case_label: cornerCaseFilter,
        determinism_level: determinismFilter
      })
  });
  const sensorProfilesQuery = useQuery({
    queryKey: ['sensor-profiles'],
    queryFn: listSensorProfiles
  });

  const recordings = recordingsQuery.data?.recordings ?? [];
  const sensorProfiles = sensorProfilesQuery.data ?? [];
  const selectedRecording =
    recordings.find((item) => item.recording_id === selectedRecordingId) ??
    recordings[0] ??
    null;
  const selectedProfile =
    sensorProfiles.find((profile) => profile.sensor_profile_id === launchDraft.sensor_profile_id) ??
    null;
  const previewSensors = useMemo(
    () => selectedProfile?.sensors.filter((sensor) => sensor.type === 'sensor.camera.rgb') ?? [],
    [selectedProfile]
  );
  const selectedPreviewSensor =
    previewSensors.find((sensor) => sensor.id === launchDraft.preview_sensor_id) ?? null;
  const canLaunchReplay = Boolean(launchDraft.sensor_profile_id && launchDraft.preview_sensor_id);

  useEffect(() => {
    if (!selectedRecordingId && recordings.length > 0) {
      setSelectedRecordingId(recordings[0].recording_id);
    }
    if (
      selectedRecordingId &&
      recordings.length > 0 &&
      !recordings.some((item) => item.recording_id === selectedRecordingId)
    ) {
      setSelectedRecordingId(recordings[0].recording_id);
    }
  }, [recordings, selectedRecordingId]);

  useEffect(() => {
    if (!launchDraft.sensor_profile_id && sensorProfiles[0]) {
      const firstPreviewSensor = sensorProfiles[0].sensors.find(
        (sensor) => sensor.type === 'sensor.camera.rgb'
      );
      setLaunchDraft((current) => ({
        ...current,
        sensor_profile_id: sensorProfiles[0].sensor_profile_id,
        preview_sensor_id: current.preview_sensor_id || firstPreviewSensor?.id || '',
        fixed_delta_seconds: sensorProfiles[0].fixed_delta_seconds
      }));
    }
  }, [launchDraft.sensor_profile_id, sensorProfiles]);

  useEffect(() => {
    if (!selectedProfile) {
      if (launchDraft.preview_sensor_id) {
        setLaunchDraft((current) => ({ ...current, preview_sensor_id: '' }));
      }
      return;
    }

    if (previewSensors.some((sensor) => sensor.id === launchDraft.preview_sensor_id)) {
      return;
    }

    setLaunchDraft((current) => ({
      ...current,
      preview_sensor_id: previewSensors[0]?.id || ''
    }));
  }, [launchDraft.preview_sensor_id, previewSensors, selectedProfile]);

  useEffect(() => {
    if (!selectedRecording) {
      return;
    }
    setLaunchDraft((current) => ({
      ...current,
      start_seconds: selectedRecording.recommended_start_seconds ?? current.start_seconds,
      duration_seconds:
        selectedRecording.recommended_duration_seconds ??
        selectedRecording.duration_seconds ??
        current.duration_seconds
    }));
  }, [selectedRecording?.recording_id]);

  const mapOptions = useMemo(
    () => Array.from(new Set(recordings.map((item) => item.map_name))).sort(),
    [recordings]
  );
  const tagOptions = useMemo(
    () => Array.from(new Set(recordings.flatMap((item) => item.tags))).sort(),
    [recordings]
  );
  const cornerCaseOptions = useMemo(
    () => Array.from(new Set(recordings.flatMap((item) => item.corner_case_labels))).sort(),
    [recordings]
  );

  const launchMutation = useMutation({
    mutationFn: (recording: ScenarioRecording) =>
      launchScenarioRecording(recording.recording_id, launchDraft),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ['scenario-recordings'] });
      void queryClient.invalidateQueries({ queryKey: ['runs'] });
      navigate(`/executions/${result.run.run_id}`);
    }
  });

  const updateLaunchDraft = <Key extends keyof ScenarioRecordingLaunchPayload>(
    key: Key,
    value: ScenarioRecordingLaunchPayload[Key]
  ) => {
    setLaunchDraft((current) => ({ ...current, [key]: value }));
  };

  function selectSensorProfile(profileId: string) {
    const profile = sensorProfiles.find((item) => item.sensor_profile_id === profileId);
    const firstPreviewSensor = profile?.sensors.find(
      (sensor) => sensor.type === 'sensor.camera.rgb'
    );
    setLaunchDraft((current) => ({
      ...current,
      sensor_profile_id: profileId,
      preview_sensor_id: firstPreviewSensor?.id || '',
      fixed_delta_seconds: profile?.fixed_delta_seconds ?? current.fixed_delta_seconds
    }));
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="场景资产库"
        eyebrow="场景 / 可复现实验"
        chips={['CARLA recorder', 'Corner case', 'Fixed delta']}
        description="管理 CARLA recorder 资产，并从资产创建绑定 live sensor profile 与同步时间基的可复现 replay run。"
        actions={
          <>
            <Link className="horizon-button-secondary" to="/executions">
              查看执行台
            </Link>
            {selectedRecording && (
              <button
                className="horizon-button"
                disabled={launchMutation.isPending || !canLaunchReplay}
                onClick={() => launchMutation.mutate(selectedRecording)}
                type="button"
              >
                创建回放运行
              </button>
            )}
          </>
        }
      />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
        <div className="space-y-5">
          <Panel
            eyebrow="过滤"
            title="资产检索"
            subtitle="按地图、标签、corner case 和 determinism level 缩小 recorder 资产范围。"
          >
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
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
                <span>标签</span>
                <select value={tagFilter} onChange={(event) => setTagFilter(event.target.value)}>
                  <option value="">全部标签</option>
                  {tagOptions.map((tag) => (
                    <option key={tag} value={tag}>
                      {tag}
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
                  <option value="">全部类型</option>
                  {cornerCaseOptions.map((label) => (
                    <option key={label} value={label}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="form-field">
                <span>Determinism</span>
                <select
                  value={determinismFilter}
                  onChange={(event) => setDeterminismFilter(event.target.value)}
                >
                  <option value="">全部等级</option>
                  {determinismOptions.map((level) => (
                    <option key={level} value={level}>
                      {level}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </Panel>

          <Panel
            eyebrow="Recorder Assets"
            title="资产列表"
            subtitle="v1 资产只承诺世界状态 replay；芯片输入 repeatability 由 live sensor profile、fixed-delta 和 HIL sidecar 时间同步保证。"
          >
            {recordingsQuery.isLoading ? (
              <EmptyState title="资产库加载中" description="正在读取 SQLite 资产索引。" />
            ) : recordingsQuery.isError ? (
              <EmptyState
                title="资产库加载失败"
                description={
                  recordingsQuery.error instanceof Error
                    ? recordingsQuery.error.message
                    : '接口异常。'
                }
              />
            ) : recordings.length === 0 ? (
              <EmptyState
                title="还没有场景资产"
                description="在执行详情页找到带 recorder 文件的 run，点击发布为场景资产后会显示在这里。"
              />
            ) : (
              <div className="space-y-3">
                {recordings.map((recording) => (
                  <button
                    key={recording.recording_id}
                    className={clsx(
                      'w-full rounded-[20px] border px-4 py-4 text-left transition',
                      selectedRecording?.recording_id === recording.recording_id
                        ? 'border-brand-500 bg-brand-50/80 shadow-sm'
                        : 'border-secondaryGray-200 bg-white/80 hover:border-brand-200'
                    )}
                    onClick={() => setSelectedRecordingId(recording.recording_id)}
                    type="button"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-extrabold text-navy-900">
                          {recording.scenario_name}
                        </p>
                        <p className="mt-1 text-xs text-secondaryGray-500">
                          {recording.recording_id} / {recording.map_name}
                        </p>
                      </div>
                      <StatusPill status={recording.source_run_status ?? 'UNKNOWN'} />
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {recording.corner_case_labels.map((label) => (
                        <span key={label} className="rounded-full bg-orange-50 px-2 py-1 text-xs font-bold text-orange-700">
                          {label}
                        </span>
                      ))}
                      {recording.tags.map((tag) => (
                        <span key={tag} className="rounded-full bg-secondaryGray-100 px-2 py-1 text-xs font-bold text-secondaryGray-600">
                          {tag}
                        </span>
                      ))}
                    </div>
                    <p className="mt-3 text-xs text-secondaryGray-500">
                      {formatFileSize(recording.recorder_file_size_bytes)} / {recording.determinism_level}
                    </p>
                  </button>
                ))}
              </div>
            )}
          </Panel>
        </div>

        <aside className="space-y-5">
          <Panel
            eyebrow="Replay Context"
            title="执行上下文"
            subtitle="创建 replay run 时会强制 synchronous/fixed-delta，并使用 CARLA live sensor profile。"
            actions={selectedRecording ? <StatusPill status="READY" /> : undefined}
          >
            {selectedRecording ? (
              <div className="space-y-5">
                <KeyValueGrid
                  items={[
                    { label: '资产名称', value: selectedRecording.name ?? selectedRecording.scenario_name },
                    { label: '资产 ID', value: selectedRecording.recording_id },
                    { label: '来源 run', value: selectedRecording.source_run_id },
                    { label: '来源', value: selectedRecording.source_type ?? selectedRecording.source_provider ?? '-' },
                    { label: '地图', value: selectedRecording.map_name },
                    { label: 'CARLA', value: selectedRecording.carla_version ?? '-' },
                    { label: '天气', value: textFromUnknown(selectedRecording.weather['preset']) },
                    {
                      label: '背景车辆',
                      value: textFromUnknown(selectedRecording.traffic_density['num_vehicles'])
                    },
                    {
                      label: '行人',
                      value: textFromUnknown(selectedRecording.traffic_density['num_walkers'])
                    },
                    {
                      label: '推荐窗口',
                      value:
                        selectedRecording.recommended_duration_seconds != null
                          ? `${selectedRecording.recommended_start_seconds ?? 0}s + ${selectedRecording.recommended_duration_seconds}s`
                          : '-'
                    },
                    {
                      label: '文件大小',
                      value: formatFileSize(selectedRecording.recorder_file_size_bytes)
                    },
                    {
                      label: '创建时间',
                      value: formatDateTime(selectedRecording.created_at_utc)
                    }
                  ]}
                />

                <div className="space-y-3 border-t border-border-glass pt-4">
                  <label className="form-field">
                    <span>Sensor profile</span>
                    <select
                      value={launchDraft.sensor_profile_id}
                      onChange={(event) => selectSensorProfile(event.target.value)}
                    >
                      <option value="">选择传感器配置</option>
                      {sensorProfiles.map((profile: SensorProfile) => (
                        <option key={profile.sensor_profile_id} value={profile.sensor_profile_id}>
                          {profile.name} / {profile.sensor_profile_id}
                        </option>
                      ))}
                    </select>
                  </label>
                  {selectedProfile ? (
                    <div className="rounded-lg border border-secondaryGray-200 bg-secondaryGray-50 px-3 py-2 text-xs font-semibold text-secondaryGray-600">
                      hash {selectedProfile.profile_hash.slice(0, 12)}... / {selectedProfile.fixed_delta_seconds}s / {selectedProfile.expected_fps} FPS / {selectedProfile.hil_output_mode}
                    </div>
                  ) : sensorProfilesQuery.isError ? (
                    <p className="text-sm text-rose-600">{sensorProfilesQuery.error.message}</p>
                  ) : null}
                  <label className="form-field">
                    <span>OpenCV preview sensor</span>
                    <select
                      disabled={!selectedProfile}
                      value={launchDraft.preview_sensor_id ?? ''}
                      onChange={(event) => updateLaunchDraft('preview_sensor_id', event.target.value)}
                    >
                      <option value="">选择 RGB 相机</option>
                      {previewSensors.map((sensor) => (
                        <option key={sensor.id} value={sensor.id}>
                          {sensor.id} / {sensor.width ?? 1920}x{sensor.height ?? 1080}
                        </option>
                      ))}
                    </select>
                  </label>
                  {selectedProfile && previewSensors.length === 0 ? (
                    <p className="text-sm text-rose-600">当前 SensorProfile 没有 RGB 相机。</p>
                  ) : selectedPreviewSensor ? (
                    <div className="rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700">
                      {selectedPreviewSensor.id} / FOV {selectedPreviewSensor.fov ?? selectedPreviewSensor.horizontal_fov ?? 90} / tick {textFromUnknown(selectedPreviewSensor.attributes?.sensor_tick ?? selectedPreviewSensor.reading_frequency ?? 'profile')}
                    </div>
                  ) : null}
                  <label className="form-field">
                    <span>开始秒数</span>
                    <input
                      min={0}
                      step={0.1}
                      type="number"
                      value={launchDraft.start_seconds}
                      onChange={(event) =>
                        updateLaunchDraft('start_seconds', Number(event.target.value))
                      }
                    />
                  </label>
                  <label className="form-field">
                    <span>持续秒数</span>
                    <input
                      min={0.1}
                      step={0.1}
                      type="number"
                      value={launchDraft.duration_seconds}
                      onChange={(event) =>
                        updateLaunchDraft('duration_seconds', Number(event.target.value))
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
                      value={launchDraft.fixed_delta_seconds ?? selectedProfile?.fixed_delta_seconds ?? 0.05}
                      onChange={(event) =>
                        updateLaunchDraft('fixed_delta_seconds', Number(event.target.value))
                      }
                    />
                  </label>
                  <label className="form-field">
                    <span>Sensor warmup</span>
                    <input
                      min={0}
                      max={60}
                      step={0.1}
                      type="number"
                      value={launchDraft.sensor_warmup_seconds}
                      onChange={(event) =>
                        updateLaunchDraft('sensor_warmup_seconds', Number(event.target.value))
                      }
                    />
                  </label>
                  <label className="form-field">
                    <span>Timebase</span>
                    <select
                      value={launchDraft.timebase}
                      onChange={(event) => updateLaunchDraft('timebase', event.target.value)}
                    >
                      <option value="synchronous_fixed_delta">synchronous_fixed_delta</option>
                    </select>
                  </label>
                  <label className="form-field">
                    <span>HIL clock</span>
                    <select
                      value={launchDraft.hil_clock_mode}
                      onChange={(event) => updateLaunchDraft('hil_clock_mode', event.target.value)}
                    >
                      <option value="fixed_delta">fixed_delta</option>
                      <option value="wall_clock">wall_clock</option>
                    </select>
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
                    disabled={launchMutation.isPending || !canLaunchReplay}
                    onClick={() => launchMutation.mutate(selectedRecording)}
                    type="button"
                  >
                    {launchMutation.isPending ? '创建中...' : '创建回放运行'}
                  </button>
                  {launchMutation.error && (
                    <p className="text-sm text-rose-600">
                      {launchMutation.error.message}
                    </p>
                  )}
                </div>
              </div>
            ) : (
              <EmptyState title="未选择资产" description="先从左侧选择一个 recorder 资产。" />
            )}
          </Panel>
        </aside>
      </div>
    </div>
  );
}
