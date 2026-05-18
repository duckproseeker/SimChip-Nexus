import { useEffect, useMemo, useState } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import { Link } from 'react-router-dom';

import {
  copySensorProfile,
  createSensorProfile,
  listSensorProfiles,
  updateSensorProfile
} from '../../api/sensorProfiles';
import type { SensorProfile, SensorProfileSavePayload, SensorSpec } from '../../api/types';
import { EmptyState } from '../../components/common/EmptyState';
import { KeyValueGrid } from '../../components/common/KeyValueGrid';
import { PageHeader } from '../../components/common/PageHeader';
import { Panel } from '../../components/common/Panel';
import { formatDateTime } from '../../lib/format';

interface SensorProfileEditor {
  sensor_profile_id: string;
  name: string;
  description: string;
  vehicle_model: string;
  fixed_delta_seconds: number;
  expected_fps: number;
  output_mode: string;
  hil_output_mode: string;
  metadata_text: string;
  sensors_text: string;
  is_new: boolean;
}

function emptyEditor(): SensorProfileEditor {
  return {
    sensor_profile_id: '',
    name: '',
    description: '',
    vehicle_model: '',
    fixed_delta_seconds: 0.05,
    expected_fps: 20,
    output_mode: 'carla_live',
    hil_output_mode: 'camera_open_loop',
    metadata_text: '{}',
    sensors_text: JSON.stringify(
      [
        {
          id: 'FrontRGB',
          type: 'sensor.camera.rgb',
          x: 1.5,
          y: 0,
          z: 1.7,
          roll: 0,
          pitch: 0,
          yaw: 0,
          width: 1920,
          height: 1080,
          fov: 90
        }
      ],
      null,
      2
    ),
    is_new: true
  };
}

function profileToEditor(profile: SensorProfile): SensorProfileEditor {
  const metadata = { ...profile.metadata };
  delete metadata.vehicle_model;
  return {
    sensor_profile_id: profile.sensor_profile_id,
    name: profile.name,
    description: profile.description,
    vehicle_model: profile.vehicle_model ?? '',
    fixed_delta_seconds: profile.fixed_delta_seconds,
    expected_fps: profile.expected_fps,
    output_mode: profile.output_mode,
    hil_output_mode: profile.hil_output_mode,
    metadata_text: JSON.stringify(metadata, null, 2),
    sensors_text: JSON.stringify(profile.sensors, null, 2),
    is_new: false
  };
}

