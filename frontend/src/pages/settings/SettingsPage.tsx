import { CompactPageHeader } from '../../components/common/CompactPageHeader';
import { DetailPanel } from '../../components/common/DetailPanel';
import { ThemeModeSwitch } from '../../components/layout/ThemeModeSwitch';
import { useTheme } from '../../features/theme/state';

const themePreferenceLabel = {
  light: '浅色',
  dark: '深色',
  system: '跟随系统'
} as const;

const resolvedThemeLabel = {
  light: '浅色',
  dark: '深色'
} as const;

const platformConventions = [
  {
    label: '品牌标识',
    title: 'SimChip Nexus',
    description: '控制台与展示页统一使用芯境智测平台命名，突出车载算力芯片测评定位。'
  },
  {
    label: '业务边界',
    title: '展示页与控制台分离',
    description: '首页负责平台能力展示；控制台负责项目、任务、设备、执行和报告管理。'
  },
  {
    label: '数据链路',
    title: '从仿真到结论',
    description: '围绕 CARLA 场景、虚拟传感器注入、待测端运行和 Web 评测分析组织流程。'
  }
];

export function SettingsPage() {
  const { preference, resolvedTheme } = useTheme();

  return (
    <div className="page-stack">
      <CompactPageHeader
        stepLabel="Console Settings"
        title="界面设置"
        description="管理控制台主题偏好，并查看与展示页一致的平台表达约定。"
        contextSummary={`当前偏好: ${themePreferenceLabel[preference]} / 生效主题: ${resolvedThemeLabel[resolvedTheme]}`}
      />

      <DetailPanel subtitle="主题偏好会应用到侧边栏、列表、图表和运行监控等控制台界面。" title="主题模式">
        <ThemeModeSwitch />
      </DetailPanel>

      <DetailPanel subtitle="保持控制台文案与 landing page 的平台定位一致。" title="平台标识与使用约定">
        <div className="grid gap-3 md:grid-cols-3">
          {platformConventions.map((item) => (
            <article
              className="rounded-[22px] border border-border-glass bg-[var(--surface-glass)] p-5"
              key={item.label}
            >
              <span className="text-xs font-extrabold uppercase tracking-[0.18em] text-text-muted">{item.label}</span>
              <strong className="mt-3 block text-lg text-text">{item.title}</strong>
              <p className="mt-2 text-sm leading-6 text-text-muted">{item.description}</p>
            </article>
          ))}
        </div>
      </DetailPanel>
    </div>
  );
}
