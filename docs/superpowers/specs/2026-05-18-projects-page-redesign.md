# ProjectsPage 重构设计文档

**日期：** 2026-05-18
**目标：** 把页面重心从"展示所有信息"转移到"帮用户完成一件事"，减少垂直堆叠，建立清晰的信息层级。

---

## 背景

当前页面（重构前）存在三个核心问题：

1. **信息层级平坦**：MetricCards、全局状态概览 Panel、甜甜圈图、项目列表、项目详情、右侧栏三个面板，视觉权重几乎相同，用户不知道先看哪里。
2. **内容重复**：MetricCards 和"全局状态概览"Panel 说同一件事；右侧栏三个面板和主面板总览 tab 说同一件事。
3. **页面过长**：用户需要大量滚动才能到达核心操作区（选项目、看结果、决定下一步）。

上一轮已删除右侧栏 aside、MetricCard 平台健康/最近异常、全局状态概览 Panel 的 hero 文字块。本次完成剩余重构。

---

## 目标布局

```
┌─────────────────────────────────────────────────────┐
│  PageHeader（标题 + 操作按钮）                       │
├─────────────────────────────────────────────────────┤
│  状态条（Pill 风格）：API · 队列 · 设备 · 采集 · 异常↗│
├──────────────┬──────────────────────────────────────┤
│              │                                      │
│  项目列表    │  选中项目的详情                      │
│  （左侧栏）  │  tabs: 总览 / 报告归档 / 运行态      │
│              │                                      │
│              │  WorkflowNextStep（底部）             │
├──────────────┴──────────────────────────────────────┤
│  ▶ 平台健康详情（可折叠，默认收起）                  │
│    [运行分布] [采集分布] [网关分布]                  │
│    异常队列（横向条）                                │
└─────────────────────────────────────────────────────┘
```

---

## 组件设计

### 1. 状态条（PlatformStatusBar）

**位置：** PageHeader 下方，主内容区上方。

**内容（左到右）：**
- API 状态 pill（绿色背景 = 在线，红色 = 离线）
- 执行队列 pill（数字）
- 在线设备 pill（数字）
- 运行中采集 pill（数字）
- 异常数 pill（红色背景，有异常时显示；点击跳转到 `/executions` 或 `/devices`）

**交互：**
- 异常数 pill 点击直接导航（Link to `/executions`，因为大多数异常来自执行失败）
- 其余 pill 纯展示，不可交互

**实现方式：** 内联在 ProjectsPage JSX 中，不抽取为独立组件（逻辑简单，数据已在页面 queries 中）。

**CSS：** 新增 `.project-console__status-bar` 和 `.project-console__status-pill` 系列类，写入 `globals.css`。

---

### 2. 删除"全局状态概览"Panel

整个 `<Panel title="全局状态概览">` 块（含 3 个快捷卡片：最近采集、最近网关、执行器队列）直接删除。

这些信息的去向：
- 执行器状态 → 状态条 API pill + 队列 pill 已覆盖
- 最近采集 → 状态条"采集中"pill 已覆盖
- 最近网关 → 状态条"在线设备"pill 已覆盖

---

### 3. 删除"优先排查队列"Panel（独立面板）

当前"优先排查队列"Panel 是一个独立的右侧面板，和"全局状态概览"并排。删除后，异常信息移入底部可折叠区的异常条。

---

### 4. 底部可折叠区（PlatformHealthDetails）

**默认状态：** 收起，只显示触发行（▶ 平台健康详情）。

**展开后布局（方案 B）：**
- 第一行：3 个甜甜圈图（运行分布 / 采集分布 / 网关分布），`grid-template-columns: 1fr 1fr 1fr`
- 第二行：异常队列横向条，显示最近 3–6 条异常，每条可点击跳转

**状态管理：** `useState<boolean>` 控制展开/收起，key 为 `healthExpanded`。

**实现方式：** 内联在 ProjectsPage JSX 中。

**CSS：** 新增 `.project-console__health-section`、`.project-console__health-trigger`、`.project-console__incident-bar` 系列类。

---

### 5. 主布局调整

当前 `project-console__layout` 是三列（280px + 1fr + 300px）。右侧栏已在上一轮删除，现在改为两列：

```css
.project-console__layout {
  grid-template-columns: 280px minmax(0, 1fr);
}
```

（已在上一轮实际生效，本次确认 CSS 无残留。）

---

## 数据依赖

所有数据已在现有 queries 中：

| 状态条字段 | 数据来源 |
|-----------|---------|
| API 状态 | `systemQuery.data?.api.status` |
| 执行队列 | `systemQuery.data?.executor.pending_commands` |
| 在线设备 | `devicesWorkspaceQuery.data?.summary.online_device_count` |
| 运行中采集 | `devicesWorkspaceQuery.data?.summary.running_capture_count` |
| 异常数 | `recentIncidents.length` |

底部可折叠区的甜甜圈图和异常队列数据已在 `systemQuery` 和 `recentIncidents` 中，无需新增 query。

---

## 不在本次范围内

- 修改 tabs 内容（总览 / 报告归档 / 运行态）
- 修改 WorkflowNextStep 组件
- 修改 PageHeader
- 响应式断点适配（移动端）
- 动画/过渡效果（折叠展开可用简单 CSS max-height transition）

---

## 文件变更清单

| 文件 | 变更 |
|------|------|
| `frontend/src/pages/projects/ProjectsPage.tsx` | 删除全局状态概览 Panel、优先排查队列 Panel；新增状态条 JSX；新增可折叠健康详情区；3 个甜甜圈图移入折叠区 |
| `frontend/src/styles/globals.css` | 新增状态条和折叠区 CSS 类 |
