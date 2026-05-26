# 节点式流程编排重构设计规格

**日期：** 2026-05-25
**状态：** 已确认，待实施

---

## 背景与目标

当前流程编排界面（v1）使用粗粒度节点：一个 `ScenarioConfigNode` 包含场景、地图、天气三个字段，一个 `SensorProfileNode` 只能输入 Profile ID。用户无法直观理解各字段含义，也无法在画布上灵活组合传感器。

本次重构将每个可配置维度拆分为独立节点，用连线表达依赖关系，实现真正的节点式编排。同时区分**实时仿真**和**录制回放**两条执行路径，为后续 corner case 场景库接入打好基础。

---

## 节点类型全集

### 流程骨架类

| 节点类型 | 标识符 | 说明 |
|---------|--------|------|
| 项目 | `project` | 选择业务项目，提供 project_id 上下文 |
| 实时仿真 | `live_run` | 接收环境+传感器配置，触发 CARLA live run |
| 录制回放 | `replay_run` | 接收录制文件+传感器配置，触发 replay run |
| 报告 | `report` | 展示执行结果，链接到报告详情 |

### 环境配置类（仅用于实时仿真）

| 节点类型 | 标识符 | 说明 |
|---------|--------|------|
| 场景 | `scenario` | 从场景目录选择，存 scenario_name |
| 地图 | `map` | 从 Town01_Opt…Town10HD_Opt 选择 |
| 天气 | `weather` | 19 个预设 + 自定义滑块 |

### 场景录制类（仅用于录制回放）

| 节点类型 | 标识符 | 说明 |
|---------|--------|------|
| 场景录制 | `recording` | 从 scenario-recordings 库选择录制文件 |

### 传感器类

| 节点类型 | 标识符 | CARLA 类型 |
|---------|--------|-----------|
| 摄像头 | `sensor_camera` | sensor.camera.rgb |
| 激光雷达 | `sensor_lidar` | sensor.lidar.ray_cast |
| 毫米波雷达 | `sensor_radar` | sensor.other.radar |
| GNSS | `sensor_gnss` | sensor.other.gnss |
| IMU | `sensor_imu` | sensor.other.imu |

---

## 两条执行路径

### 路径 A：实时仿真

```
[项目] ──────────────────────────────────────┐
[场景] ──────────────────────────────────────┤
[地图] ──────────────────────────────────────┼──→ [实时仿真] ──→ [报告]
[天气] ──────────────────────────────────────┤
[摄像头 × N] ────────────────────────────────┤
[激光雷达 × N] ──────────────────────────────┤
[毫米波雷达 × N] ────────────────────────────┘
```

**实时仿真节点输入端口：**

| 端口 ID | 接受节点 | 连线数 |
|---------|---------|--------|
| `project` | project | 1 |
| `scenario` | scenario | 1 |
| `map` | map | 1 |
| `weather` | weather | 1 |
| `sensor` | 任意传感器类型 | 1–N |

### 路径 B：录制回放

```
[项目] ──────────────────────────────────────┐
[场景录制] ──────────────────────────────────┼──→ [录制回放] ──→ [报告]
[摄像头 × N] ────────────────────────────────┤
[激光雷达 × N] ──────────────────────────────┘
```

**录制回放节点输入端口：**

| 端口 ID | 接受节点 | 连线数 |
|---------|---------|--------|
| `project` | project | 1 |
| `recording` | recording | 1 |
| `sensor` | 任意传感器类型 | 1–N |

地图、天气、Traffic 来自录制文件本身，**不暴露输入端口**，避免用户误连。

---

## 各节点属性面板

属性面板为右侧固定 320px 侧栏，单击节点展示。

### 项目节点

- **选择项目**：下拉，调用 `GET /projects`，显示 `name`，存 `project_id` + `project_name`
- ARCHIVED 状态项目灰色标注，仍可选

### 场景节点

- **选择场景**：下拉，调用 `GET /scenarios/scenario-catalog`，显示中文 `display_name`，存 `scenario_name`

### 地图节点

- **选择地图**：下拉，固定 6 项：Town01_Opt / Town02_Opt / Town03_Opt / Town04_Opt / Town05_Opt / Town10HD_Opt

### 天气节点

