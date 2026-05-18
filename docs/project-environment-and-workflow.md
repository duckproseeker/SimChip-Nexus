# 项目开发环境与实施流程

## 1. 项目定位

SimChip Nexus / CARLA 芯片测评平台用于把 CARLA 场景、传感器模板、HIL 设备链路和执行报告串成可复现实验流程。当前平台主线包括：

- 场景目录启动：从平台场景模板创建 native runtime run。
- 公共场景源 materialization：把 ScenarioRunner `.xosc` baseline、Leaderboard / Bench2Drive route XML 在本平台环境中重物化为 recorder run。
- 场景资产库：把 recorder run 发布为 SQLite 管理的可回放资产。
- replay run：从 recorder 资产创建 `carla_recorder_replay` 运行，并绑定 sensor replay profile、fixed-delta 和 HIL replay 环境变量。
- HIL 观测链：Host / Pi / Jetson / gateway / viewer / metrics / events 共同组成芯片测评闭环。

本文件用于项目管理、交付、运维和后续开发人员快速理解当前开发环境、验证流程和交付边界。

## 2. 代码与运行目录

本地工作区：

```text
/Users/kavin/Documents/GitHub/
  SimChip-Nexus/         # 平台产品代码：FastAPI、React、executor、storage、scripts、hil_runtime
```

默认实现任务以 `SimChip-Nexus/` 为工作目录。`hil_runtime/` 作为子目录维护在平台产品目录内。

远端当前实施目标按本轮项目要求使用 SimChip-Nexus 路径：

```text
/home/du/ros2-humble/src/
  SimChip-Nexus/         # 当前远端平台目标目录
  hil_runtime/           # HIL runtime 资产，需按目标机器单独同步

/ros2_ws/src/
  SimChip-Nexus/         # ros2-dev 容器内源码挂载路径
```

注意：部分历史文档仍写的是 `/home/du/ros2-humble/src/carla_web_platform` 和 `/ros2_ws/src/carla_web_platform`。当前实施和远端验证以用户指定的 `SimChip-Nexus` 目标路径为准；如果部署脚本仍假设旧目录，需要在执行前确认脚本参数或同步目标。

## 3. 本地与远端职责划分

本地机器职责：

- 阅读、编辑和审查代码。
- 执行静态检查、单元测试、API contract sync、前端类型检查和前端 build。
- 生成和维护文档、OpenAPI snapshot、前端 API 类型。

远端主机职责：

- Docker / container 生命周期验证。
- CARLA server、Traffic Manager、地图加载和 synchronous/fixed-delta 验证。
- ROS2、HIL gateway、Host display、Pi/Jetson 设备链路验证。
- 部署后的 `/healthz`、`/ui`、运行创建、executor、recorder、replay smoke。

当任务依赖真实运行环境时，远端验证优先于本地推断。本地验证只能证明代码形态或静态行为正确，不能证明 CARLA/HIL 链路可用。

## 4. 已确认远端环境

- SSH 目标：`du@192.168.110.151`
- 远端用户 home：`/home/du`
- 主开发容器：`ros2-dev`
- 容器工作目录：`/ros2_ws`
- 主源码挂载：`/home/du/ros2-humble/src` -> `/ros2_ws/src`
- 当前平台目标目录：`/home/du/ros2-humble/src/SimChip-Nexus`
- 当前容器内平台目录：`/ros2_ws/src/SimChip-Nexus`
- CARLA 镜像：`carlasim/carla:0.9.16`
- CARLA 启动入口：主机 shell 执行 `bash ~/startCarla.sh`

重要约束：

- 不要把明文密码、token、私钥或其他 secrets 写入仓库、提交、文档或日志。
- 容器名是 `ros2-dev`，不是 `ros2_dev`。
- CARLA server 不是默认常驻服务；运行前需要检查是否已经启动。
- CARLA 相关验证要说明验证时 CARLA 是否实际运行。
- `ros2-dev` 内外路径不同，排查 recorder 文件时必须确认 CARLA 容器、executor 容器和主机路径是否共享。

## 5. 标准开发流程

1. 读代码与文档
   - UI 改动先看 `frontend/src/app/`、`frontend/src/pages/`、`frontend/src/components/`、`frontend/src/api/`。
   - API 改动先看 `app/api/main.py`、`app/api/schemas.py`、相关 `app/api/routes_*.py`、匹配的 `frontend/src/api/*.ts` 和测试。
   - runtime 改动先看 `app/core/config.py`、`app/executor/`、`app/orchestrator/`、`scripts/start_platform.sh`。

2. 本地实现
   - 保持既有边界：`frontend/src/pages/*` -> `frontend/src/api/*` -> `app/api/routes_*.py` -> service / manager / store -> executor / gateway / runtime side effects。
   - 前端页面不要直接 raw `fetch`，使用 `frontend/src/api/client.ts` 和领域 API 模块。
   - 后端 routes 不直接写 run、capture、gateway 文件，继续走 service、manager、registry、storage 层。
   - 配置读取走 `app/core/config.py`，不要临时解析环境变量绕过配置层。

3. API contract sync
   - 任何接口 shape 改动必须同步 backend schema、payload builder、frontend wrapper、frontend types 和 route tests。
   - 默认执行：

```bash
cd /Users/kavin/Documents/GitHub/SimChip-Nexus
make contract-sync
```

4. 本地测试与 build

```bash
cd /Users/kavin/Documents/GitHub/SimChip-Nexus
pytest -q
make lint

cd /Users/kavin/Documents/GitHub/SimChip-Nexus/frontend
npm run check-types
npm run build
```

