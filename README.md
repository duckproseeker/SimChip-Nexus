# SimChip-Nexus

虚拟传感器数据生成与注入平台 — 将 CARLA 仿真传感器数据注入真实芯片（DUT），用于自动驾驶 HIL（Hardware-in-the-Loop）测试。

## 核心能力

- **场景录制**：基于 CARLA ScenarioRunner 录制 corner case 场景（.log 文件）
- **离线渲染**：同步模式逐帧渲染多传感器数据，保证时间对齐，存盘为帧序列
- **在线注入**：从磁盘按精确帧率读取，通过 RTP/UVC 推送给 DUT 芯片
- **Pipeline 编辑器**：可视化拖拽配置传感器拓扑（相机、LiDAR、Radar 等）
- **场景库管理**：管理录制场景和渲染数据集

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                    Web UI (React)                         │
│  Pipeline 编辑器 │ 场景库 │ 数据集管理 │ 执行监控        │
└──────────────────────────┬──────────────────────────────┘
                           │ REST API
┌──────────────────────────┴──────────────────────────────┐
│                  FastAPI 后端                             │
│  routes_pipelines │ routes_datasets │ routes_scenarios   │
└───────┬───────────────────┬─────────────────┬───────────┘
        │                   │                 │
┌───────┴───────┐  ┌───────┴───────┐  ┌─────┴──────┐
│ 离线渲染引擎   │  │ 在线播放引擎   │  │ 存储层      │
│ offline_      │  │ online_       │  │ SQLite     │
│ renderer.py   │  │ player.py     │  │ datasets   │
└───────┬───────┘  └───────┬───────┘  │ scenarios  │
        │                  │           │ pipelines  │
        │ docker exec      │           └────────────┘
┌───────┴──────────────────┴──────────────────────────────┐
│              ros2-dev 容器 (CARLA Python API)             │
│  CARLA Client → Sensor Spawn → Frame Capture → 存盘     │
└───────────────────────────┬─────────────────────────────┘
                            │ RPC (port 2000)
┌───────────────────────────┴─────────────────────────────┐
│           CARLA Server (carla-offscreen 容器)             │
│  Unreal Engine 渲染 │ 物理仿真 │ Replay 引擎            │
└─────────────────────────────────────────────────────────┘
```

## 快速开始

### 环境要求

- Docker + NVIDIA Container Toolkit
- Python 3.10+
- Node.js 18+
- CARLA 0.9.16 Docker 镜像 (`carlasim/carla:0.9.16`)

### 启动服务

```bash
# 1. 启动 CARLA（无头模式，High 画质）
docker run -d --rm --name carla-offscreen \
  --runtime=nvidia --net=host \
  --env NVIDIA_VISIBLE_DEVICES=all \
  carlasim/carla:0.9.16 \
  ./CarlaUE4.sh -RenderOffScreen -quality-level=High -nosound

# 2. 启动平台
cd scripts && bash start_platform.sh
# 或手动：
uvicorn app.api.main:app --host 0.0.0.0 --port 8000

# 3. 访问 Web UI
# http://<host-ip>:8000/ui/
```

## 工作流

### 场景录制

```bash
# 终端 A：启动 ScenarioRunner（等待 ego 连接）
bash scripts/record_scenario.sh PedestrianCrossingFront.xosc

# 终端 B：键盘控制 ego 车辆
docker exec -e DISPLAY=:1 ros2-dev python3 \
  /ros2_ws/carla_workspace/scenario_runner/manual_control.py \
  --host localhost --port 2000 --rolename hero
```

用 WASD 驾驶 ego 到触发点，场景事件自动触发，录制自动完成。

### 离线渲染

通过 API 或 Web UI 触发：

```bash
curl -X POST http://localhost:8000/datasets/generate \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_id": "<scenario_id>",
    "sensor_configs": [
      {
        "sensor_id": "camera_front",
        "sensor_type": "sensor.camera.rgb",
        "transform": {"x": 1.5, "y": 0, "z": 1.7, "pitch": -5},
        "attributes": {"image_size_x": 1920, "image_size_y": 1080, "fov": 90}
      }
    ]
  }'
```

### 在线播放

```bash
# 全屏播放渲染好的数据集
docker exec -e DISPLAY=:1 ros2-dev python3 \
  /tmp/replay_scenario.py --dataset-id <dataset_id>
```

或通过 Pipeline 编辑器点击"在线播放"。

## 目录结构

```
SimChip-Nexus/
├── app/                        # Python 后端
│   ├── api/                    # FastAPI 路由
│   │   ├── main.py             # 应用入口
│   │   ├── routes_pipelines.py # Pipeline CRUD + 执行
│   │   ├── routes_datasets.py  # 数据集 API
│   │   └── routes_scenarios.py # 场景库 API
│   ├── executor/               # 执行引擎
│   │   ├── offline_renderer.py # 离线渲染（CARLA 同步模式）
│   │   ├── online_player.py    # 在线播放（磁盘读取）
│   │   ├── native_runtime_controller.py  # 原有 HIL 控制器
│   │   ├── carla_client.py     # CARLA 连接封装
│   │   └── sensor_recorder.py  # 传感器录制
│   ├── storage/                # 数据持久化
│   │   ├── dataset_store.py    # 数据集 SQLite
│   │   ├── pipeline_store.py   # Pipeline SQLite
│   │   └── scenario_asset_store.py  # 场景 SQLite
│   └── core/                   # 模型定义
│       ├── models.py           # Pydantic 模型
│       └── config.py           # 配置
├── frontend/                   # React 前端
│   └── src/
│       ├── pages/              # 页面组件
│       ├── components/         # UI 组件
│       ├── api/                # API 客户端
│       └── store/              # Zustand 状态管理
├── hil_runtime/                # HIL 硬件集成
│   ├── host/scripts/           # 主机端脚本
│   └── pi/scripts/             # Pi 网关脚本
├── configs/                    # 配置文件
│   └── sensors/                # 传感器配置 YAML
├── scripts/                    # 运维脚本
│   ├── record_scenario.sh      # 场景录制
│   ├── replay_scenario.py      # 场景回放
│   └── start_platform.sh       # 平台启动
└── tests/                      # 测试
```

## 关键概念

### 场景 (Scenario)

一个 CARLA recorder `.log` 文件，记录了所有 actor 的运动轨迹、事件和交通流。不包含传感器数据。可以用不同传感器配置反复渲染。

### 数据集 (Dataset)

场景 + 传感器配置的渲染产物。包含逐帧的传感器数据（图片、点云、雷达检测）和时间戳文件。多传感器通过同步模式保证帧对齐。

### Pipeline

可视化的传感器拓扑配置。定义了：
- 场景源（哪个 .log）
- 传感器节点（类型、位置、参数）
- 输出节点（RTP/存盘/DUT）

### 执行模式

| 模式 | 用途 | 帧率 |
|------|------|------|
| 离线生成 | 渲染传感器数据存盘 | 不限（GPU 速度） |
| 在线播放 | 从磁盘读取全屏显示 | 精确 30/60 fps |
| 在线注入 | 推送给 DUT 芯片 | 精确目标帧率 |

## API 文档

启动服务后访问：`http://localhost:8000/docs`（Swagger UI）

## 技术栈

- **后端**：Python 3.10, FastAPI, SQLite, Pydantic
- **前端**：React 18, TypeScript, Zustand, React Flow
- **仿真**：CARLA 0.9.16, Unreal Engine 4
- **容器**：Docker, NVIDIA Container Toolkit
- **硬件接口**：GStreamer RTP, USB Video Class (UVC)