- **预设卡片**：3 列网格，展示全部 19 个预设（中文名），点击选中高亮
- **自定义**：最后一个卡片，点击展开 4 个滑块：
  - 降雨量 `precipitation` (0–100)
  - 云量 `cloudiness` (0–100)
  - 雾浓度 `fog_density` (0–100)
  - 路面湿度 `wetness` (0–100)
- 存储：预设存 `weather_preset_id`，自定义存 `weather_custom: {precipitation, cloudiness, fog_density, wetness}`

### 场景录制节点

- **选择录制**：下拉，调用 `GET /scenario-recordings`，显示录制名称和时长
- 节点卡片展示：录制名称 + 时长 + 地图名（只读）

### 摄像头节点

| 字段 | 标签 | 类型 | 默认值 |
|------|------|------|--------|
| `sensor_id` | 传感器 ID | 文本 | FrontRGB |
| `x` / `y` / `z` | 安装位置 (m) | 数字 | 1.5 / 0.0 / 1.7 |
| `roll` / `pitch` / `yaw` | 旋转角度 (°) | 数字 | 0 / 0 / 0 |
| `width` / `height` | 分辨率 (px) | 整数 | 1920 / 1080 |
| `fov` | 视场角 (°) | 数字 | 90.0 |

### 激光雷达节点

| 字段 | 标签 | 类型 | 默认值 |
|------|------|------|--------|
| `sensor_id` | 传感器 ID | 文本 | LIDAR |
| `x` / `y` / `z` | 安装位置 (m) | 数字 | 0.7 / -0.4 / 1.6 |
| `roll` / `pitch` / `yaw` | 旋转角度 (°) | 数字 | 0 / 0 / -45 |
| `channels` | 通道数 | 整数 | 64 |
| `range` | 扫描范围 (m) | 数字 | 85.0 |
| `points_per_second` | 点云密度 (pts/s) | 整数 | 600000 |
| `rotation_frequency` | 旋转频率 (Hz) | 数字 | 10.0 |

### 毫米波雷达节点

| 字段 | 标签 | 类型 | 默认值 |
|------|------|------|--------|
| `sensor_id` | 传感器 ID | 文本 | RADAR |
| `x` / `y` / `z` | 安装位置 (m) | 数字 | 0.7 / -0.4 / 1.6 |
| `roll` / `pitch` / `yaw` | 旋转角度 (°) | 数字 | 0 / 0 / -45 |
| `horizontal_fov` | 水平视场角 (°) | 数字 | 30.0 |
| `vertical_fov` | 垂直视场角 (°) | 数字 | 30.0 |
| `range` | 探测范围 (m) | 数字 | 100.0 |

### GNSS 节点

| 字段 | 标签 | 类型 | 默认值 |
|------|------|------|--------|
| `sensor_id` | 传感器 ID | 文本 | GNSS |
| `x` / `y` / `z` | 安装位置 (m) | 数字 | 0 / 0 / 0 |

### IMU 节点

| 字段 | 标签 | 类型 | 默认值 |
|------|------|------|--------|
| `sensor_id` | 传感器 ID | 文本 | IMU |
| `x` / `y` / `z` | 安装位置 (m) | 数字 | 0 / 0 / 0 |
| `roll` / `pitch` / `yaw` | 旋转角度 (°) | 数字 | 0 / 0 / 0 |

---

## 节点库分组（左侧面板）

```
流程骨架
  项目 / 实时仿真 / 录制回放 / 报告

环境配置（实时仿真用）
  场景 / 地图 / 天气

场景录制（录制回放用）
  场景录制

传感器
  摄像头 / 激光雷达 / 毫米波雷达 / GNSS / IMU
```

---

## 前后端衔接

### 执行时数据组装（前端负责）

调用 `POST /pipelines/{id}/execute` 前，前端遍历画布节点，组装执行请求：

**实时仿真路径：**
```json
{
  "project_id": "...",
  "scenario_name": "town01_urban_loop",
  "map_name": "Town01_Opt",
  "weather": { "preset": "ClearNoon" },
  "sensors": [
    { "id": "FrontRGB", "type": "sensor.camera.rgb", "x": 1.5, "y": 0.0, "z": 1.7, "width": 1920, "height": 1080, "fov": 90.0 },
    { "id": "LIDAR", "type": "sensor.lidar.ray_cast", "x": 0.7, "y": -0.4, "z": 1.6, "channels": 64, "range": 85.0 }
  ]
}
```

**录制回放路径：**
```json
{
  "project_id": "...",
  "recording_id": "...",
  "sensors": [...]
}
```