本地 Python 如果系统解释器缺依赖，使用已验证的 conda 环境 `duckpark-carla-web`。

5. 同步远端
   - 平台产品代码同步到远端当前目标目录。
   - `hil_runtime/` 需要按 Host / Pi / Jetson 目标单独同步。
   - 同步凭据保持 out-of-band，不写入文档或脚本。

6. 远端容器内测试

```bash
ssh du@192.168.110.151
docker exec -it ros2-dev bash
cd /ros2_ws/src/SimChip-Nexus
pytest -q
```

7. 远端 host 前端 build

远端 `/usr/bin/node` 可能不是项目所需版本。若系统 Node 过旧，使用已验证的 SimChip Node 路径：

```bash
ssh du@192.168.110.151
cd /home/du/ros2-humble/src/SimChip-Nexus/frontend
PATH=/home/du/.local/share/simchip-node/node-v22.22.2-linux-x64/bin:$PATH npm run check-types
PATH=/home/du/.local/share/simchip-node/node-v22.22.2-linux-x64/bin:$PATH npm run build
```

8. 远端服务与 UI smoke

```bash
ssh du@192.168.110.151
docker exec -it ros2-dev bash
cd /ros2_ws/src/SimChip-Nexus
bash scripts/start_platform.sh \
  --api-host 0.0.0.0 \
  --api-port 8000 \
  --carla-host 192.168.110.151 \
  --carla-port 2000 \
  --traffic-manager-port 8010
```

基础检查：

```bash
curl http://127.0.0.1:8000/healthz
curl http://127.0.0.1:8000/system/status
curl -I http://127.0.0.1:8000/ui
curl http://127.0.0.1:8000/scenario-sources
curl http://127.0.0.1:8000/scenario-recordings
```

9. CARLA smoke
   - 主机上先确认 CARLA 是否已运行。
   - 若未运行，在主机 shell 执行 `bash ~/startCarla.sh`。
   - 在 `ros2-dev` 内确认 CARLA RPC、Traffic Manager、地图加载、synchronous mode 和 fixed delta 可设置。
   - 涉及 materialization 或 replay 时，必须额外确认 recorder 输出目录共享路径和权限。

## 6. 常用命令速查

本地平台目录：

```bash
cd /Users/kavin/Documents/GitHub/SimChip-Nexus
```

契约同步：

```bash
make export-openapi
make contract-sync
```

后端测试：

```bash
pytest -q
python -m pytest -q tests/test_api_scenario_sources.py tests/test_api_scenario_recordings.py
```

前端检查：

```bash
cd frontend
npm run check-types
npm run build
```

启动平台：

```bash
bash scripts/start_platform.sh --api-host 0.0.0.0 --api-port 8000
```

进入远端容器：

```bash
ssh du@192.168.110.151
docker exec -it ros2-dev bash
cd /ros2_ws/src/SimChip-Nexus
```

启动远端 CARLA：

```bash
ssh du@192.168.110.151
bash ~/startCarla.sh
```

## 7. 发布与验证检查表

代码与契约：

- [ ] 相关本地文件已阅读，改动范围限定在当前任务链路。
- [ ] API shape 改动已同步 `app/api/schemas.py`、routes、frontend API wrapper、types、tests。
- [ ] `make contract-sync` 已执行，或明确说明本次无 API shape 改动。
- [ ] 后端测试已执行，若失败已区分新增问题和历史问题。
- [ ] `npm run check-types` 已通过。
- [ ] `npm run build` 已通过。

远端基础：

- [ ] 目标路径确认是 `/home/du/ros2-humble/src/SimChip-Nexus`。
- [ ] 容器名确认是 `ros2-dev`。
- [ ] `/healthz` 返回 200。
- [ ] `/system/status` 返回可读状态。
- [ ] `/ui` 返回 200。
- [ ] 关键新增页面，例如 `/ui/scenario-sources`、`/ui/scenario-recordings` 返回 200。

CARLA / runtime：

- [ ] 验证时说明 CARLA 是否运行。
- [ ] CARLA RPC 端口可连接。
- [ ] Traffic Manager 可连接，并且 synchronous mode 可配置。
- [ ] fixed delta 可设置。
- [ ] 目标地图存在或可加载。
- [ ] recorder 输出目录在主机、executor 容器和 CARLA 容器之间路径一致且可写。
- [ ] materialization run 的 metadata 包含 source lineage、sensor profile、fixed delta、materialization agent。
- [ ] replay run 的 HIL sidecar env 包含 recording id、source log、start/duration、fixed delta、sensor mode。

## 8. 当前风险与待收敛项

- CARLA recorder 状态链路已接通，但 recorder `.log` 文件落盘依赖 CARLA server 容器和 executor 容器之间的共享路径设计。不能只以 run 状态为 `RUNNING` 或 `COMPLETED` 判断 recorder 产物可用。
- 若 CARLA 容器没有挂载 `/home/du/ros2-humble/src` 到 `/ros2_ws/src`，`client.start_recorder()` 使用的容器内路径可能不会落到平台可见目录。
- `ros2-dev` 内运行路径与主机路径不同，调试 recorder 时要同时检查主机、`ros2-dev` 和 `carla-headed` 容器视角。
- 远端 Node 版本可能不一致，前端 build 优先使用已验证的 SimChip Node 路径。
- 旧文档和脚本中可能仍引用 `carla_web_platform` 远端目录；当前实施目标为 `SimChip-Nexus` 时，需要在执行前确认路径。
- 全量 `pytest` 可能受历史缺失脚本或环境依赖影响，交付时要说明执行的是全量还是选定测试集。

