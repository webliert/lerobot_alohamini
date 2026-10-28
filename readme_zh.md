# lerobot_alohamini（中文说明）

> **AlohaMini 产品线的共享软件层**，构建在 HuggingFace LeRobot 之上。
> 同时支持完整 AlohaMini 机器人（双臂 + 全向移动底盘 + 升降轴）与单臂产品 AM-ARM200。

英文版见 [README.md](./README.md)｜面向 AI agent 的开发约定见 [AGENTS.md](./AGENTS.md)（`CLAUDE.md` 是它的软链）｜面向普通用户的操作手册见 [AGENT_GUIDE.md](./AGENT_GUIDE.md)

---

## 目录

- [1. 项目定位](#1-项目定位)
- [2. 仓库规模与组成](#2-仓库规模与组成)
- [3. 系统架构](#3-系统架构)
- [4. 安装](#4-安装)
- [5. 快速开始](#5-快速开始)
- [6. 硬件型号矩阵](#6-硬件型号矩阵)
- [7. 安全保护体系](#7-安全保护体系)
- [8. 升降轴（Z 轴）](#8-升降轴z-轴)
- [9. ROS 兼容与 50 Hz 实时控制](#9-ros-兼容与-50-hz-实时控制)
- [10. 多速率录制](#10-多速率录制)
- [11. AM-ACT 策略](#11-am-act-策略)
- [12. 数据集完整性检查与修复](#12-数据集完整性检查与修复)
- [13. 仿真栈 alohamini_sim](#13-仿真栈-alohamini_sim)
- [14. 调试工具](#14-调试工具)
- [15. 测试](#15-测试)
- [16. 文档索引](#16-文档索引)
- [17. 已知问题与风险清单](#17-已知问题与风险清单)
- [18. 开发工作流](#18-开发工作流)
- [19. 团队与致谢](#19-团队与致谢)

---

## 1. 项目定位

这是 **HuggingFace LeRobot 的下游产品仓库**（`github.com/liyiteng/lerobot_alohamini`）。

LeRobot 本身是一个研究导向的算法库：数据集、策略、训练、评测。它缺少的是从「算法跑通」到「机器人可交付」的那一段——实时性、安全保护、双机通信、数据完整性、硬件适配。

**这个 fork 补上的正是这一段。** 核心价值可以概括为三个层次：

| 层次 | 内容 | 成熟度 |
|---|---|---|
| **机器人运行层** | Host/Client 双机架构、电流分级保护、控制权独占、多速率录制 | ✅ 成熟，有 2244 行针对性测试，可上真机 |
| **策略扩展层** | AM-ACT 混合离散动作头 | ⚠️ 设计精巧但工程未收尾（零测试、无文档） |
| **仿真数据层** | `alohamini_sim/` 手机视频 → Isaac 场景 → LeRobot 数据集 | ⚠️ 高质量 **vendored 参考实现**，当前 checkout 不可运行 |

---

## 2. 仓库规模与组成

| 项 | 数值 |
|---|---|
| 上游基座 | LeRobot **v0.6.1**（`e40b58a8` 合入） |
| Python 要求 | ≥ 3.12 |
| 相对上游净改动 | **68 文件，+13833 / −30 行**（`src/` `examples/` `scripts/` `docs/` `tests/`） |
| `alohamini_sim/` | 另 4 个提交引入，**135 文件，约 10900 行 Python** |
| 注册策略 | 19 个 |
| 注册机器人 | 17 个 |
| 遥操作端 | 16 个 |
| 电机总线 | 4 个（Feetech / Dynamixel / Damiao / RobStride） |
| 仿真基准 | 7 个（LIBERO / MetaWorld / RoboCasa / RoboCerebra / RoboMME / RoboTwin / VLABench） |
| CLI 入口 | 18 个 |

### 目录速查

```
.
├── src/lerobot/
│   ├── robots/alohamini/          # ★ AlohaMini 机器人栈（Host / Client / 升降轴 / 相机流 / 控制权）
│   ├── policies/am_act/           # ★ AM-ACT 策略（ACT + 混合离散动作头）
│   ├── robots/so_follower/        #   扩展：arm_profile + 过流保护
│   ├── teleoperators/so_leader/   #   扩展：arm_profile + 归一化绕行
│   ├── motors/feetech/            #   扩展：注册 STS3095
│   ├── scripts/
│   │   ├── create_alohamini_visual_only_dataset.py  # ★ 视觉-only 数据集视图
│   │   ├── lerobot_record.py      #   扩展：多 leader 臂 + 升降轴动作
│   │   └── lerobot_rollout.py     #   扩展：注册 alohamini 类型
│   └── policies/                  #   其余 18 个上游策略
├── examples/alohamini/            # ★ PC 侧工作流：遥操作 / 录制 / 回放 / 评估 / 标定
├── examples/debug/                # ★ Feetech 低层硬件调试工具
├── scripts/                       # ★ 数据集完整性检查与两阶段修复（顶层，非包内）
├── alohamini_sim/                 # ★ 仿真栈（video2sim + data_engine）
├── docs/alohamini/                # ★ AlohaMini 用户文档
├── docs/source/                   #   上游 HF 文档
└── tests/                         #   上游测试 + ★ AlohaMini 专属测试
```

> `scripts/` 与 `alohamini_sim/` 位于 `src/` 之外，**不会被打包**（`pyproject.toml` 的 `packages.find where = ["src"]`），只能从仓库根目录使用。

---

## 3. 系统架构

### 3.1 AlohaMini 双机架构

```
┌──────────────────────────────┐        LAN        ┌──────────────────────────────────┐
│         PC (Client)          │ ◄───────────────► │      树莓派 / 机器人主机 (Host)   │
│                              │   ZMQ TCP         │                                  │
│  • Leader 臂 (USB)           │   5555 命令       │  • Follower 臂 (USB)             │
│  • 键盘遥操作                 │   5556 观测       │  • 底盘 3 全向轮 + 升降轴 (USB)   │
│  • 策略推理 / 训练 / 评估      │   5557 相机流(选配) │  • 相机 (USB)                    │
│  • 数据集录制                 │                   │  • alohamini_host.py             │
└──────────────────────────────┘                   └──────────────────────────────────┘
```

- **Host** — [src/lerobot/robots/alohamini/alohamini_host.py](src/lerobot/robots/alohamini/alohamini_host.py)：ZMQ `PULL` 收命令、`ROUTER` 应答观测、可选 `PUB` 相机流；50 Hz 控制循环；看门狗；控制权管理；安全巡检。
- **Client** — [src/lerobot/robots/alohamini/alohamini_client.py](src/lerobot/robots/alohamini/alohamini_client.py)：实现 LeRobot 的 `Robot` 接口，因此可直接喂给 `lerobot-record` / `lerobot-eval` / `lerobot-rollout` / `lerobot-rollout` 的推理引擎。

### 3.2 观测协议

请求带 **请求 token**（`"<id>:camera"` / `"<id>:state"`），客户端只接受 token 匹配的响应——这是整套「防陈旧反馈」机制的基石。

响应为 **multipart 二进制帧**：第 0 段是 JSON（状态 + `_image_encoding` + `_images` + `_robot_metadata` + `_safety`），其后每两段是 `(相机名, JPEG 字节)`。

早期协议用 base64 JSON 携带图像，客户端仍保留兼容解析分支。

### 3.3 继承自 LeRobot 的能力

| 模块 | 内容 |
|---|---|
| `policies/` | `act`、`am_act`、`diffusion`、`smolvla`、`pi0`/`pi05`/`pi0_fast`、`wall_x`、`xvla`、`groot`、`evo1`、`eo1`、`fastwam`、`lingbot_va`、`molmoact2`、`multi_task_dit`、`vla_jepa`、`vqbet`、`tdmpc`、`gaussian_actor` |
| `robots/` | `alohamini`、`alohamini_client`、`so101_follower`、`koch_follower`、`lekiwi`、`openarm_follower`、`rebot_b601_follower`、`unitree_g1` 等 |
| `teleoperators/` | `so101_leader`、`bi_so_leader`（双臂）、`phone`、`gamepad`、`keyboard`、`openarm_leader` 等 |
| `rollout/` | 推理引擎层：`sync` / `rtc`（Real-Time Chunking）、策略 `dagger`/`episodic`/`sentry`/`highlight` |
| `datasets/` | LeRobotDataset v3.0 + processor 流水线 |

---

## 4. 安装

### 4.1 通用（uv，推荐）

```bash
git clone https://github.com/liyiteng/lerobot_alohamini.git
cd lerobot_alohamini

uv sync --locked                            # 基础依赖
uv sync --locked --extra test --extra dev   # 测试 + 开发工具
uv sync --locked --extra all                # 全部
```

### 4.2 conda（树莓派 / x86 PC）

```bash
# x86-64
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh
bash miniconda.sh -b -u -p ~/miniconda3 && ~/miniconda3/bin/conda init bash

# ARM64（树莓派）
wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-aarch64.sh -O miniforge.sh
bash miniforge.sh -b -u -p ~/miniforge3 && ~/miniforge3/bin/conda init bash

conda create -y -n lerobot_alohamini python=3.12
conda activate lerobot_alohamini
pip install -e ".[all]"
pip install pyzmq feetech-servo-sdk
conda install -y ffmpeg=7.1.1 -c conda-forge
```

### 4.3 串口权限与 HF 登录

```bash
sudo usermod -a -G dialout $USER   # 之后需重启

git config --global credential.helper store
hf auth login --token <your_token> --add-to-git-credential
HF_USER=$(hf auth whoami | sed 's/^user=//')
```

### 4.4 固定设备名（udev）

树莓派上的 follower 臂、PC 上的 leader 臂建议固定别名，否则重插 USB 后端口号会变：

```udev
# /etc/udev/rules.d/90-mydevice.rules
SUBSYSTEM=="tty", ATTRS{serial}=="<follower_left_serial>",  SYMLINK+="am_arm_follower_left"
SUBSYSTEM=="tty", ATTRS{serial}=="<follower_right_serial>", SYMLINK+="am_arm_follower_right"
SUBSYSTEM=="tty", ATTRS{serial}=="<leader_left_serial>",    SYMLINK+="am_arm_leader_left"
SUBSYSTEM=="tty", ATTRS{serial}=="<leader_right_serial>",   SYMLINK+="am_arm_leader_right"
```

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger && ls /dev/am*
```

---

## 5. 快速开始

> 📖 **刚拿到新设备？** 请按 **[docs/alohamini/getting_started.md](docs/alohamini/getting_started.md)** 的 12 阶段清单逐项执行——它包含硬件接线拓扑、每一步的「通过标准」、故障排查表和一份可勾选的完整检查清单。本节只给出最简路径。

### 5.1 找端口与相机

```bash
lerobot-find-port
ls /dev/ttyACM* /dev/serial/by-id/
lerobot-find-cameras
v4l2-ctl --d /dev/video0 --list-formats-ext
```

> 每台相机独占一个 USB 口，不要共用 USB Hub。

### 5.2 标定

**Follower 臂（树莓派）** — 关节摆到机械中位 → 回车 → 左转 90° → 回车 → 右转 90° → 回车：

```bash
python -m lerobot.robots.alohamini.alohamini_calibrate --robot_model alohamini2
```

**Leader 臂（PC）** — 可独立执行，不需要树莓派在线：

```bash
python examples/alohamini/calibrate_bi.py \
  --teleop.id am_leader_bi --teleop.arm_profile am-leader-6dof
```

> 标定后**给双臂断电重启**才会生效。

### 5.3 遥操作

```bash
# 树莓派
python -m lerobot.robots.alohamini.alohamini_host --robot_model alohamini2

# PC
python examples/alohamini/teleoperate_bi.py \
  --robot.remote_ip <Pi_IP> \
  --robot.robot_model alohamini2 \
  --teleop.id am_leader_bi \
  --teleop.arm_profile am-leader-6dof \
  --fps 50 --camera-fps 30
```

只驱动底盘和升降（不接随动臂）：Host 加 `--no_follower`，Client 加 `--no_leader`。

### 5.4 录制

```bash
python examples/alohamini/record_bi.py \
  --dataset.repo_id $HF_USER/am2_bi_test \
  --dataset.num_episodes 50 \
  --dataset.fps 30 \
  --dataset.episode_time_s 45 \
  --dataset.reset_time_s 8 \
  --dataset.single_task "pickup1" \
  --robot.remote_ip <Pi_IP> \
  --robot.robot_model alohamini2 \
  --teleop.id am_leader_bi \
  --teleop.arm_profile am-leader-6dof
```

- `--resume` 续录已有数据集
- `--dataset.push_to_hub=false` 只存本地
- `--dataset.root /path/to/dataset` 指定本地工作目录

### 5.5 训练

```bash
lerobot-train \
  --dataset.repo_id=$HF_USER/am2_bi_test \
  --policy.type=act \
  --output_dir=outputs/train/act_am2_bi_test \
  --job_name=act_am2_bi_test \
  --policy.device=cuda \
  --policy.repo_id=$HF_USER/act_am2_bi_test \
  --dataset.video_backend=pyav
```

### 5.6 评估

```bash
python examples/alohamini/evaluate_bi.py \
  --eval.n_episodes 10 \
  --fps 20 \
  --eval.episode_time_s 45 \
  --dataset.single_task "Pick and place task" \
  --policy.path outputs/train/act_am2_bi_test/checkpoints/020000/pretrained_model \
  --dataset.repo_id $HF_USER/eval_act_am2_bi_test \
  --robot.remote_ip <Pi_IP> \
  --robot.robot_model alohamini2 \
  --inference.type sync \
  --interpolation_multiplier 3
```

`--inference.type rtc` 启用 Real-Time Chunking（仅 SmolVLA 等支持 RTC 的策略可用；ACT 必须用 `sync`）。

### 5.7 回放与可视化

```bash
python examples/alohamini/replay_bi.py \
  --dataset.repo_id $HF_USER/am2_bi_test --dataset.episode 0 \
  --robot.remote_ip <Pi_IP> --robot.robot_model alohamini2

lerobot-dataset-viz --repo-id $HF_USER/am2_bi_test --episode-index 0 --display-compressed-images
```

---

## 6. 硬件型号矩阵

设计上刻意分两层：

- **`arm_profile`** 描述「手臂本身」——自由度、电机型号、归一化模式
- **`robot_model`** 描述「整机 SKU」——臂 profile + 底盘电机 + 升降电机 + 丝杠导程 + 运动学参数

这种分层让同一套代码同时支持 AlohaMini 整机与 AM-ARM200 单臂。

### AlohaMini 整机（Host 侧 `--robot_model`）

| `--robot_model` | 随动臂 profile | 底盘电机 | 升降电机 | 丝杠导程 | 轮半径 | 底盘半径 | 状态维度 |
|---|---|---|---|---|---|---|---|
| `alohamini1` | `so-arm-5dof`（6 DoF） | STS3215 ×3 | STS3215 | 84 mm/rev | 0.05 m | 0.125 m | 16 |
| `alohamini2` | `am-follower-6dof`（7 DoF） | STS3215 ×3 | STS3095 | 131 mm/rev | 0.063 m | 0.195 m | 18 |
| `alohamini2pro` | `am-follower-6dof-hd` | STS3250 ×3 | STS3095 | 131 mm/rev | 0.063 m | 0.195 m | 18 |

### AM-ARM200 单臂（PC 侧 `--teleop.arm_profile` / `--robot.arm_profile`）

| 产品 SKU | 角色 | profile |
|---|---|---|
| AM-ARM200 | Leader（5 V） | `am-leader-6dof` |
| AM-ARM200 | Follower（12 V） | `am-follower-6dof` |
| AM-ARM200 Pro | Leader（5 V） | `am-leader-6dof` |
| AM-ARM200 Pro | Follower（12 V HD） | `am-follower-6dof-hd` |

### 关节定义

| profile | 关节 |
|---|---|
| `so-arm-5dof` | shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper |
| `am-leader-6dof` / `am-follower-6dof` / `am-follower-6dof-hd` | shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, **wrist_yaw**, wrist_roll, gripper |

定义见 [src/lerobot/robots/alohamini/model_specs.py](src/lerobot/robots/alohamini/model_specs.py)。

---

## 7. 安全保护体系

这是本 fork 最重的一块代码。核心原则：**分级响应**——告警不夺权，持续过载才停止。

### 7.1 电流分级阈值

按电机型号查额定/堵转电流表，派生三级阈值：

| 电机 | 额定 | 堵转 | 关节卡滞告警 | 持续停止 | 近堵转停止 |
|---|---:|---:|---:|---:|---:|
| STS3215 | 0.9 A | 2.7 A | 1.35 A | 1.8 A | 2.16 A |
| STS3095 | 2.2 A | 9.8 A | 3.3 A | 4.4 A | 7.84 A |
| STS3250 | 1.4 A | 4.2 A | 2.1 A | 2.8 A | 3.36 A |

派生规则：碰撞阈值 = 1.5 × 额定，持续阈值 = 2.0 × 额定，近堵转阈值 = 0.8 × 堵转。

### 7.2 各机制一览

| 机制 | 位置 | 行为 |
|---|---|---|
| **关节卡滞检测** | `alohamini.py` `_has_sustained_overcurrent` | 需同时满足：电流达阈值 **且** 指令误差 ≥ 2° **且** 150 ms 内进展 < 0.2°。**只告警不夺权**，每电机 5 s 一次。位置差按标定换算成**物理角度**（归一化坐标下也正确） |
| **持续过载停止** | `send_action` | 650 ms 持续超限 → 停机 |
| **近堵转快速停止** | `send_action` | 80 ms → 停机 |
| **夹爪力控** | `_limit_gripper_goal_by_current` | 独立 0.5 A 阈值。接触后保持位置并留一点残余夹紧力；反向需越过 1.0 的释放裕量 |
| **命令看门狗** | `alohamini_host.py` | 1 s 无有效命令 → 保持当前位置 + 停车 + 释放控制权。**只有伺服写入成功后才续租**；非法/重复/过期 epoch/他人命令都不能续租 |
| **控制权独占** | [command_owner.py](src/lerobot/robots/alohamini/command_owner.py) | 首个命令客户端获得控制权，他人被拒。命令携带 `client_id` + `sequence` + `host_session_id` + `control_epoch`，防重放与跨 Host 会话串扰 |
| **每周期安全巡检** | `supervise_arm_motion` | 即使没有新命令，每个控制周期仍用最新反馈复查活跃目标，**只写安全修正量** |
| **观测背压** | `alohamini_client.py` | ZMQ 发送队列满 → 延后到下一周期，不阻塞控制、不记录未发出的请求 |
| **反馈新鲜度绑定** | `control_feedback_valid` | 计时从「上次**有效请求**」起算；缓存读取和迟到回复**都不能续命** |
| **命令与反馈绑定** | `send_action` | `send_action` 消费并清空本周期反馈快照；**一个反馈快照只服务一个 observe→act 周期** |
| **阻塞推理后刷新** | `refresh_observation` | 策略推理阻塞结束后重新取反馈，丢弃全部预取响应 |
| **评估期保护** | `examples/alohamini/evaluation_safety.py` | 关节保护触发时暂停推理、丢弃预测、重新开始，无需人工回车 |

### 7.3 观测 / 动作的时序契约

```
Host 控制周期（50 Hz）
  1. 轮询观测请求（token 决定是否要相机）
  2. get_observation()  ──► 一次反馈快照（位置 + 电流 + 高度）
  3. 收命令 + 校验身份/有限性
  4. send_action()      ──► 消费并清空该快照；做限幅与电流保护
  5. 编码观测响应（JPEG 多线程）
  6. 发送
```

客户端侧的 `command_permitted` / `control_feedback_valid` / `observation_updated` 三个属性共同决定「此刻能否下发指令」。

---

## 8. 升降轴（Z 轴）

[src/lerobot/robots/alohamini/lift_axis.py](src/lerobot/robots/alohamini/lift_axis.py) 是融合进 Feetech 总线的独立控制器。

- **多圈累计**：4096 tick/圈，跨圈解卷绕 → 毫米级高度
- **速度模式闭环**：`v = kp_vel × 误差`，`v_max` 限幅
- **下降地面保护**（`descent_floor_mm`）：低于阈值拒绝下行，防止电机顶死
- **回零**：向下驱动至堵转（电流或无位移）→ 松扭矩 → 记录零点
- **软限位**：`soft_min_mm` / `soft_max_mm`
- **客户端键盘控制**用**绝对高度目标 + 限前导**（`lift_target_max_lead_mm = 50`），保证松键和反向都跟手

观测键：`lift_axis.height_mm`；动作键：`lift_axis.height_mm`（推荐）或 `lift_axis.vel`。

---

## 9. ROS 兼容与 50 Hz 实时控制

- **相机 FPS 与控制 FPS 解耦**：控制 50 Hz，相机请求 30 Hz。相机驱动跑自己的异步采集线程，Host 只「偷看」带时效上限的缓存（`read_latest(max_age_ms=500)`）
- **ROS state-only 请求**：token 以 `:state` 结尾时不触发相机采集，纯状态观察者不占控制关键路径
- **独立相机流**（TCP 5557 `PUB`）：非阻塞推送，携带 RGB 顺序和采集时间戳
- **机器人元数据**：`build_robot_metadata` 输出 schema 版本、电机 ID/型号/归一化模式/标定范围、相机列表、升降软限位——供 ROS 侧校验硬件型号一致性
- **原生运动 profile**：随动伺服使用共享的 position-mode 速度/加速度限制（`arm_goal_velocity=2000`、`arm_acceleration=100`，寄存器单位），既保留直接目标语义，又限制远距离/不连续目标的物理运动

启动：

```bash
python -m lerobot.robots.alohamini.alohamini_host \
  --robot_model alohamini2pro --camera-stream
```

`--profile_timing` 会每秒打印 Host / 电机 / 相机 / JPEG / 网络的分段耗时，便于定位瓶颈。

---

## 10. 多速率录制

| 入口 | 行为 |
|---|---|
| `examples/alohamini/record_bi.py` | **单速率**：控制与数据集采样都用 `--dataset.fps`（向后兼容） |
| `examples/alohamini/record_bi_multirate.py` | **多速率**：50 Hz 控制 + 数据集频率提交新鲜帧 |

多速率录制的两个关键组件（[record_utils_multirate.py](examples/alohamini/record_utils_multirate.py)）：

- **`ControlSampleBuffer`** — 环形缓冲，保留带 Host 时间戳的控制历史，用于把**延迟到达的相机帧**对齐到正确的 state/action 采样
- **`FreshCameraGate`** — 强制要求：
  - 所有相机的时间戳都推进了（否则 `camera_stall_timeout_s = 1.0 s` 超时直接报错）
  - **相机间偏斜 ≤ 50 ms**
  - **状态对齐误差 ≤ 100 ms**
  - **实际帧率 ≥ 目标帧率 90%**

任一条件不满足就**抛错终止**，而不是静默写入重复帧。

> `record_bi_multirate.py` 只是 15 行的 shim：monkey-patch `record_bi.record_loop` 后调用 `record_bi.main()`，所以 CLI 完全相同。`control_fps` 固定 50，**没有 CLI 旋钮**；若 `--dataset.fps > 50` 会抛 `control_fps must be at least dataset fps`。

LeRobot 把时间戳定义为 `frame_index / dataset.fps`，所以多速率录制会**记录到请求的帧数**并允许一点墙钟超时，而不是在相机实际只有 29.5 Hz 时悄悄缩短数据集时间轴。

---

## 11. AM-ACT 策略

[src/lerobot/policies/am_act/](src/lerobot/policies/am_act/) — 在上游 `act` 之上加**混合离散/连续动作头**。

### 11.1 核心机制

大部分动作维度仍走**连续 L1 回归**；选定维度改走**分类头**。

1. **物理值 → 归一化类中心**
   `_initialize_discrete_action_values` 读 `dataset_stats["action"]["mean"/"std"]`，按 `(values - mean[d]) / std[d]` 换算并存入 `config.discrete_action_normalized_values`（随 checkpoint 保存）。有 `dataset_stats` 时**总是重算**（微调安全），否则回退到 checkpoint 中的值。`std[d] ≈ 0` 直接报错。

2. **标签分配**：训练时目标维度取 `argmin(|target − centers|)` 的索引。

3. **损失**
   - `L1` 只在「非 fixed 且非 discrete」的维度上计算，并**按维归一化**（`sum / (valid.sum() × n_active_dims)`）
   - 逐维 CE，带可选类别权重，逐维记日志 `classification_loss_dim_{d}`
   - `total = l1 + discrete_action_loss_weight × mean_CE`，VAE 路径再加 `mean_kld × kl_weight`

4. **推理解码**
   `actions[..., dim] = centers[logits.argmax(dim=-1)]`。因为 argmax 不可微，**离散维度完全没有梯度回流**，只由分类损失驱动。代入的是归一化中心，标准 `UnnormalizerProcessorStep` 会还原成精确物理值——**机器人 API 与 unnormalizer 都不用改**。

5. **不启用时与上游 ACT 逐字节等价**：`discrete_action_dims=[]` → `discrete_action_heads` 为空 `ModuleList` → `discrete_logits` 为空列表（falsy）→ 走原路径。

### 11.2 配置项

| 参数 | 默认 | 含义 |
|---|---|---|
| `fixed_action_dims` | `[]` | 排除训练、归一化空间强制置零的维度 |
| `discrete_action_dims` | `[]` | 改用分类训练的维度索引 |
| `discrete_action_values` | `[]` | 各离散维度的**物理**类值（顺序即类顺序） |
| `discrete_action_normalized_values` | `[]` | 由数据集统计量自动填充，存于 checkpoint |
| `discrete_action_class_weights` | `[]` | 可选的逐类 CE 权重 |
| `discrete_action_loss_weight` | `1.0` | 分类损失均值乘数 |
| `action_loss_groups` | `{}` | 连续维度的命名分组，各自独立归一化 L1 |
| `action_loss_weights` | `{}` | 各组权重 |
| `observation_state_dims` | `[]` | 送入模型的 `observation.state` 子集 |
| `inference_action_scale_dims` | `[]` | 反归一化后缩放的物理维度 |
| `inference_action_scale` | `1.0` | 缩放系数 |
| `allow_partial_pretrained_load` | `False` | ⚠️ **死旋钮，全仓库无读取点** |
| `use_dataset_input_features` | `False` | ⚠️ **死旋钮，全仓库无读取点** |

标准 ACT 参数全部保留：`chunk_size=100`、`dim_model=512`、`use_vae=True`、`latent_dim=32`、`kl_weight=10.0`、`optimizer_lr=1e-5` 等。

### 11.3 使用

```bash
python -m lerobot.scripts.lerobot_train \
  --dataset.repo_id=local/my_dataset --dataset.root=/path/to/my_dataset \
  --policy.type=am_act --policy.device=cuda \
  --policy.discrete_action_dims='[14,15,16]' \
  --policy.discrete_action_values='[[-0.15,0,0.15],[-0.15,0,0.15],[-45,0,45]]' \
  --policy.discrete_action_class_weights='[[3,1,1.5],[3,1,2],[2,1,2]]' \
  --policy.discrete_action_loss_weight=1.0 \
  --output_dir=outputs/am_act_run --steps=100000 --batch_size=2
```

### 11.4 ⚠️ 现状提醒

- **零测试**：`tests/` 下没有任何 `am_act` 相关测试
- **`docs/` 无文档**：[docs/alohamini/](docs/alohamini/) 里仍写 `--policy.type=act`
- 动机很务实：底盘 `theta.vel` 这类「离散步进」性质的量，用 L1 回归训出来抖动大，改成分类后行为离散可预测

### 11.5 配套：视觉-only 数据集

[src/lerobot/scripts/create_alohamini_visual_only_dataset.py](src/lerobot/scripts/create_alohamini_visual_only_dataset.py)（414 行）生成 v3 数据集的**过滤视图**（不动源数据）：

```bash
python -m lerobot.scripts.create_alohamini_visual_only_dataset \
  --source /path/to/dataset --target /path/to/visual_only \
  --keep-camera wrist_right --drop-state --mode auto
```

- `--keep-camera` / `--drop-camera`（可裸后缀匹配：`wrist_right` → `observation.images.wrist_right`）
- `--drop-feature` 拒绝 `action` / `timestamp` / `frame_index` / `episode_index` / `index` / `task_index` 等保护特征
- `--mode {auto,hardlink,copy}`，`auto` 优先硬链接媒体与 parquet，跨设备/无权限时回退复制
- `--dry-run` 只打印计划
- 任一异常会 `rmtree` 掉半成品目标

配合 AM-ACT 的 `observation_state_dims` 使用。

---

## 12. 数据集完整性检查与修复

两个顶层脚本（**不在 `src/` 内**，装成包后不可导入）。

### 12.1 `scripts/check_lerobot_dataset_integrity.py`（1017 行）

离线诊断 LeRobot v3 数据集。**永不连 Hub，永不修改源数据**。把逐帧 `data/*.parquet` 当作权威样本记录，校验 `meta/info.json`、`meta/episodes/**` 和视频文件是否描述同一批 episode/帧。

```bash
python scripts/check_lerobot_dataset_integrity.py \
  --dataset.root /path/to/dataset \
  --decode-videos \
  --output-json report.json
```

| 参数 | 说明 |
|---|---|
| `--dataset.root` | 必填，本地数据集根目录 |
| `--decode-videos` | 逐帧解码所有被引用的视频，而不是相信容器头 |
| `--timestamp-tolerance-s` | `timestamp == frame_index / fps` 的容差，默认 `1e-4` |
| `--output-json` | 机器可读报告 |
| `--repair-output` | 输出修复后的新数据集（见下） |
| `--fail-on-warnings` | 有告警也返回 1 |

退出码：无错误 0；数据无效 1。`--repair-output` 且修复结果通过校验时返回 0。

错误码分类（~50 个）举例：

- 结构类：`DATA_EPISODE_IDS_NONCONTIGUOUS`、`EPISODE_DATASET_RANGE_MISMATCH`、`GLOBAL_INDEX_NONCONTIGUOUS`、`METADATA_LENGTH_SUM_MISMATCH`、`TOTAL_EPISODES_MISMATCH`、`TOTAL_FRAMES_MISMATCH`
- 视频类：`VIDEO_FRAME_GAP`、`VIDEO_LEADING_GAP`、`VIDEO_EPISODE_LENGTH_MISMATCH`、`VIDEO_DECODE_COUNT_MISMATCH`、`VIDEO_SHAPE_MISMATCH`、`VIDEO_FPS_MISMATCH`、`VIDEO_RANGE_OVERLAP`
- 数值类：`FEATURE_NONFINITE`（action / observation.state 中的 NaN/Inf）
- 告警类：`UNREFERENCED_VIDEO`、`UNREFERENCED_DATA_PARQUET`、`RAW_IMAGES_REMAIN`、`VIDEO_FRAME_COUNT_ESTIMATED`

### 12.2 `scripts/repair_lerobot_video_gaps.py`（186 行）

第二阶段：修复视频里存在「无索引帧空洞」的数据集。逐帧解码而非信任头，必要时重编码压缩帧区间，并重写 episode 的 `from_timestamp` / `to_timestamp`。

```bash
python scripts/repair_lerobot_video_gaps.py --source /path/in --output /path/out
```

输出目录必须不存在（也会检查 `.{name}.incomplete` 暂存目录）。**源数据集永不修改**；未完成的原始 `images/` 残留有意不拷贝。

### 12.3 三阶段修复流程

`DatasetRepairer.run()` 编排三个显式阶段到一个**新**目录，最后复验：

1. **Stage 1 — 规整元数据与全局索引** → `.{output}.metadata-fixed`
   重映射 `episode_index`（旧→新连续）与全局 `index`；重算逐集 `episode_index` / `index` stats，用 `aggregate_stats` + `write_stats` 重新生成 `meta/stats.json`；只硬链接（或复制）被引用的视频；写出 `repair_manifest.json`（源/目标、`episode_mapping`、保留的 episode/帧、策略说明「data parquet 与匹配的 episode 元数据是权威」、三步工作流说明）
2. **Stage 2 — 压缩被引用的视频区间** → `.{output}.validated-candidate`
   调用 `repair_video_gaps`；源区间已连续且物理帧数匹配则 `shutil.copy2`，否则用上游 `_keep_episodes_from_video_with_av` + `encoder_config_from_video_info` 重编码并校验帧数
3. **Stage 3 — 全量复验**
   用新的 `IntegrityChecker(candidate, decode_videos=True)` 必须报 valid；通过才原子 `rename()` 到最终路径，失败则 `rmtree` 候选目录

**安全前置条件**：输出必须不同于源（禁止原地修复）；输出/暂存/候选路径必须不存在；**任何不在 `REPAIRABLE_ERROR_CODES` 白名单内的错误码都会中止修复**（「损坏是歧义的或破坏性的」）；data parquet 的 episode 集合必须与元数据 episode 集合相等。

---

## 13. 仿真栈 alohamini_sim

目标：**把手机拍的真实房间变成可交互的 Isaac Sim 场景，生成脚本化操作数据，导出成 LeRobotDataset 与真机数据混合训练。**

```
alohamini_sim/
├── video2sim/     # 手机视频 → NuRec splat 房间 + TSDF 碰撞体 → Isaac Sim 5.x
└── data_engine/   # 脚本化仿真 episode 引擎 + LeRobotDataset 桥接
    ├── data_gen/aspire_engine/     # ASPIRE 引擎：技能运行时、任务编译、修复循环
    ├── data_gen/intern_engine/     # InternDataEngine 风格流水线：Load→Plan→Render→Store
    ├── agents/aloha_mini/          # ManiSkill agent（SO100 / Pro 并行夹爪）
    └── lerobot_bridge.py            # episodes → LeRobotDataset (v3.0)
```

### 13.1 video2sim

把**单次手持手机漫游**变成 Isaac Sim 5.x 舞台：一个可照片级渲染的 NuRec Gaussian-splat 房间，外加一个**不可见、有公制、重力对齐**的 TSDF 碰撞体。

**明确 SfM-free**——不用 COLMAP/GLOMAP 建图。COLMAP 仅作为**文本模型容器**（`sparse/0/cameras.txt|images.txt|points3D.txt`），由 `to_colmap.py` 写、由 `pycolmap` 读回。相机位姿来自 LingBot-Map 流式推理，并在 splat 训练中**联合精化**（逐视图 se3 经光栅化梯度，view 0 作为规范锚点）；splat 用 **MV 一致的 TSDF 点云稠密初始化**（InstantSplat 思路，350k 点）——正是这个稠密初始化把训练从 80k 迭代压到 **10k 迭代（约 20 分钟）**，floating point 少 38 倍。

流水线（每阶段既可 `import` 也可 `python -m video2sim.<stage>` 运行）：

```
手机视频 → extract(ffmpeg, 8fps)
        → lingbot_infer(LingBot-Map 流式位姿+深度, fp8 KV, sw=48)
        → fuse(MV 一致性过滤 + 4mm TSDF 融合)  → to_colmap(LingBot E/K + TSDF 稠密点云)
        → refine(孤岛过滤/RANSAC/地面 z=0/公制缩放) → train(gsplat MCMC 10k iters + 联合位姿优化)
        → scene_prep(降 30 万面 → collider.npz)   → export(splat.pt → SH3 PLY → scene.usdz)
        → scene(splat + 隐形碰撞体 + 机器人 + Dome 450 → scene.usd)
```

`cli.py` 是**纯编排器**（无业务逻辑）：按阶段把子进程路由到各自契约要求的解释器（**绝不在进程内自动切换**），计时，并支持**基于 sentinel 文件的断点续跑**。

```bash
python -m video2sim run VIDEO.mp4 --workdir OUT [--config cfg.yaml] \
    [--from STAGE] [--until STAGE] [--gui] [--force] \
    [--main-python P] [--nurec-python P] [--isaac-python P] \
    [--lingbot-repo DIR] [--lingbot-model CKPT] [--robot USD]
```

`--until` 默认停在 `scene_prep`；`--gui` 会顶到 `scene`。

**这些默认值不要随便改**（`configs/default.yaml` 注释原文："每个数字都是 ~10 次失败跑出来的"）：

| 坑 | 说明 |
|---|---|
| **GPU 必须独占** | 开一个 Isaac GUI 就要吃掉 8 GB 卡里的 3–4 GB；CUDA SfM / LingBot 推理 / splat 训练期间不能有别的进程 |
| **单相机强制** | 一条手机轨迹 = 一个相机 |
| **深度正则只能同轨配对** | 跨轨配对会**静默破坏几何**，而不是杀掉 floating point |
| **NuRec 需要 SH3 零填充 PLY** | 只有 SH0 会命中 ~47 s/帧的病态慢路径 |
| **MCMC splat 不能做不透明度剪枝** | 会删掉 ~79% 的 ensemble；只允许**空间**剪枝 |
| **`packed=True` 永远开**；位姿优化锚定 view 0 | — |
| **学习率必须按名字建字典** | `ParameterDict` 按字母序排 key，按位置 zip 会**静默打乱所有学习率**（opacities 拿到 1e-3 而非 5e-2）——README 原话："the single biggest cause of the fog splats" |
| **`scene_scale` 上限 6.0** | 走廊/前向运动场景会吹大 means-lr 与 MCMC 噪声，opacity 塌成雾 |

其他关键实现细节：

- `fuse`：在 ±4/±8/±12 邻帧重投影，3% 相对深度差、≥2 个邻帧一致、`depth_conf > 2.3`；**保留像素率就是位姿健康度**（同轨 ≈88%，跨轨 ≈58%）
- `refine`：相机轨迹门控 `above > 0.9`、`med > 0.2`、`spread < 0.45`——spread 专门用来**排除墙面**（手机相对地面高度恒定、到墙面距离变化大）；公制尺度用地面→天花板锚点（2.4 m），失败回退「手机手持高度 1.35 m」
- `export`：SH3 零填充 PLY（62 属性）；TSDF 空间剪枝半径 0.20 m
- `scene_prep`：**30 万三角面**是验证过的预算（避免 PhysX cooking 爆炸）；`.npz` 是 open3d(main venv) → pxr(Isaac venv) 之间**唯一的跨界物**
- `scene`：`Gf.Matrix4d` 用**行向量**约定；`CollisionAPI` 不配 `RigidBodyAPI` 即为静态；`DomeLight` 强度 450（1200+ 会把 splat 曝成白模糊）
- `check_env`：纯标准库的预检 pass/fail 表，任一 FAIL 退出非零

### 13.2 data_engine

三层依赖预算，刻意分离：

**第 1 层 — Planner/skills（vendored，仅执行层）**

`data_gen/` 是 AlohaMini `maniskill/data_gen` 的原样 vendored 副本，`agents/aloha_mini/` 是配套的 ManiSkill agent 包。

- **aspire_engine**（2486 行）
  - `engine.py` — `run_episode(command, seed, cfg)`：建环境 → 解析物体 → 编译技能程序 → **预先校验 pick 和 place 两个站点的可行性** → 执行技能 → 判定成功（move/place `xy_err < 0.06`，push `≤ 0.05` 且仍在桌面）
  - `skills_runtime.py`（777 行）— 执行器。**站点物理校验**（2 yaw × 5 dx × 3 by 候选 → 传送底盘 + 步进 6 次物理 → `base_err > 0.02` 拒绝）；**desc-first IK 分支** + **straddle-first 航点下降**（先求抓取位姿，再由它播种预抓取位姿；先到抓取点**正上方**的航点再垂直下降）——这是 `9aee5af5` 修的「手掌横扫物体顶」的 bug
  - `task_compiler.py` — 自然语言 → 原子技能程序。动词 `{move, gather, push, pick}`，约 80 个 YCB 物体 ID
  - `nav_planner.py` — 纯 numpy 2D 导航（`OccupancyGrid` + A\* octile + 视线捷径平滑）
  - `aspire_loop.py` — **agentic 修复循环**：`run_with_repairs(max_attempts=4)`，失败症状匹配技能库后做参数化修复（pitch 变异、底盘重定位、push 收缩、重摇种子等）；**只有验证通过的修复才被准入 `repairs_log.jsonl`**
  - `skills/library/` — 13 个 ASPIRE §2.2 格式的 JSON 技能定义
- **intern_engine**（2621 行）— Load → Plan → Render → Store 四阶段；`skills/ik.py` 是 IK 核心（阻尼最小二乘 + 有限差分雅可比，5 DoF；`solve_arm_ik_full_pose` 额外处理**夹爪开口分离轴**，供 6 DoF Pro 臂使用）；`writers/lerobot_v21.py` 是一个**不 import lerobot** 的自包含 v2.1 写入器

**第 2 层 — Bridge（在本仓库 uv 环境内运行）**

[alohamini_sim/data_engine/lerobot_bridge.py](alohamini_sim/data_engine/lerobot_bridge.py) 把引擎 episode 转成 LeRobotDataset **v3.0**（`create` → `add_frame` → `save_episode` → `finalize`）。只依赖 numpy + 仓库内 dataset API，**无模拟器依赖**。

- 16 维 `observation.state` / `action`，命名与 `AlohaMini._state_ft`（`so-arm-5dof` profile）一致：`arm_left_{6关节}.pos` + `arm_right_{6关节}.pos` + `x.vel` / `y.vel` / `theta.vel` + `lift_axis.height_mm`
- **值映射**：
  - 手臂关节原样拷贝（弧度）。真机录制存的是归一化电机量程——**单位对齐需要真机标定，留给调用方**
  - 夹爪：仿真米制手指位置 → 可选 `gripper_range=(closed, open)` 线性映射到真机 0–100
  - `x.vel`/`y.vel`：仿真记录世界系根位置 → 有限差分 `(p[t]−p[t−1])×fps` 再按 `yaw[t]` 旋回机体系；**动作**速度是单步「到达速度」`(target[t]−p[t])×fps`，同样旋转
  - `theta.vel`：偏航角速度（度/秒），带角度回绕
  - `lift_axis.height_mm`：仿真 `vertical_move`（米）× 1000
- 仿真专有元数据（seed / command / traces / final）在 LeRobotDataset schema 里无处安放，**被丢弃**

```bash
python -m alohamini_sim.data_engine.lerobot_bridge \
    --episodes out/episodes.pkl --repo-id local/alohamini_sim_pick --root out/lerobot_ds \
    [--fps 20] [--gripper-range CLOSED OPEN] [--parallel-encoding] [--no-videos]
```

**第 3 层 — Assets**：agent URDF + STL 网格，`ALOHAMINI_URDF_DIR` 可覆盖目录。

### 13.3 ⚠️ alohamini_sim 的实际状态

**这一半是 vendored 参考实现，在当前 checkout 里跑不起来。**

| 问题 | 核验结果 |
|---|---|
| **URDF 完全缺失** | `git ls-files alohamini_sim \| grep urdf` → 空；磁盘上也没有。README 声称的 `aloha_mini_pro_v2.urdf` / `_v3.urdf` / `maniskill_so100_version.urdf` **全不存在** → `resolve_urdf()` 会回落到 `~/.maniskill/data/robots/aloha_mini`（vendoring 本想消除的仓库外旧安装） |
| **二进制资产全是未拉取的 LFS 指针** | 所有 `*.STL` / `*.usd` / `*.usdz` 都是 130 字节指针；`git lfs ls-files` 返回空 |
| **43 处硬编码 `/home/perelman/`** | `cli.DEFAULTS`、`lingbot_infer`、`export`、`check_env` 及每个模块 docstring。三个 venv 必须全部覆写 |
| **ASPIRE 路径全程 state-only** | `render_mode=None`，`SkillRuntime._run` 恒记 `"rgb": None` → bridge 产出的数据集**没有 `observation.images.*`**，视觉数据生成端到端不通 |
| **`pick` / `gather` 动词必然判失败** | 最终成功判定恒为 `‖obj_final[:2] − target_xy‖ < 0.06`，而 pick 的物体停在抓取点，离默认 target `[0.06,−0.31]` 很远 |
| **修复循环不在数据生成路径上** | `generate_dataset → _worker → run_episode` 直接调引擎；`aspire_loop` 只能单独 `python -m` 运行（且跑的是硬编码 push 回归用例） |
| **三个互不兼容的写入器** | aspire 写 v2.1 / 18 维 state + 16 维 action；`lerobot_v21.py` 写 v2.1 / **12 维纯手臂**（丢掉底盘与升降）；bridge 写 v3.0 / 16 维 AlohaMini 约定 |
| **16 维布局写死 5 自由度** | `AlohaMiniProV3` 是 6 关节/侧（20 qpos → 18 维动作），环境注册支持，但无任何写入器/桥接路径覆盖 |
| **`spots.py` 产出无人消费** | `scene.py` **没有应用任何 ROOM_SHIFT**，仓库里也没有 Isaac 侧 `rep.create.camera` 脚本 |
| **死代码** | `annotations.py`（引擎用 `engine._annotation()`）、`nav_planner.py`（`SkillRuntime` 直接 `interp()`，不走 A\*） |
| **`--depth-reg` 编排器从不传** | README 的「去雾」深度正则只有手动跑 `python -m video2sim.train` 才可用 |
| **未打包** | `pyproject.toml` 的 `packages.find where = ["src"]` 排除了它，bridge 只能在仓库根目录导入 |

**能在本仓库 CI 里跑的部分**：`tests/test_alohamini_sim_bridge.py`、`tests/test_alohamini_sim_engine_imports.py`，以及 CPU-only 的 `alohamini_sim/video2sim/tests/test_smoke.py`。

---

## 14. 调试工具

[examples/debug/](examples/debug/) 是面向 Feetech 串口总线的低层排查工具集。

```bash
# 查看全部电机状态
python examples/debug/motors.py get_motors_states --port /dev/ttyACM0

# 只驱动移动底盘
python examples/debug/wheels.py --port /dev/ttyACM0

# 只驱动升降轴
python examples/debug/axis.py --port /dev/ttyACM0

# 指定 ID 转动 / 改 ID / 设相位 / 回中点 / 关扭矩
python examples/debug/motors.py move_motor_to_position --id 1 --position 2 --port /dev/ttyACM0
python examples/debug/motors.py configure_motor_id   --id 1 --set_id 8 --port /dev/ttyACM0
python examples/debug/motors.py configure_motor_phase --set_phase 12 --port /dev/ttyACM0
python examples/debug/motors.py reset_motors_to_midpoint --port /dev/ttyACM1
python examples/debug/motors.py reset_motors_torque      --port /dev/ttyACM0

# 执行动作脚本
python examples/debug/motors.py move_motors_by_script --script_path examples/debug/action_scripts/test_dance.txt --port /dev/ttyACM0
```

`motors.py`（767 行）支持脚本中的 `{Present_Position}` 占位符表达式。`wheels.py`（283 行）是三全向轮键盘遥操作（`Goal_Speed` 原始 16 位写入）。`axis.py`（138 行）是带过流保护的升降轴演示（1000 mA 切断）。

其他：`test_cv.py`（OpenCV + 相机）、`test_cuda.py`（GPU 冒烟）、`test_network.py`（连通性）、`test_dataset.py`（读 parquet）、`test_input.py`（无头/Wayland 键盘诊断）、`test_mic.py`（音频设备）。

---

## 15. 测试

### AlohaMini 专属（2244 行，9 个文件）

| 文件 | 行数 | 覆盖 |
|---|---:|---|
| `test_alohamini_host.py` | 644 | 运动 profile 配置校验、state-only 观测无 JPEG 帧、客户端 token 选载荷、**用标定换算物理角度做卡滞判断**、空闲周期只告警不改目标、编码器抖动仍告警、电流单位与上一电机无关 |
| `test_alohamini_command_safety.py` | 437 | 控制权独占与竞争者拒绝、看门狗续租只在写入成功后、**重放/旧会话命令被拒**、legacy 客户端不可被抢占、ROS 独占时客户端不发命令、未发出的动作不谎报为已发送、缓存读取不能延长反馈截止期 |
| `test_alohamini_recording.py` | 262 | 控制缓冲可跨越多个 tick、**对齐误差超限拒绝**、相机门控要求所有相机推进、停滞与偏斜诊断、单速率循环保持原行为 |
| `test_alohamini_sync_feedback.py` | 217 | 刷新丢弃预取 token 不逐个等待、**同步推理后重新检查反馈**、录制延迟上限不阻断评估 |
| `test_alohamini_ros_compat.py` | 192 | 50 Hz 分支保留原相机默认值、`:state` 后缀向后兼容、相机流携带采集时间与 RGB 顺序、帧与时间戳原子一致 |
| `test_alohamini_camera_warnings.py` | 128 | 禁用相机不告警、缺失相机每集只告警一次、state-only 不触发、恢复后才再次告警 |
| `test_alohamini_observation_backpressure.py` | 79 | 队列背压不报错不记录请求、窗口在背压时停止并后续补充、真实传输错误可见 |
| `test_alohamini_sim_bridge.py` | 201 | Bridge 逐维值映射、写-读回环、state-only episode、CLI |
| `test_alohamini_sim_engine_imports.py` | 84 | 保证 `data_gen/__init__.py` 不把 `mani_skill` 拉进 `sys.modules` |

另有 `tests/scripts/test_check_lerobot_dataset_integrity.py`（147 行）。

### ⚠️ 覆盖缺口

- `am_act`：**零测试**
- `alohamini_sim` 的 video2sim / data_engine 执行路径：**无测试**（仅 CPU-only 冒烟）

---

## 16. 文档索引

| 文档 | 面向 | 内容 |
|---|---|---|
| [README.md](./README.md) | 所有人 | 英文简介、产品链接、团队信息 |
| **本文件** | 所有人 | 中文总览与深度技术说明 |
| [AGENTS.md](./AGENTS.md)（= `CLAUDE.md`） | AI agent / 贡献者 | 架构、开发命令、模块约定、mypy 严格模块列表 |
| [AGENT_GUIDE.md](./AGENT_GUIDE.md) | 普通用户 | SO-101 全流程：装机器→标定→录数据→**选策略（带实测显存/耗时对照表）**→训练多少 epoch（附 steps 换算表）→评估。含红色 LED 排障图解 |
| [docs/alohamini/](docs/alohamini/) | AlohaMini 用户 | **`getting_started.md`（新设备开箱手册，按阶段 12 步 + 检查清单）**、`install.md`（conda/uv/串口/HF）、`alohamini.md`（双机全流程 414 行）、`am-arm200.md`（单臂全流程 206 行）、`profiles.md`（型号对照表）、`commands.md`（639 行速查表） |
| [docs/source/](docs/source/) | 上游 HF 文档 | 策略、硬件、基准、高级训练 |
| [AI_POLICY.md](./AI_POLICY.md) | 贡献者 | AI 辅助使用规范（需披露、人类负责、噪音需甄选） |

---

## 17. 已知问题与风险清单

### 高

1. **`alohamini_sim` 在当前 checkout 不可用** — URDF 缺失、LFS 未拉、43 处硬编码路径。
2. **`am_act` 零测试 + `docs/` 无文档 + 两个死配置项**。
3. **`so_follower` 的过流保护全局影响 SO-100/101 用户** — 每次读状态多一次串口读，超 2500 mA 连续 20 次会**硬断连**并抛 `RuntimeError`。
4. **`SerialMotorsBus.num_retry` 默认 0 → 3** 是跨项目的全局行为变更，上游合并冲突高发点。

### 中

5. `lerobot_record.py` 的 `else` 分支丢弃 `lift_action` — 无底盘动作时升降指令不下发。
6. `record_bi_multirate.py` 无 `control_fps` CLI 旋钮，且 `--dataset.fps > 50` 会直接抛错。
7. 三个数据集写入器的维度约定不兼容；intern 路径完全丢失底盘与升降通道。
8. `scripts/` 两个工具位于 `src/` 外，装成包后不可导入（测试靠仓库根相对路径）。
9. ASPIRE 路径全程 state-only → **视觉数据生成端到端不通**。
10. `pick` / `gather` 动词在 vendored 引擎中必然被判失败。

### 低

11. `video2sim/video2sim/__init__.py` docstring 仍写 `extract → sfm → train`（无 `sfm` 阶段，实际是 `to_colmap`）。
12. `alohamini_sim/README.md` 称 bridge 输出 v3.0，但 vendored `writer_adapter` 写 v2.1——两者是不同产物，README 未说明关系。

---

## 18. 开发工作流

```bash
# 依赖
uv sync --locked
uv sync --locked --extra test --extra dev
uv sync --locked --extra all
git lfs install && git lfs pull

# 测试
uv run pytest tests -svv --maxfail=10
DEVICE=cuda make test-end-to-end          # 全部 E2E
uv run pytest alohamini_sim/video2sim/tests -q   # video2sim CPU 冒烟

# 规范
pre-commit run --all-files                # ruff / typos / bandit / mypy / gitleaks

# 提交
git commit -s                             # 建议带 sign-off
```

> **优先使用 `uv run`** 执行 Python 命令，不要直接用 `python` 或 `pip`。

**Mypy 是渐进式**的：仅 `lerobot.envs`、`lerobot.configs`、`lerobot.optim`、`lerobot.model`、`lerobot.cameras`、`lerobot.motors`、`lerobot.transport` 是严格模式，修改这些模块时需补类型标注。

**可选依赖**：多数策略、环境、机器人都在 extras 后面（如 `lerobot[aloha]`），新引入可选包必须做惰性导入或加保护。

---

## 19. 团队与致谢

AlohaMini 由 **Li Yiteng** 与 **Wu Zhiyong** 创建。

- Email：liyiteng+github@gmail.com
- WeChat：liyiteng

硬件与产品：

- [AlohaMini](https://github.com/liyiteng/alohamini)
- [AM-ARM200](https://github.com/liyiteng/AM-ARM)

致谢：

- [LeRobot](https://github.com/huggingface/lerobot) — 本仓库所基于的软件栈
- [ALOHA](https://tonyzhaozh.github.io/aloha/) — 双臂遥操作范式
- [SO-ARM100](https://github.com/TheRobotStudio/SO-ARM100) — 低成本开源机械臂设计范式

---

<div align="center">

**License** — Apache License 2.0，详见 [LICENSE](./LICENSE)

</div>