function parseJsonObject(raw: string, label: string) {
  const normalized = raw.trim();
  if (!normalized) {
    return {};
  }
  const parsed = JSON.parse(normalized) as unknown;
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${label} 必须是 JSON 对象`);
  }
  return parsed as Record<string, unknown>;
}

function parseSensors(raw: string) {
  const parsed = JSON.parse(raw.trim() || '[]') as unknown;
  if (!Array.isArray(parsed)) {
    throw new Error('Sensors 必须是 JSON 数组');
  }
  return parsed as SensorSpec[];
}

function editorToPayload(editor: SensorProfileEditor): SensorProfileSavePayload {
  const metadata = parseJsonObject(editor.metadata_text, 'Metadata');
  if (editor.vehicle_model.trim()) {
    metadata.vehicle_model = editor.vehicle_model.trim();
  }
  return {
    sensor_profile_id: editor.sensor_profile_id.trim(),
    name: editor.name.trim(),
    profile_name: editor.sensor_profile_id.trim(),
    display_name: editor.name.trim(),
    description: editor.description.trim(),
    vehicle_model: editor.vehicle_model.trim() || null,
    fixed_delta_seconds: editor.fixed_delta_seconds,
    expected_fps: editor.expected_fps,
    output_mode: editor.output_mode.trim(),
    hil_output_mode: editor.hil_output_mode.trim(),
    metadata,
    sensors: parseSensors(editor.sensors_text)
  };
}

function shortHash(value: string) {
  return value ? `${value.slice(0, 12)}...${value.slice(-8)}` : '-';
}

export function SensorProfilesPage() {
  const queryClient = useQueryClient();
  const [selectedProfileId, setSelectedProfileId] = useState('');
  const [editor, setEditor] = useState<SensorProfileEditor>(emptyEditor);
  const [editorError, setEditorError] = useState<string | null>(null);

  const profilesQuery = useQuery({
    queryKey: ['sensor-profiles'],
    queryFn: listSensorProfiles
  });
  const profiles = profilesQuery.data ?? [];
  const selectedProfile =
    profiles.find((item) => item.sensor_profile_id === selectedProfileId) ?? null;
  const sortedProfiles = useMemo(
    () => [...profiles].sort((a, b) => a.name.localeCompare(b.name)),
    [profiles]
  );

  useEffect(() => {
    if (!selectedProfileId && sortedProfiles[0]) {
      setSelectedProfileId(sortedProfiles[0].sensor_profile_id);
      setEditor(profileToEditor(sortedProfiles[0]));
    }
  }, [sortedProfiles, selectedProfileId]);

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload = editorToPayload(editor);
      if (editor.is_new) {
        return createSensorProfile(payload);
      }
      return updateSensorProfile(editor.sensor_profile_id, payload);
    },
    onMutate: () => setEditorError(null),
    onError: (error) => {
      setEditorError(error instanceof Error ? error.message : '保存失败');
    },
    onSuccess: async (profile) => {
      setSelectedProfileId(profile.sensor_profile_id);
      setEditor(profileToEditor(profile));
      await queryClient.invalidateQueries({ queryKey: ['sensor-profiles'] });
    }
  });

  const copyMutation = useMutation({
    mutationFn: (profile: SensorProfile) =>
      copySensorProfile(profile.sensor_profile_id, {
        sensor_profile_id: `${profile.sensor_profile_id}_copy_${Date.now().toString(36)}`,
        name: `${profile.name} Copy`
      }),
    onSuccess: async (profile) => {
      setSelectedProfileId(profile.sensor_profile_id);
      setEditor(profileToEditor(profile));
      await queryClient.invalidateQueries({ queryKey: ['sensor-profiles'] });
    }
  });

  function selectProfile(profile: SensorProfile) {
    setSelectedProfileId(profile.sensor_profile_id);
    setEditor(profileToEditor(profile));
    setEditorError(null);
  }

  function updateEditor<K extends keyof SensorProfileEditor>(key: K, value: SensorProfileEditor[K]) {
    setEditor((current) => ({ ...current, [key]: value }));
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="传感器库"
        eyebrow="Sensor Profile Library"
        chips={['SQLite', 'Profile hash', 'Live sensors']}
        description="维护可复用的 CARLA live sensor profile；每次 replay run 会冻结当前 snapshot 和 profile_hash。"
        actions={
          <div className="flex flex-wrap gap-3">
            <Link className="horizon-button-secondary" to="/scenario-recordings">
              去场景资产库
            </Link>
            <button
              className="horizon-button"
              onClick={() => {
                setSelectedProfileId('');
                setEditor(emptyEditor());
                setEditorError(null);
              }}
              type="button"
            >
              新建 Profile
            </button>
          </div>
        }
      />

      <div className="grid gap-5 xl:grid-cols-[340px_minmax(0,1fr)]">
        <Panel title="Profile 列表" subtitle="SQLite 为主存储，旧 YAML 会在首次读取时导入。">
          {profilesQuery.isLoading ? (
            <EmptyState title="正在加载" description="读取传感器库。" />
          ) : profilesQuery.isError ? (
            <EmptyState title="加载失败" description={profilesQuery.error.message} />
          ) : sortedProfiles.length === 0 ? (
            <EmptyState title="还没有 profile" description="创建一个 sensor profile 后即可用于 replay。" />
          ) : (
            <div className="space-y-3">
              {sortedProfiles.map((profile) => (
                <button
                  key={profile.sensor_profile_id}
                  className={clsx(
                    'w-full rounded-lg border px-4 py-3 text-left transition',
                    selectedProfileId === profile.sensor_profile_id
                      ? 'border-brand-500 bg-brand-50/80'
                      : 'border-secondaryGray-200 bg-white/80 hover:border-brand-200'
                  )}
                  onClick={() => selectProfile(profile)}
                  type="button"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-extrabold text-navy-900">{profile.name}</p>
                      <p className="mt-1 truncate text-xs text-secondaryGray-500">
                        {profile.sensor_profile_id}
                      </p>
                    </div>
                    <span className="rounded-full bg-secondaryGray-100 px-2 py-1 text-xs font-bold text-secondaryGray-600">
                      {profile.sensors.length}
                    </span>
                  </div>
                  <p className="mt-3 text-xs text-secondaryGray-500">
                    {profile.fixed_delta_seconds}s / {profile.expected_fps} FPS / {shortHash(profile.profile_hash)}
                  </p>
                </button>
              ))}
            </div>
          )}
        </Panel>

        <div className="space-y-5">
          <Panel
            title="Profile 摘要"
            subtitle="用于 replay run 冻结和审计的关键字段。"
            actions={
              selectedProfile ? (
                <button
                  className="horizon-button-secondary"
                  disabled={copyMutation.isPending}
                  onClick={() => copyMutation.mutate(selectedProfile)}
                  type="button"
                >
                  {copyMutation.isPending ? '复制中...' : '复制 Profile'}
                </button>
              ) : undefined
            }
          >
            {selectedProfile ? (
              <KeyValueGrid
                items={[
                  { label: 'Profile ID', value: selectedProfile.sensor_profile_id },
                  { label: 'Profile hash', value: shortHash(selectedProfile.profile_hash) },
                  { label: 'Fixed delta', value: `${selectedProfile.fixed_delta_seconds}s` },
                  { label: 'Expected FPS', value: selectedProfile.expected_fps },
                  { label: 'Output mode', value: selectedProfile.output_mode },
                  { label: 'HIL mode', value: selectedProfile.hil_output_mode },
                  { label: 'Vehicle', value: selectedProfile.vehicle_model ?? '-' },
                  { label: 'Updated', value: formatDateTime(selectedProfile.updated_at_utc) }
                ]}
              />
            ) : (
              <EmptyState title="未选择 profile" description="选择或创建一个传感器配置。" />
            )}
          </Panel>

          <Panel
            title={editor.is_new ? '新建 Profile' : '编辑 Profile'}
            subtitle="保存后后端会重新计算 profile_hash。"
            actions={
              <button
                className="horizon-button"
                disabled={saveMutation.isPending}
                onClick={() => saveMutation.mutate()}
                type="button"
              >
                {saveMutation.isPending ? '保存中...' : editor.is_new ? '创建' : '保存'}
              </button>
            }
          >
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <label className="form-field">
                <span>Profile ID</span>
                <input
                  disabled={!editor.is_new}
                  value={editor.sensor_profile_id}
                  onChange={(event) => updateEditor('sensor_profile_id', event.target.value)}
                />
              </label>
              <label className="form-field">
                <span>名称</span>
                <input value={editor.name} onChange={(event) => updateEditor('name', event.target.value)} />
              </label>
              <label className="form-field">
                <span>车型</span>
                <input
                  value={editor.vehicle_model}
                  onChange={(event) => updateEditor('vehicle_model', event.target.value)}
                />
              </label>
              <label className="form-field">
                <span>描述</span>
                <input
                  value={editor.description}
                  onChange={(event) => updateEditor('description', event.target.value)}
                />
              </label>
              <label className="form-field">
                <span>Fixed delta</span>
                <input
                  min={0.001}
                  max={0.2}
                  step={0.001}
                  type="number"
                  value={editor.fixed_delta_seconds}
                  onChange={(event) => updateEditor('fixed_delta_seconds', Number(event.target.value))}
                />
              </label>
              <label className="form-field">
                <span>Expected FPS</span>
                <input
                  min={0.1}
                  max={240}
                  step={0.1}
                  type="number"
                  value={editor.expected_fps}
                  onChange={(event) => updateEditor('expected_fps', Number(event.target.value))}
                />
              </label>
              <label className="form-field">
                <span>Output mode</span>
                <select value={editor.output_mode} onChange={(event) => updateEditor('output_mode', event.target.value)}>
                  <option value="carla_live">carla_live</option>
                  <option value="record_artifacts">record_artifacts</option>
                </select>
              </label>
              <label className="form-field">
                <span>HIL mode</span>
                <select
                  value={editor.hil_output_mode}
                  onChange={(event) => updateEditor('hil_output_mode', event.target.value)}
                >
                  <option value="camera_open_loop">camera_open_loop</option>
                  <option value="frame_stream">frame_stream</option>
                  <option value="disabled">disabled</option>
                </select>
              </label>
            </div>

            <div className="mt-4 grid gap-4 xl:grid-cols-2">
              <label className="form-field">
                <span>Metadata JSON</span>
                <textarea
                  className="min-h-[180px]"
                  value={editor.metadata_text}
                  onChange={(event) => updateEditor('metadata_text', event.target.value)}
                />
              </label>
              <label className="form-field">
                <span>Sensors JSON</span>
                <textarea
                  className="min-h-[180px] font-mono text-xs"
                  value={editor.sensors_text}
                  onChange={(event) => updateEditor('sensors_text', event.target.value)}
                />
              </label>
            </div>

            {editorError ? <p className="mt-3 text-sm font-semibold text-rose-600">{editorError}</p> : null}
            {copyMutation.error ? (
              <p className="mt-3 text-sm font-semibold text-rose-600">{copyMutation.error.message}</p>
            ) : null}
          </Panel>
        </div>
      </div>
    </div>
  );
}