传感器列表由前端从画布上所有传感器节点组装，**不依赖预先创建的 SensorProfile**。

### 旧节点类型迁移

已保存的 pipeline JSON 中若包含旧节点类型（`scenario_config` / `sensor_profile`），加载时在画布顶部显示警告横幅：

> ⚠️ 此流程包含旧版节点，请删除后重新配置。

不自动迁移，不静默忽略。

---

## 客户端 DAG 校验规则

### 实时仿真节点

| 规则 | 错误码 |
|------|--------|
| 必须连接 project 节点 | `MISSING_PROJECT` |
| 必须连接 scenario 节点 | `MISSING_SCENARIO` |
| 必须连接 map 节点 | `MISSING_MAP` |
| 必须连接 weather 节点 | `MISSING_WEATHER` |
| 至少连接 1 个传感器节点 | `MISSING_SENSOR` |
| 图中不能有环 | `CYCLE` |

### 录制回放节点

| 规则 | 错误码 |
|------|--------|
| 必须连接 project 节点 | `MISSING_PROJECT` |
| 必须连接 recording 节点 | `MISSING_RECORDING` |
| 至少连接 1 个传感器节点 | `MISSING_SENSOR` |
| 图中不能有环 | `CYCLE` |

---

## 受影响文件

### 删除/替换
- `frontend/src/components/pipeline/nodes/ScenarioConfigNode.tsx` → 拆分为 ScenarioNode / MapNode / WeatherNode
- `frontend/src/components/pipeline/nodes/SensorProfileNode.tsx` → 替换为 5 种传感器节点
- `frontend/src/components/pipeline/nodes/RunNode.tsx` → 替换为 LiveRunNode / ReplayRunNode

### 新增
- `frontend/src/components/pipeline/nodes/ScenarioNode.tsx`
- `frontend/src/components/pipeline/nodes/MapNode.tsx`
- `frontend/src/components/pipeline/nodes/WeatherNode.tsx`
- `frontend/src/components/pipeline/nodes/RecordingNode.tsx`
- `frontend/src/components/pipeline/nodes/SensorCameraNode.tsx`
- `frontend/src/components/pipeline/nodes/SensorLidarNode.tsx`
- `frontend/src/components/pipeline/nodes/SensorRadarNode.tsx`
- `frontend/src/components/pipeline/nodes/SensorGnssNode.tsx`
- `frontend/src/components/pipeline/nodes/SensorImuNode.tsx`
- `frontend/src/components/pipeline/nodes/LiveRunNode.tsx`
- `frontend/src/components/pipeline/nodes/ReplayRunNode.tsx`
- `frontend/src/components/pipeline/forms/ProjectForm.tsx`
- `frontend/src/components/pipeline/forms/ScenarioForm.tsx`
- `frontend/src/components/pipeline/forms/MapForm.tsx`
- `frontend/src/components/pipeline/forms/WeatherForm.tsx`
- `frontend/src/components/pipeline/forms/RecordingForm.tsx`
- `frontend/src/components/pipeline/forms/SensorCameraForm.tsx`
- `frontend/src/components/pipeline/forms/SensorLidarForm.tsx`
- `frontend/src/components/pipeline/forms/SensorRadarForm.tsx`
- `frontend/src/components/pipeline/forms/SensorGnssForm.tsx`
- `frontend/src/components/pipeline/forms/SensorImuForm.tsx`

### 修改
- `frontend/src/components/pipeline/PropertyPanel.tsx` — 按节点类型路由到对应 Form
- `frontend/src/components/pipeline/NodeLibrary.tsx` — 新分组和节点类型
- `frontend/src/components/pipeline/PipelineCanvas.tsx` — 注册新节点类型
- `frontend/src/components/pipeline/EditorToolbar.tsx` — 执行前组装传感器列表
- `frontend/src/features/pipeline/validation.ts` — 新校验规则
- `frontend/src/api/pipelines.ts` — 执行请求结构更新
- `app/api/routes_pipelines.py` — 执行引擎适配新节点结构
- `app/core/models.py` — PipelineNodeDef.type 枚举扩展

---

## 不在本次范围内

- 传感器节点保存为新 SensorProfile（后续迭代）
- 多个 Run 节点并行执行（后续迭代）
- 节点模板/预设（后续迭代）
- Traffic 节点（后续迭代）
