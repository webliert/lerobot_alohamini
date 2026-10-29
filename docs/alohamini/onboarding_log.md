# AlohaMini 上手进度记录

> **用途**：记录实体设备上手过程中的**实测结论**，供下次接手时直接续做，避免重复排查。
> 配套手册：[getting_started.md](getting_started.md)（流程）· [profiles.md](profiles.md)（型号）· [commands.md](commands.md)（命令速查）
>
> 最后更新：**2026-10-29**

---

## 状态摘要

| 项 | 状态 |
|---|---|
| **当前阶段** | 第 4 步 · 底盘 / 升降 / 相机 / 从臂 单独测试（**进行中**：底盘 ✅ · 从臂读数 ✅ · 相机 ✅ · 升降 ✅，仅剩**从臂 `jog`** 未跑） |
| **下一步** | ① `lift.py --heights 0,400,500 --dwell 20 --show-registers` 探机械行程上限 + 查清下降段 0 mA（§6.7）→ ② 从臂 `jog`（已修使能瞬间的跳变隐患，§6.8）→ ③ 补抓相机 PNG 确认视角（§6.4 #8）→ ④ 修 Host 力矩（§8，**不是简单取消注释**，见该条） |
| 机器人型号 | ✅ **已确定：`alohamini1`** |
| 手臂串口 | ✅ 已确认（含序列号映射） |
| 相机 | 配置已提交（MJPG，`head_front` + `head_top`）；✅ Pi 侧已同步并**开图成功**（§6.5）；⏳ **视角/上下镜像待复核**（§6.4 #8）|
| 从臂标定 | ✅ **已完成**（EEPROM `Homing_Offset` 非零）；⚠️ 2 个关节的限位可疑，待核对（§6.4） |
| 底盘测试 | ✅ **通过**（2026-10-29 真机复测，6 个动作 raw 与模型全对，见 §6.1） |
| 升降测试 | ✅ **通过**（2026-10-29 真机两轮：0/80/200/300/80/10 全部到位，**单圈回绕处理经真机验证**，见 §6.7）；⏳ 机械行程上限未探明（已确认 ≥300 mm）、下降段无负载反馈待查 |
| 相机测试 | ✅ **通过**（2026-10-29 真机：`head_front` + `head_top` 全部 OK，见 §6.5）；⏳ 视角待确认 |
| 从臂测试 | ✅ `read` 模式通过；⏳ `jog` 模式未跑（**已修使能瞬间跳变隐患**，见 §6.8）；⚠️ 读数显示**力矩为关**（0.0 mA） |
| Host 启动 | ⬜ 未开始（**阻塞**：`alohamini.py:545`/`:567` 的 `enable_torque()` 被注释；⚠️ **不能只解注释**，三个电机类别的寄存器都得先处理，见 §8） |
| 主臂标定（PC） | ⬜ 未开始 |
| 遥操作验收 | ⬜ 未开始 |
| 数据采集 | ⬜ 未开始 |

---

## 1. 环境

| 项 | 值 |
|---|---|
| 树莓派 | `pi5@raspberrypi`，主机名 `raspberrypi` |
| **树莓派 IP** | **`10.168.1.110`**（`<Pi_IP>`） |
| 树莓派仓库路径 | `~/lerobot_alohamini`（即 `/home/pi5/lerobot_alohamini`） |
| 树莓派 Python 环境 | conda env `lerobot_alohamini`（已激活） |
| 树莓派 Python 版本 | ✅ **Python 3.12**（conda env **`lerobot_alohamini`**，与 PC 同名；清华镜像源，见 §1.1） |
| 树莓派串口权限 | ✅ 可正常访问 `/dev/ttyACM*`（`dialout` 已生效） |
| PC 终端环境 | 原生 Linux（内核 `6.8.0-65-generic`），`/home/szxx/lxy_ws/lerobot_alohamini` |
| PC Python 环境 | conda env `lerobot_alohamini`（`~/Downloads/New_miniconda3/envs/lerobot_alohamini`，editable 安装指向本仓库 `src/lerobot`，依赖齐全） |
| PC Python 版本 | ✅ **Python 3.12.16**（conda-forge 经清华镜像，2026-10-28 建） |
| PC 角色 | Leader 臂 + 策略推理/训练（**Leader 臂尚未接入**） |
| 网络 | 树莓派与 PC 需同局域网，**IP 待确认**（后续所有命令要用 `<Pi_IP>`） |

> **环境决策（2026-10-28）**：PC 与树莓派**统一使用 conda env `lerobot_alohamini`**，
> **不再用 `uv sync` 建 `.venv`**。所有命令在 `conda activate lerobot_alohamini` 之后直接用 `python` 执行。
> 文档里出现的 `uv sync` / `uv run` 写法均为备选，不是本项目的执行方式。

### 1.1 两端环境一致性约定（2026-10-29）

**结论：两端 Python 版本已对齐到 3.12.16；真正必须一致的其实是 `lerobot` 的代码版本。**

| 项 | 是否必须一致 | 原因 |
|---|---|---|
| Python 版本 | 原则上是（已对齐 3.12.16） | 但**技术上不必** —— 两端是独立进程，只通过 ZMQ 传序列化字节，不共享 Python 对象，没有 pickle 协议版本问题 |
| conda env 名字 | 建议一致（`lerobot_alohamini`） | 文档可读性，非技术必需 |
| **`lerobot` 代码版本（commit）** | ✅ **必须** | action / observation 键名要对齐：`arm_left_shoulder_pan.pos`、`x.vel`、`lift_axis.height_mm`、`observation.images.head_front` |
| 相机键名 | ✅ 必须 | 进数据集 schema，一开采集就固定 |
| 标定数据（EEPROM + 标定 JSON） | ✅ 必须 | 角度换算直接依赖 EEPROM 的 `Min/Max_Position_Limit` |

> ⚠️ **真正的风险是代码版本不一致，不是 Python 版本不一致**：
> PC 发出的 `arm_left_shoulder_pan.pos` 如果 Pi 上的 `send_action()` 不认这个键
> （`alohamini.py:838-852` 是按前缀筛的），会**静默不动**，不报错。

**核对代码版本**（两端各跑一次，应完全相同）：

```bash
git rev-parse HEAD
```

#### 为什么树莓派必须用 3.12（不能用 3.10）

用 `ast.parse(feature_version=(3,10))` 扫过全部 502 个 `.py`，发现 **4 处 PEP 695 语法**（3.12 独有），
其中 2 处**在 Host 的 import 链上** → Python 3.10 上 import 阶段就 `SyntaxError`：

| 文件 | 行 | 语法 |
|---|---|---|
| `src/lerobot/motors/motors_bus.py` | 50-51 | `type NameOrID = str \| int` |
| `src/lerobot/processor/pipeline.py` | 254 | `class DataProcessorPipeline[TInput, TOutput](HubMixin)` |
| `src/lerobot/utils/io_utils.py` | 93 | `def deserialize_json_into_object[T: JsonLike](...)` |
| `src/lerobot/datasets/streaming_dataset.py` | 61 | `class Backtrackable[T]` |

再加上 `src/lerobot/configs/video.py:23` 的 `from typing import ... Self`（`typing.Self` 是 3.11+）
和 `pyproject.toml:32` 的 `requires-python = ">=3.12"`，一共 6 处要改 —— 而这些**全在上游跟踪的公共代码里**，
改完会持续制造与上游 lerobot 的合并冲突。

**树莓派上 3.12 是可用的**（2026-10-29 实测 `conda search -c conda-forge "python=3.12" --platform linux-aarch64`
→ conda-forge 有到 3.12.16，`pkgs/main` 也有 3.12.16）。所以**不需要回退 PC，也不需要改仓库代码**。

#### 树莓派重建 3.12 环境的完整步骤

```bash
# 0. 先把 conda-forge 配成首选频道（比每次命令行加 -c 更省事，见下方「为什么 -c conda-forge 有效」）
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge
conda config --set channel_priority strict
conda config --show channels          # 确认 conda-forge 在第一位

# 1. 建新环境（先建新名，保留 3.10 那个作兜底，验证通过再换名）
conda create -n lerobot_alohamini_312 python=3.12 -c conda-forge -y
conda activate lerobot_alohamini_312
python -V                      # 期望 Python 3.12.16

# 2. 同步仓库代码（这一步同时解决 §6.2 的旧版本问题）
cd ~/lerobot_alohamini
git pull

# 2a. 配清华镜像（国内网络；PC 端已用同一套 conda 源，见 §1 环境表）
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 2b. 先干跑验证解析（不下载 wheel，约几分钟：torch 的索引页很大）
pip install -e . --dry-run

# 2c. 正式安装
pip install -e .

# 3. 验证 import 链 + 版本
python -c "import lerobot, lerobot.robots.alohamini as m; print(lerobot.__file__); print(m.__file__)"
python -c "from lerobot.robots.alohamini.config_alohamini import alohamini_cameras_config; print(list(alohamini_cameras_config()))"
python -c "from lerobot.robots.alohamini.lift_axis import LiftAxisConfig; print('descent_floor_mm' in LiftAxisConfig.__dataclass_fields__)"
# 期望第三条输出 True

# 4. 重跑之前失败的两个脚本
python examples/debug/cameras.py
python examples/debug/lift.py --port /dev/am_arm_follower_left --heights 0,80,200,80,10

# 5. 验证通过后换成正式名，与 PC 保持同名
conda env rename -n lerobot_alohamini lerobot_alohamini_310   # 旧的先改名留底
conda env rename -n lerobot_alohamini_312 lerobot_alohamini   # 新的改成正式名
```

> `conda env rename` 需要 conda ≥ 4.9。若报命令不存在，直接改目录名：
> `mv ~/miniconda3/envs/lerobot_alohamini_312 ~/miniconda3/envs/lerobot_alohamini`
> （先确保旧的已经改名或移走）。

#### 为什么 `-c conda-forge` 能装上 3.12（而之前装不上）

**结论：关键不是命令行那个 `-c`，而是「conda-forge 有没有被配成可用频道」。**

PC 端的硬证据 —— `~/.condarc`：
```yaml
channels:
  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge
  - defaults
auto_activate: false
show_channel_urls: true
```

而 PC 上创建 3.12 环境时**命令行并没有加 `-c`**：
```
# cmd: /home/szxx/Downloads/New_miniconda3/bin/conda create -y -n lerobot_alohamini python=3.12
```
但 `conda-meta/history` 显示实际拉到的包**全部来自 conda-forge**：
```
+https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge/linux-64::python-3.12.16-h5f976f7_0_cpython
+https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge/linux-64::libpython-3.12.16-ha57cdbe_0_cpython
```
→ **`.condarc` 里 conda-forge 排在第一位 = 等价于每次都自动带上 `-c conda-forge`。**
`-c` 只是命令行上的**一次性覆盖**，`.condarc` 是**持久配置**，两者效果相同。

Pi 上之前装不上，最可能是下面三个原因之一（可用右侧命令逐个排除）：

| 候选原因 | 判定命令 | 典型症状 |
|---|---|---|
| **Pi 的 `.condarc` 里没有 conda-forge**，只能从 `defaults` 拿 | `conda config --show channels` | 列表里只有 `defaults` |
| `defaults`（Anaconda 官方频道）对 **linux-aarch64** 的覆盖比 conda-forge 窄，且有商业授权限制 | `conda search python=3.12 --platform linux-aarch64`（**不加** `-c`）| 结果里没有 3.12，或解析直接报错 |
| **Pi 的 conda 版本太老**，读不了 conda-forge 现在的 zstd 压缩 repodata | `conda --version` | conda < 23.1 时，conda-forge 会出现 `JSONDecodeError` / 读频道失败 |

**2026-10-29 镜像侧实测（把候选原因收窄）**

用清华镜像的目录清单直接核对，**"aarch64 上装不了 python 3.12" 这条可以排除**：

| 检查项 | `pkgs/main/linux-aarch64` | `conda-forge/linux-aarch64` | 结论 |
|---|---|---|---|
| `python 3.12` | ✅ 有（3.12.0 – 3.12.16） | ✅ 有 | 两边都有 |
| `ld_impl_linux-aarch64`（CPython 3.12 在 aarch64 上的 C 运行时垫片） | ✅ 有（2.36.1 / 2.38 / 2.40 / 2.44） | — | **不缺包** |
| `.conda` 包总数 | 61,593 | 291,472 | conda-forge 是 `defaults` 的 4.7 倍 |

> ⚠️ 更正一条**之前查错的结论**：曾用 `ld_impl_so` 这个名字去 grep，得到「TUNA 的 aarch64 频道里没有这个包」的结论 ——
> **那是包名写错了**（实际叫 `ld_impl_linux-aarch64`）。用对的名字复查后**该包在 aarch64 频道里是存在的**，
> 所以「缺 `ld_impl_so` 导致解析失败」这条线索**作废**，不要再按它排查。

既然两个频道都有 python 3.12 且依赖闭包完整，那剩下的差异只可能出在**「哪个频道被真正用上了」**上：
`defaults` 指向 `repo.anaconda.com`（国内慢、偶发断流），而 conda-forge 若配成清华源则很快。
**所以重点仍是「Pi 的 `.condarc` 里有没有 conda-forge」**，而不是「aarch64 支不支持」。

**在 Pi 上并排对比验证**（这两条的差异就是原因）：
```bash
conda --version
conda config --show channels
conda search python=3.12 --platform linux-aarch64 | tail -15
conda search -c conda-forge python=3.12 --platform linux-aarch64 | tail -15
```
- 前一条缺 3.12、后一条有 → **频道覆盖问题** → 用 `-c conda-forge`，或写进 `.condarc`（推荐，见步骤 0）
- 两条都有 3.12 → 之前是 **conda 版本太老** 或 **网络/镜像问题** → 升级 conda：`conda install -n base -c defaults conda`

> ℹ️ PC 端 conda 是 **25.7.0**。建议显式设 `conda config --set channel_priority strict` ——
> 默认的 `flexible` 会为了拿更新的包去选高优先级频道，解析行为不直观。

---

#### 清华 PyPI 镜像可用性核对（2026-10-29 实测）

结论：**可以用**。`https://pypi.tuna.tsinghua.edu.cn/simple` 上 `pyproject.toml` 的 16 个核心依赖
**全部有 aarch64 wheel**，且版本区间都能满足仓库约束：

| 包 | 仓库约束 | 镜像上的 aarch64 可用版本 | 结论 |
|---|---|---|---|
| torch | `>=2.7,<2.12.0` | 2.7.0 / 2.7.1 / 2.8.0 / 2.9.0 / 2.9.1 / 2.10.0 / 2.11.0 | ✅ |
| torchvision | `>=0.22.0,<0.27.0` | 0.22.0 / 0.22.1 / 0.23.0 / 0.24.0 / 0.24.1 / 0.25.0 / 0.26.0 | ✅ |
| numpy | `>=2.0.0,<2.3.0` | 2.0.0 – 2.2.6 | ✅ |
| opencv-python-headless | `>=4.9.0,<4.14.0` | 4.9.0.80 – 4.13.0.92（`cp37-abi3`） | ✅ |
| Pillow | `>=10.0.0,<13.0.0` | 10.0.0 – 12.3.0 | ✅ |
| cmake | `>=3.29.0.1,<4.2.0` | 3.29.0.1 – 4.1.3 | ✅ |
| safetensors | `>=0.4.3,<1.0.0` | 0.4.3 – 0.9.0rc1 | ✅ |
| setuptools | `>=71.0.0,<81.0.0` | 71.0.0 – 80.10.2 | ✅ |
| einops / draccus / gymnasium / huggingface-hub / requests / packaging / termcolor / tqdm | 见 `pyproject.toml` | 纯 Python `py3-none-any`（与架构无关） | ✅ |
| torchcodec（`dataset` extra） | `>=0.11.0,<0.12.0` | 0.11.1 `cp312-cp312-manylinux_2_28_aarch64` | ✅ |
| av（`av-dep` extra） | — | 19.0.2 `cp312-abi3-manylinux_2_28_aarch64` | ✅ |

**注意事项**：

- `-i` / `--index-url` **只对那一条命令生效**。要长期使用就用 `pip config set global.index-url ...`（见步骤 2a）。
- **不要**给 `pip install -e .` 加 `--only-binary=:all:` —— editable 安装本身是源码构建，
  这个开关会和 PEP 517 build backend 的解析打架。要验证"能不能装上"，用 `--dry-run`（步骤 2b）。
- `pip install -e .` 走 PEP 517 build isolation，会额外从索引拉一个 `setuptools`（构建后端）。
  镜像上有，正常；若报构建后端拉取失败，加 `--no-build-isolation` 兜底（此时环境里必须已有 setuptools ≥71）。
- **3.10 环境里的 pip 缓存完全用不上**（cp310 与 cp312 ABI 不同），torch 的 aarch64 wheel 约 90–250 MB，
  加上 torchvision / opencv / numpy，**要预留 1–2 GB 磁盘和 10 分钟以上**。
- **解析阶段本身就很慢**：torch 的 simple 索引页很大（几十 MB），
  `pip install --dry-run` 实测在 PC 上跑了 20 分钟仍未出结果。**Pi 上请耐心等，不要中途 Ctrl-C**。

---

## 2. 已确认的硬件事实（实测）

### 2.1 串口与总线

```
for p in /dev/ttyACM*; do
  s=$(udevadm info --attribute-walk --name=$p 2>/dev/null | awk -F'"' '/ATTRS{serial}/{print $2; exit}')
  echo "$p  ->  $s"
done
```

| 端口 | 序列号 | 角色 | 在线电机 ID | udev 别名 |
|---|---|---|---|---|
| `/dev/ttyACM1` | `58CD181359` | **左总线** | `1,2,3,4,5,6` + `8,9,10`（底盘）+ `11`（升降） | `am_arm_follower_left` ✅ 厂商预装 |
| `/dev/ttyACM0` | `5AE6081591` | **右总线** | `1,2,3,4,5,6` | `am_arm_follower_right` ✅ 厂商预装 |

> **厂商已在 Pi 上预装 udev 规则**（创建于 Oct 27 05:55），映射正确：
> `/dev/am_arm_follower_left -> ttyACM1`、`/dev/am_arm_follower_right -> ttyACM0`。
> → **手臂部分不需要再装规则**，`config_alohamini.py` 的默认路径开箱即用。
> 规则原文位置待查：`grep -r am_arm_follower /etc/udev/rules.d/ /lib/udev/rules.d/`
>
> **重启验证（2026-10-28）**：编号**未互换**，与首次枚举一致。

`/dev/serial/by-id/` 原始条目：
```
usb-1a86_USB_Single_Serial_58CD181359-if00
usb-1a86_USB_Single_Serial_5AE6081591-if00
```

### 2.2 电机 ID 分布（`examples/debug/motors.py get_motors_states` 实测）

| 总线 | ID | 部件 |
|---|---|---|
| 左 | 1 | arm_left_shoulder_pan |
| 左 | 2 | arm_left_shoulder_lift |
| 左 | 3 | arm_left_elbow_flex |
| 左 | 4 | arm_left_wrist_flex |
| 左 | 5 | arm_left_wrist_roll |
| 左 | 6 | arm_left_gripper |
| 左 | 8 / 9 / 10 | base_left_wheel / base_back_wheel / base_right_wheel |
| 左 | 11 | lift_axis（升降轴） |
| 右 | 1–6 | 右臂同构 6 电机 |

> **ID 7 缺失是正常的**，不是故障：5 自由度臂 = 5 关节 + 1 夹爪 = 6 个电机。

### 2.3 电气状态（实测读数）

| 寄存器 | 读数 | 解读 |
|---|---|---|
| `Present_Voltage` | 124–125 | **12.4–12.5 V** → 12 V 系统 ✓ |
| `Present_Current` | 0.0（全部） | 扭矩未使能 + 空载，正常（debug 脚本不写 `Torque_Enable`） |
| `Load` | 0（全部） | 同上 |
| `Acceleration` | 254（全部） | 出厂默认值；Host 的 `configure()` 会改成 100，无需干预 |
| `Present_Temperature` | 23–36 °C | 正常（motor_5 最高 36 °C，通电待机的温升） |

---

## 3. 关键参数结论

> ## `robot_model = alohamini1`
>
> **推导依据**：双臂均为 6 电机（ID 1–6）→ `so-arm-5dof` profile。
> `alohamini2` / `alohamini2pro` 用 `am-follower-6dof`，应是 **7 电机（ID 1–7，含 wrist_yaw）**。

连带确定的整机规格（来自 `model_specs.py` 的 `ROBOT_SPECS["alohamini1"]`）：

| 项 | 值 |
|---|---|
| arm_profile | `so-arm-5dof` |
| base_motor | `sts3215` |
| lift_motor | `sts3215` |
| lead_mm_per_rev | 84.0 |
| wheel_radius | 0.05 m |
| base_radius | 0.125 m |
| 状态维度 | **16**（左臂 6 + 右臂 6 + x.vel/y.vel/theta.vel + lift_axis.height_mm） |

**Leader 臂 profile 推断**：机器人是 5 自由度，Leader 臂大概率也是 `so-arm-5dof` → `--teleop.id so101_leader_bi --teleop.arm_profile so-arm-5dof`。
⚠️ **待确认**：PC 上 Leader 臂的实际型号和 ID。

---

## 4. 相机现状

### 4.1 枚举结果（`v4l2-ctl --list-devices`）

| USB 设备名 | 采集节点 | 元数据节点 | **厂商别名** | `ATTRS{product}` | `ATTRS{serial}` | `ID_V4L_CAPABILITIES` |
|---|---|---|---|---|---|---|
| `am_camera_head_top` | `/dev/video0` | `/dev/video1` | **`/dev/am_camera_head_top`** | `am_camera_head_top` | `xhci-hcd.1` | `:capture:` |
| `am_camera_head_back` | `/dev/video2` | `/dev/video3` | **`/dev/am_camera_head_back`** | `am_camera_head_back` | `xhci-hcd.0` | `:capture:` |
| `am_camera_head_front` | `/dev/video4` | `/dev/video5` | **`/dev/am_camera_head_front`** | `am_camera_head_front` | `xhci-hcd.1` | `:capture:` |

判定依据：采集节点能列出完整格式表（MJPG + YUYV），元数据节点格式表为空。

> ### ⚠️ 厂商已预装**全部**别名，一条新规则都不用写
>
> `/etc/udev/rules.d/90-mydevice.rules`：
> ```udev
> SUBSYSTEM=="tty", ATTRS{serial}=="58CD181359", SYMLINK+="am_arm_follower_left"
> SUBSYSTEM=="tty", ATTRS{serial}=="5AE6081591", SYMLINK+="am_arm_follower_right"
> SUBSYSTEM=="tty", ATTRS{serial}=="5AE6081513", SYMLINK+="am_arm_follower_left"   # 另一套板子
> SUBSYSTEM=="tty", ATTRS{serial}=="5AE6082250", SYMLINK+="am_arm_follower_right"  # 另一套板子
> SUBSYSTEM=="video4linux", ATTRS{product}=="am_camera_head_top",   ATTR{index}=="0", SYMLINK+="am_camera_head_top"
> SUBSYSTEM=="video4linux", ATTRS{product}=="am_camera_head_back",  ATTR{index}=="0", SYMLINK+="am_camera_head_back"
> SUBSYSTEM=="video4linux", ATTRS{product}=="am_camera_head_front", ATTR{index}=="0", SYMLINK+="am_camera_head_front"
> SUBSYSTEM=="video4linux", ATTRS{product}=="am_camera_wrist_left",  ATTR{index}=="0", SYMLINK+="am_camera_wrist_left"
> SUBSYSTEM=="video4linux", ATTRS{product}=="am_camera_wrist_right", ATTR{index}=="0", SYMLINK+="am_camera_wrist_right"
> ```
>
> **相机的 `ATTR{index}=="0"`（单数）** 匹配 v4l 节点自身的 index 属性：
> `index0` = 采集节点，`index1` = 元数据节点。比重写 `ID_V4L_CAPABILITIES` 过滤更直接。
>
> **wrist_left / wrist_right 规则存在但设备未接** → 没有符号链接
> → 这正是**默认配置里 `wrist_right` 打不开的原因**（不是 bug，是硬件没有腕部相机）。
>
> ⚠️ **隐患**：`5AE6081513` / `5AE6082250` 两条规则指向与在用的**同名**符号链接。
> 当前每条名字只被一块板占用，不冲突；但若把那块板插到 Pi 上，
> 它会**抢走** `am_arm_follower_left`（udev 后匹配者胜）。插板前先 `ls -l /dev/am_arm_*` 确认。
>
> ### ⚠️ 相机的 `ATTRS{serial}` 不是芯片序列号
> 是 **USB 拓扑路径**（`xhci-hcd.N`），且 **head_top 与 head_front 同为 `xhci-hcd.1`**。
> → 任何相机的 udev 规则都**必须**用 `ATTRS{product}`。

### 4.2 格式支持（三台一致）

| FourCC | 分辨率 | 帧率 | 备注 |
|---|---|---|---|
| **MJPG** | 1280×720 / 800×600 / 640×480 / 320×240 / 160×120 / 176×144 / 352×288 / 1280×960 | 30 / 25 / 20 / 15 / 10 / 5 fps | ✅ **推荐** |
| YUYV | 同上（1280×720 仅 9/5 fps） | 30 / 25 / 20 / 15 / 10 / 5 fps | 带宽大，不推荐 |

### 4.3 需要忽略的伪相机

`/dev/video19`–`/dev/video35` 是**树莓派内置 ISP 的软件节点**（`pispbe` / `rpi-hevc-dec`），不是真实相机。
`lerobot-find-cameras` 对它们报的 FPS 警告 / read timeout **是噪声**，不必处理。

### 4.4 ⚠️ 关键差异：没有腕部相机

默认配置 `config_alohamini.py` 里是 `forward`（`/dev/am_camera_forward`）+ `wrist_right`（`/dev/am_camera_wrist_right`），
而本机是 **head_top / head_back / head_front 三台头部相机**。

- `/dev/am_camera_forward` —— 厂商规则里**没有**这一条 → 路径不存在
- `/dev/am_camera_wrist_right` —— 规则存在但**设备没接** → 符号链接没生成

→ **默认配置必然开不了相机**，Host 会在 `cam.connect()` 处抛异常。**配置必须改。**
→ 相机键名会进入数据集 schema（`observation.images.<key>`），一旦开始采集就固定。

### 4.5 建议：强制 MJPG

`OpenCVCameraConfig` 有 `fourcc` 参数但 AlohaMini 配置未使用，实测默认协商到 **YUYV**。
640×480 YUYV@30fps ≈ **18 MB/s/台**，3 台 ≈ 55 MB/s，单 USB 2.0 带宽就吃满了 → 控制循环会掉帧。
MJPG 约几百 KB/s。**配置里应加 `fourcc="MJPG"`**。

---

## 5. 下一步（续做从这里开始）

### 5-1 ~~装 udev 规则~~ → **不需要，已由厂商预装** ✅

手臂和相机的别名**全部已存在且映射正确**，见 §4.1。
仓库里的 `docs/alohamini/udev/90-alohamini.rules` 只作为说明与备份，**不必安装**。

**唯一要做的**：把 `config_alohamini.py` 的相机路径改成厂商别名。

### 5-2 同步相机配置到树莓派 + 验证 ✅ **已完成（2026-10-29）**

> ✅ Pi 上的 `config_alohamini.py` 已是新版（2026-07-11 改名后的版本）。
> 验证：`alohamini_cameras_config()` 返回 `['head_front', 'head_top']`
> （旧版用的是 `forward` / `wrist_right` 键名，见 §4.4）。
> udev 别名本身**不需要新建** —— 厂商规则已预装全部 `am_camera_*`（§5-1）。

同步后验证：

```bash
python -c "
from lerobot.robots.alohamini.config_alohamini import alohamini_cameras_config
for k, v in alohamini_cameras_config().items():
    print(f'{k:12s} {v.index_or_path}  {v.width}x{v.height}@{v.fps} fourcc={v.fourcc}')
"
```
**期望**：
```
head_front   /dev/am_camera_head_front   640x480@30 fourcc=MJPG
head_top     /dev/am_camera_head_top     640x480@30 fourcc=MJPG
```

再实际打开一次确认能出图：
```bash
python -c "
from lerobot.cameras.opencv.camera_opencv import OpenCVCamera
from lerobot.robots.alohamini.config_alohamini import alohamini_cameras_config
for name, cfg in alohamini_cameras_config().items():
    cam = OpenCVCamera(cfg); cam.connect(); f = cam.read()
    print(name, 'shape=', None if f is None else f.shape); cam.disconnect()
" 2>&1 | tail -4
```
**期望**：两行 `shape= (480, 640, 3)`。

### 5-3 抓 3 张图确认视角

```bash
mkdir -p /tmp/camcheck
for p in video0 video2 video4; do
  v4l2-ctl -d /dev/$p \
    --set-fmt-video=width=640,height=480,pixelformat=MJPG \
    --stream-mmap=3 --stream-count=1 --stream-to=/tmp/camcheck/$p.jpg 2>/dev/null
done
ls -l /tmp/camcheck/
```

拉回 PC 查看：`scp pi5@<Pi_IP>:/tmp/camcheck/*.jpg ./`

**要回答**：每台分别看到什么（正前方？背后？桌面？），以及有没有上下颠倒 / 左右镜像。

### 5-4 改相机配置（依据 5-3 的结果决定键名）

编辑 `src/lerobot/robots/alohamini/config_alohamini.py` 的 `alohamini_cameras_config()`：
- 设备路径改成 5-2 建好的 symlink
- 加上 `fourcc="MJPG"`
- 按实际视角定键名
- **改完必须重启 Host 才生效**

---

## 6. 真机验证结果（2026-10-29）

四个新脚本一次性 SCP 到 Pi 上跑完，结果如下。

| 脚本 | 结果 | 关键输出 |
|---|---|---|
| `base_pulse.py` | ✅ **通过** | 6 个动作的 raw 全部对上离线模型；电流 0–695.5 mA，未触发 1000 mA 保护；退出码 0 |
| `arms.py`（read 模式） | ✅ **通过** | 「已标定（存在非零 Homing_Offset）」；6 个关节电流全 0.0 mA |
| `cameras.py` | ❌ **失败（环境问题）** | `ModuleNotFoundError: No module named 'lerobot.robots.alohamini.config_alohamini'` |
| `lift.py` | ❌ **失败（环境问题）** | `TypeError: LiftAxisConfig.__init__() got an unexpected keyword argument 'descent_floor_mm'` |

> 两个失败项**与脚本本身无关**，是 Pi 上装的 `lerobot` 版本过旧 → 见 §6.2。

### 6.1 底盘：已通过，运动学模型被电流独立验证

实测 raw 与离线模型的逐项比对（顺序 = `base_left_wheel` / `base_back_wheel` / `base_right_wheel`）：

| 动作 | 离线预测 raw | 真机实测 raw | 一致 |
|---|---|---|---|
| fwd | 2258 / 0 / -2258 | 同左 | ✅ |
| back | -2258 / 0 / 2258 | 同左 | ✅ |
| left | -1304 / 2608 / -1304 | 同左 | ✅ |
| right | 1304 / -2608 / 1304 | 同左 | ✅ |
| rotl | 2276 / 2276 / 2276 | 同左 | ✅ |
| rotr | -2276 / -2276 / -2276 | 同左 | ✅ |

**最有价值的一条证据**：`fwd` / `back` 两步里 `base_back_wheel` 的电流**恰好 0.0 mA**，
而 `left`/`right`/`rotl`/`rotr` 四步它都有电流。

这不是 bug，是运动学决定的：三轮的滚动方向分别是 150° / -90° / 30°，
前后移动时中间那个轮的滚动方向垂直于运动方向，它不需要转（omni 轮可自由侧滑）；
横移时它才成为主力（raw 2608 = 侧轮 1304 的两倍，正好是 |sin 90°| : |sin 30°| = 1 : 0.5）。

→ **电流读数独立验证了运动学模型正确**，同时证明 `base_back_wheel`（ID 9）接线正常、ID 没错。

**唯一留意点**：`right` 那步 `base_back_wheel` 冲到 **695.5 mA**，是全程最高
（STS3215 额定 900 mA，脚本阈值 1000 mA）。下次跑留意这个值是否稳定在 700 附近。

### 6.2 两个失败项：同一个根因 —— Pi 上的 lerobot 版本过旧

三个时间点对上：

| 事件 | 日期 | 提交 |
|---|---|---|
| `lift_axis.py` 引入 | 2025-10-24 | `c3c9229a` |
| `descent_floor_mm` 加入 `LiftAxisConfig` | 2026-04-11 | `d0a48229` |
| `config_lekiwi.py` → `config_alohamini.py` 改名 | 2026-07-11 | `db74a060` |

Pi 上的版本：**既有** `lift_axis.py`（所以 import 成功、报错发生在构造 config 时）、
**没有** `descent_floor_mm`、**没有** `config_alohamini.py`
→ 唯一解是 **2026-04-11 之前的版本**。

**诊断**（先跑这个，区分「仓库旧」还是「装的旧」）：

```bash
python -c "import lerobot, lerobot.robots.alohamini as m; print(lerobot.__file__); print(m.__file__)"
cd ~/lerobot_alohamini && git log --oneline -1 && git status -sb && ls src/lerobot/robots/alohamini/
```

**修复**（完整步骤见 **§1.1**，含重建 3.12 环境）：

```bash
cd ~/lerobot_alohamini
git pull
pip install -e .      # 若不是 editable 安装，必须重装
```

> ⚠️ 2026-07-11 那次重构改了模块名（`lekiwi*` → `alohamini*`）。
> 若 Pi 上旧版连 `python -m lerobot.robots.alohamini.alohamini_host` 都跑不了，
> 说明 site-packages 里装的是另一份旧代码 —— 光 `git pull` 不够，必须 `pip install -e .` 覆盖。

**修复后重跑**：

```bash
python examples/debug/cameras.py
python examples/debug/lift.py --port /dev/am_arm_follower_left --heights 0,80,200,80,10
```

#### ✅ 修复已验证（2026-10-29）

Pi 上重建 3.12 环境 + `git pull` + `pip install -e .`（清华镜像源）之后，两条导入链验证都通过：

```text
$ python -c "from lerobot.robots.alohamini.lift_axis import LiftAxisConfig; \
             print('descent_floor_mm' in LiftAxisConfig.__dataclass_fields__)"
True
$ python -c "from lerobot.robots.alohamini.config_alohamini import alohamini_cameras_config; \
             print(list(alohamini_cameras_config()))"
['head_front', 'head_top']
```

→ **§6.2 的版本根因已消除**，`cameras.py` / `lift.py` 的两个报错不再是阻塞。
剩下要做的就是跑脚本本身，确认真机行为（见 §6.4 的 #6）。

> ℹ️ `alohamini_cameras_config()` 返回两个相机名 `head_front` / `head_top`，
> 说明 Pi 上的 `config_alohamini.py` 已是 2026-07-11 改名后的版本。

#### ⚠️ 还没同步的第二个文件：`lift_axis.py`（**跑 `lift.py` 前必看**）

`src/lerobot/robots/alohamini/lift_axis.py` 在 PC 工作区有**未提交**的改动
（`git status` 显示 ` M`）。**`git pull` 不会带未提交的改动**，所以 Pi 上现在还是旧版。

旧版与新版的三处差别：

| # | 旧版（Pi 现状） | 新版（PC 工作区） | 影响 |
|---|---|---|---|
| 1 | `home()` 结尾的 `Goal_Velocity=0` 是**注释掉的** | 实际写入 | ⚠️ **安全项**：速度指令存在 SRAM 里，关力矩不解锁；`lift.py` 随后 `enable_torque()` 重新使能时，电机立刻按锁存的 1300 ticks/s 继续往下顶，直接撞硬限位 |
| 2 | homing 的"是否在动"判定用单帧阈值 `>10 ticks` | 改成 300 ms 窗口内 `>4 ticks` | 抗抖动，避免提前误判停机 |
| 3 | 无 homing 诊断量 | 新增 `home_travel_mm` / `home_springback_mm` / `home_stall_ma` / `home_stopped_by` | 30 s 没到底时会**显式告警**"0 mm 参考点不可信"；旧版是静默超时 |

**Pi 上先确认是不是旧版**：

```bash
cd ~/lxy_ws/lerobot_alohamini
grep -n 'Goal_Velocity", name, 0' src/lerobot/robots/alohamini/lift_axis.py
grep -c 'home_travel_mm' src/lerobot/robots/alohamini/lift_axis.py
```

- 第一条输出**带 `#` 开头**（`#self._bus.write(...)`）→ 旧版
- 第二条输出 `0` → 旧版

**同步方式**（在 PC 上执行，Pi 不用重新 `pip install -e .`，因为是 editable 安装）：

```bash
scp src/lerobot/robots/alohamini/lift_axis.py \
    pi5@10.168.1.110:~/lxy_ws/lerobot_alohamini/src/lerobot/robots/alohamini/lift_axis.py
```

> ⚠️ 跑 `lift.py` 的 homing 之前，**确保这条同步做了**。
> homing 是**有机械运动**的：1300 ticks/s ≈ 26.7 mm/s，最长 30 s。

### 6.3 从臂：标定生效，但有三处要判读

**(a) 标定已生效** ✅

```
标定状态: 已标定（存在非零 Homing_Offset）。
```

EEPROM 的 `Homing_Offset` 非零 → 标定确实写进去了。⚠️ **本次只测了左臂**（右臂在 `/dev/am_arm_follower_right`）。

**(b) 电流全 0.0 mA → 力矩是关的**

`arms.py --mode read` 既不禁用也不使能力矩（纯只读），所以 0 mA 说明**当前力矩本来就是关的**。
这与标定流程一致（标定必须 `disable_torque()`，脚本结束不重新使能）。

→ **机械臂现在没有力矩保持，会往下塌。**
→ 实测印证了 `alohamini.py:545` / `:567` 两条 `enable_torque()` 被注释掉的问题
（`configure()` 调了 `disable_torque()`，`alohamini_host.py:217` 只 `robot.connect()`，从不重新使能）
→ **这是「启动 Host → 遥操作验收」的阻塞项。**

**(c) EEPROM 限位有两处和当前代码对不上**

这些限位就是机器人自己算关节角用的 `range_min` / `range_max`
（`feetech.py:write_calibration` 把它们同时写进 EEPROM 和标定 JSON）：

| 关节 | EEPROM 限位 | 对应角度 | 判读 |
|---|---|---|---|
| shoulder_pan | [807, 3558] | ±120.9° | 正常 ROM |
| shoulder_lift | **[0, 4095]** | **±180°** | ⚠️ 整圈量程 |
| elbow_flex | **[0, 4095]** | **±180°** | ⚠️ 整圈量程 |
| wrist_flex | [2031, 4087] | ±90.4° | 正常 ROM |
| wrist_roll | [27, 3874] | ±169.1° | ⚠️ 当前代码应强制写 [0, 4095] |
| gripper | [1976, 3464] | ±65.4° | 正常 ROM |

两条线索指向同一结论：

1. `shoulder_lift` / `elbow_flex` 记成整圈（0..4095 = 一整转）→ 机器人认为这俩能转 ±180°；
2. `wrist_roll` 按**当前**标定代码应被强制写成 [0, 4095]，EEPROM 里却是 [27, 3874]
   → **EEPROM 是旧版标定代码写的**（与 §6.2 的「Pi 上是旧版」完全吻合）。

**风险**：机器人的位置限位和角度换算直接来自这些数字，±180° 的行程比真实机械行程宽得多
→ 遥操作时可能撞机械限位。

`deg` 列读数就是机器人自己算的关节角（公式与 `motors_bus._normalize` 的 DEGREES 分支一致），
可直接使用。夹爪 `开合 = 4.9%` 说明当前接近闭合姿态。

### 6.4 还需要确认的信息

**P0 —— 阻塞下一步**

| # | 要确认什么 | 怎么查 |
|---|---|---|
| 1 | ~~Pi 上 lerobot 的**实际版本 + 导入路径**~~ | ✅ **已确认**（2026-10-29）：`descent_floor_mm` 存在 + `config_alohamini` 可导入 → 装的版本 ≥ 2026-07-11，根因已消除（§6.2） |
| 2 | **标定 JSON 与 EEPROM 是否一致** | `cat ~/.cache/huggingface/lerobot/calibration/robots/*/alohamini1.json` —— 看 `shoulder_lift`/`elbow_flex` 的 `range_min`/`range_max` 是不是 0/4095，`wrist_roll` 是不是 0/4095 |
| 3 | `shoulder_lift` / `elbow_flex` 的**真实机械行程** | 人工转到底，确认实际能转多少度。EEPROM 说 ±180° 明显可疑 |
| 4 | Host 启动后**力矩是否被使能** | 代码层面：`alohamini.py:545`/`:567` 的 `enable_torque()` 被注释，需要先决定怎么修 |
| 5 | ~~**PC 与 Pi 的 `git rev-parse HEAD` 是否一致**~~ | ✅ **已确认等价**（2026-10-29）：Pi `2a1051b2` / PC `d4d1dd1d`，两者**树对象 hash 相同**（`00475ebd...`）→ 中间 4 个 commit 是「fix + 立刻 revert」和「docs + 立刻 revert」，净效果为零。**已提交代码两端 100% 一致** |

**P1 —— 本轮补齐**

| # | 要确认什么 | 怎么查 |
|---|---|---|
| 6 | **右臂是否也标定过** | 本次只测了左臂。右臂在 `/dev/am_arm_follower_right` |
| 7 | `cameras.py` 与 `lift.py` 的真实输出 | 环境阻塞已解除（§6.2），直接跑脚本 |
| 8 | 相机视角 / 上下颠倒 / 左右镜像 | ⏳ **仍待** —— `cameras.py` 已验证能出图（§6.5），但**没存 PNG**，视角要靠 `python examples/debug/cameras.py --camera head_top --save-dir /tmp/cam_frames --frames 10` 再抓一次 |
| 9 | PC 端 Leader 臂的型号与 ID | 决定 `--teleop.id` 和 `--teleop.arm_profile` |

> **关于重新标定**：若 #2 / #3 确认 EEPROM 限位过宽，
> 建议 **更新代码后重做一次从臂标定** —— 让 EEPROM 和标定 JSON 都由当前代码写出。
> 这是一次纯物理操作（断力矩、手动过一遍 ROM），和之前做过的流程一样。

### 6.5 相机：两台全部通过（2026-10-29 真机）

```text
$ python examples/debug/cameras.py
=== head_front ===
  设备路径 : /dev/am_camera_head_front
  fourcc   : 请求 MJPG，实际 MJPG
  分辨率   : 采集 640x480（请求 640x480）
  曝光/增益: exposure=157.0  gain=0.0
  实测 FPS : 30.1（91 帧 / 3.02 s，请求 30）
  画面统计 : mean=150.4 std=56.4  RGB=(142.9, 153.7, 154.5)
  结论     : OK

=== head_top ===
  设备路径 : /dev/am_camera_head_top
  fourcc   : 请求 MJPG，实际 MJPG
  分辨率   : 采集 640x480（请求 640x480）
  曝光/增益: exposure=157.0  gain=0.0
  实测 FPS : 30.0（90 帧 / 3.00 s，请求 30）
  画面统计 : mean=144.7 std=55.3  RGB=(132.7, 147.5, 153.8)
  结论     : OK
```

逐条对照验收标准：

| 验收点 | head_front | head_top | 判定 |
|---|---|---|---|
| fourcc 实际 = `MJPG` | MJPG | MJPG | ✅ |
| 分辨率 = 640×480 | 640×480 | 640×480 | ✅ |
| 实测 FPS ≈ 30 | 30.1 | 30.0 | ✅ |
| 画面 `mean` ∈ 20–200 | 150.4 | 144.7 | ✅ |
| 画面 `std` ≤ 60 | 56.4 | 55.3 | ✅ |

**意义**：① udev 别名（§5-1 厂商预装）**可用**，不需要新建规则；
② `config_alohamini.py` 里的 `/dev/am_camera_head_front` / `/dev/am_camera_head_top`
在 Pi 上**能打开**，说明 §5-2 的配置同步真的到位了；
③ MJPG 协商成功 → USB 带宽压力降到几百 KB/s/台（对比 YUYV 的 ~18 MB/s）；
④ `std` 都在 56 左右且**明显不等于 0** → 拍到的是真实画面，不是伪节点的纯色/噪点。

⏳ **还差视角确认**（§6.4 #8）：这次没带 `--save-dir`，没存下 PNG。

#### 怎么在 PC 端看到画面（Pi 是 headless，存 PNG 后有 3 种看法）

`cameras.py --save-dir` 存的是 **PNG**，文件名 `{相机名}_{序号:03d}.png`（如 `head_top_000.png`）。

**方案 A —— Pi 起 HTTP 服务，PC 浏览器直接看（推荐，不用 scp）**

```bash
# Pi 上
python examples/debug/cameras.py --camera head_top --save-dir /tmp/cam_frames --frames 10
cd /tmp/cam_frames && python -m http.server 8000
```
PC 浏览器打开 **http://10.168.1.110:8000/** → 点图看大图，随时刷新。
Pi 上 `Ctrl-C` 停服务。

**方案 B —— scp 拉回 PC**
```bash
# PC 上
scp pi5@10.168.1.110:/tmp/cam_frames/*.png ./
```

**方案 C —— 实时预览（MJPEG 流，PC 浏览器看活视频）**

Pi 上放一个 `video.sh`（**不改动仓库**，放在哪都行）：
```bash
#!/usr/bin/env bash
# video.sh —— 把 Pi 上的 USB 相机以 MJPEG 流推到 PC 浏览器
#
# 用法:
#   ./video.sh                            # 默认 head_front，端口 8080
#   ./video.sh /dev/am_camera_head_top   # 换相机
#   ./video.sh /dev/am_camera_head_top 9000
#   ./video.sh --list                     # 列出本机实际存在的相机别名
#
# PC 端浏览器打开: http://<Pi_IP>:<端口>/
set -uo pipefail

list_cameras() {
  echo "本机存在的相机别名:"
  for d in /dev/am_camera_*; do
    [ -e "$d" ] && echo "  $d"
  done
  echo
  echo "不存在（udev 规则有但设备没接 / 规则本身就没有）:"
  for d in am_camera_wrist_left am_camera_wrist_right am_camera_forward; do
    [ -e "/dev/$d" ] || echo "  /dev/$d"
  done
}

if [ "${1:-}" = "--list" ]; then list_cameras; exit 0; fi

DEV="${1:-/dev/am_camera_head_front}"
PORT="${2:-8080}"
[ -e "$DEV" ] || { echo "设备不存在: $DEV"; list_cameras; exit 1; }

DEV="$DEV" PORT="$PORT" python3 - <<'PY'
import os, sys
import cv2
from http.server import BaseHTTPRequestHandler, HTTPServer

DEV = os.environ["DEV"]
PORT = int(os.environ["PORT"])

cap = cv2.VideoCapture(DEV)
if not cap.isOpened():
    sys.exit(f"打不开 {DEV}")
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                if not ok:
                    break
                self.wfile.write(
                    b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
                )
        except (BrokenPipeError, ConnectionResetError):
            pass  # 浏览器关了标签页，属正常

    def log_message(self, *args):
        pass


server = HTTPServer(("0.0.0.0", PORT), Handler)
print(f"streaming {DEV} -> http://0.0.0.0:{PORT}/   (Ctrl-C 停止)")
try:
    server.serve_forever()
except KeyboardInterrupt:
    print("\n已停止")
finally:
    cap.release()
    server.server_close()
PY
```
PC 浏览器打开 **http://10.168.1.110:8080/**。

> ℹ️ 方案 C 用的是裸 `cv2.VideoCapture`，它返回的是 **BGR**，直接编码成 JPEG 给浏览器就是对的
> （和 `cameras.py` 的情况相反 —— 后者走 `OpenCVCamera`，拿到的是 RGB，存盘前必须转 BGR）。
> ⚠️ 用 `HTTPServer`（单线程）→ **同一时刻只允许一个浏览器连接**；换第二个浏览器会一直转圈。
> 要多端同时看就改成 `ThreadingHTTPServer`，但 `cap` 需要加锁。

> ⚠️ 三个方案都监听 `0.0.0.0`（局域网内可访问）。**只在需要时开，用完 `Ctrl-C` 停掉。**

### 6.6 ✅ Pi 磁盘满：`conda env rename` 失败 → 已解决（2026-10-29）

> **已解决**：清理 + 改名都成功了。证据是随后脚本的 traceback 路径：
> `/home/pi5/miniconda3/envs/lerobot_alohamini/lib/python3.12/`
> → 环境名已是 `lerobot_alohamini`（与 PC 端同名），Python 是 3.12。

<details>
<summary>原始故障记录（已解决，保留备查）</summary>

```text
$ conda rename -n lerobot_alohamini lerobot_alohamini_310
Source:      /home/pi5/miniconda3/envs/lerobot_alohamini
Destination: /home/pi5/miniconda3/envs/lerobot_alohamini_310
Packages: 59
Files: 92330
NoSpaceLeftError: No space left on devices.
```

**根因**：磁盘剩余空间 < 一个完整环境的体积（59 个包 / 92330 个文件）。
`conda env rename` 是**先复制再删源**（环境里有绝对路径，改名要重写路径，
不能靠 `rename(2)` 原子改名），所以需要**临时再放一份**。

**空间被谁吃掉的**（2026-10-29 实测 `du`，根分区 29 G，已用 28 G，**只剩 24 K**）：

| 目录 | 实测 | 性质 | 处理 |
|---|---|---|---|
| `~/.cache/pip` | **4.6 G** | `pip install -e .` 下载的 torch / torchvision / opencv / numpy wheel | 全删（纯缓存）|
| `~/miniconda3/envs/lerobot_alohamini` | **4.3 G** | **旧的 3.10 环境**，连 `import lerobot` 都做不到 | 全删 |
| `~/miniconda3/envs/lerobot_alohamini_310` | **2.3 G** | 改名失败留下的半成品 | 全删（垃圾）|
| `~/miniconda3/pkgs` | **1.7 G** | conda-forge 包的 tarball + 提取副本 | `conda clean -a -y` |
| `~/miniconda3/envs/lerobot_alohamini_312` | 4.9 G | **当前在用的 3.12 环境** | ❌ 不能动 |
| `~/.cache/huggingface` | 60 K | 标定 JSON 等 | ❌ 不能动 |

合计可回收 **≈ 12.9 G** → 磁盘从 100%（24 K）回到约 13 G 空闲。

> ⚠️ **清理顺序有讲究**：磁盘只剩 24 K 时，`pip cache purge` / `conda clean` 这类
> 需要写临时文件或事务日志的命令**自己就可能失败**。
> 所以先跑**纯删除**（`rm -rf`）回收空间，再跑 conda 命令。

**修复顺序**（先腾空间，再改名；否则 rename 还是会 ENOSPC）：

```bash
# 0. 先花 10 秒确认三件事（删 4.3 G 之前值得看一眼）
conda env list
~/miniconda3/envs/lerobot_alohamini/bin/python -V        # 期望 Python 3.10.x
~/miniconda3/envs/lerobot_alohamini_312/bin/python -V     # 期望 Python 3.12.x

# 1. 先删改名失败留下的半成品（+2.3 G，纯 rm，不需要写任何东西）
rm -rf ~/miniconda3/envs/lerobot_alohamini_310

# 2. 删旧 3.10 环境（+4.3 G；此时已有 2.3 G 空闲，conda 能写事务日志）
conda env remove -n lerobot_alohamini -y || rm -rf ~/miniconda3/envs/lerobot_alohamini

# 3. 清 pip 缓存（+4.6 G）
rm -rf ~/.cache/pip          # 等价于 pip cache purge，但满盘时更不容易失败

# 4. 清 conda 包缓存（+1.7 G）
conda clean -a -y

# 5. 复核
df -h /                     # 期望 Avail ≈ 13 G
```

**改名（可选，最后做）**：此时约 13 G 空闲，复制 4.9 G 的环境够用。

```bash
conda env rename -n lerobot_alohamini_312 lerobot_alohamini
```

> 若第 2 步走了 `rm -rf` 兜底，`~/.conda/environments.txt` 会留一条失效记录，
> `conda env list` 里显示为失效环境 —— 不影响使用，`conda env remove` 能清掉。

> 💡 **改名不是必须的**。§1.1 的表格里 conda env 名字一栏写的是
> 「建议一致（文档可读性，非技术必需）」——两端是两个独立进程，只通过 ZMQ 传字节。
> 如果改名仍失败，**继续用 `lerobot_alohamini_312` 即可**，只需在文档里把 PC 端的名字对齐。

> ⚠️ **磁盘满会连累别的操作**：SCP 同步 `lift_axis.py`、pip 安装、任何写文件的动作都可能失败。
> 所以 **§6.2 的 SCP 必须放在清完空间之后**。

</details>

---

### 6.7 升降：homing 与高度闭环均通过（2026-10-29 真机）

**结论：`lift.py` 跑通，且三条关键结论被独立验证——homing 生效、丝杠换算 `84 mm/转` 正确、速度上限 `v_max=1300` 正确。**
同时也暴露 2 个待确认点：① homing 行程只有 2.7 mm；② `--dwell 5.0` 对 200 mm 目标偏紧。

> 这次输出也**顺带证明了 `lift_axis.py` 已同步到 Pi**：新加的 4 个诊断量
> （`home_travel_mm` / `home_springback_mm` / `home_stall_ma` / `home_stopped_by`）
> 全部打印出来了 —— 旧版没有这些字段（见 §6.2）。

**homing 逐行判读**

| 观测 | 数值 | 判读 |
|---|---|---|
| `Present_Position` 变化 | 2894 → 2916 → 2961 → 2997 → 3024 ticks（+130） | 下行方向 tick 增大 ⇒ `dir_sign=-1` ✅ |
| 电流爬升 | 32.5 → 71.5 → 227.5 → 585.0 → **1176.5 mA** | 一路顶到硬限位；`home_stall_current_ma=300` 在 585 mA 时越过 |
| 停机原因 | `Stalled at current=1176.5 mA, moved=True` | 连续 2 次采样越限 ⇒ `home_stopped_by="current"` ✅ |
| 下行行程 | **2.7 mm** | ⚠️ 行程极短 ⇒ **启动时升降台已经在底部**，2.7 mm 只是顶住限位时的传动件弹性变形 |
| 释放力矩后回弹 | 2.6 mm | 负载把台面推回 2.6 mm ⇒ **0 mm 参考点比机械底限高 2.6 mm**（设计如此） |
| 净位移 | `Extended ticks after homing: 4.0`，`z0_deg=-0.35` | 下行 130 tick、回弹 126 tick，净值 ≈ 4 tick（0.35°）——与上两行自洽 ✅ |
| homing 用时 | 1.3 s | 含释放力矩后的 1 s 等待 |

**运动学交叉验证**（用高度序列反推，与理论值逐位吻合）

| 项 | 实测 | 理论 | 结论 |
|---|---|---|---|
| 换算率 | 7.1 mm ÷ 346 tick = **0.020520 mm/tick** | 84 mm/转 ÷ 4096 tick/转 = **0.020508 mm/tick** | ✅ `lead_mm_per_rev=84` 正确 |
| 上升速度 | 7.1 mm ÷ 0.25 s ≈ **28.4 mm/s** | `v_max=1300` tick/s × 0.020508 = **26.7 mm/s** | ✅ 速度闭环顶在 `v_max` 上 |
| 方向 | 高度 ↑ ⇒ ticks ↓（2684 → 2338 → 1993 → 1649） | `dir_sign=-1` | ✅ |
| 负载电流 | 117.0 – 136.5 mA（空载上升） | STS3215 额定 900 mA | ✅ 无卡滞 |

**另外两处行为正确**：
- 目标 `0.0 mm` 被下行保护拦截并标注「已跳过」✅（§1.1 的 `descent_floor_mm=5.0` 生效）
- homing 结束释放力矩后**重新使能没有把台面甩向硬限位** ✅ —— 这正是工作区里 `Goal_Velocity=0` 那处修复的作用（`Goal_Velocity` 是 SRAM，关力矩不会清零；不写 0 的话重新使能就会冲向限位）

**⏳ 两个待确认点**

1. **homing 行程只有 2.7 mm ⇒ 起点就在底部**，`soft_max_mm=600` 的上端**从未验证过**。
   机械实际行程上限未知，建议逐级试探并盯电流（空载 ~130 mA；一旦升到 500 mA 以上就是快到顶了）。
2. **`--dwell 5.0` 对 200 mm 目标偏紧**：80 → 200 mm = 120 mm ÷ 27 mm/s ≈ **4.4 s**，只剩 0.6 s 余量，
   脚本会误报「超时，未到位」而台面其实还在正常上升。**下一轮必须加大 dwell。**

---

#### 第二次运行（`--dwell 10`，完整高度序列）—— **全部通过**

```bash
python examples/debug/lift.py \
  --port /dev/am_arm_follower_left \
  --heights 0,80,200,300,80,10 \
  --dwell 10 \
  --current-cutoff 1000
```

**5 个目标全部「已到位」**（0 mm 被下行保护按预期跳过）：

| 目标 | 实测终点 | 耗时 | 到位时电流 | 结论 |
|---|---|---|---|---|
| 80 mm | 79.2 mm | ~2.9 s | 52.0 mA | ✅ |
| 200 mm | 199.5 mm | ~4.4 s | 52.0 mA | ✅ |
| **300 mm** | **299.6 mm** | ~3.7 s | 39.0 mA | ✅ **机械行程 ≥ 300 mm，全程电流 ≤ 143 mA，无卡滞** |
| 80 mm（下降） | 80.4 mm | ~8.1 s | 0.0 mA | ✅ |
| 10 mm | 10.3 mm | ~2.7 s | 0.0 mA | ✅ 下行地板 5 mm 保护未误触发 |

**这次最有价值的验证：单圈计数回绕（tick 0/4095 边界）被真实走过了 3 次**

| 场景 | 刻度穿越 | 高度读数 | 结论 |
|---|---|---|---|
| 上升 53.9 → 61.1 mm | ticks 266 → 4012（向上绕） | 连续无跳变 | ✅ |
| 上升 68.1 → 75.2 mm | ticks 4012 → 3668（回绕后继续） | 连续无跳变 | ✅ |
| 下降 232.6 → 225.5 mm | ticks 3844 → 95（向下绕） | 连续无跳变 | ✅ |

> `_update_extended_ticks()` 的 ±2048 半圈修正逻辑是对的。
> 之前 0–80 mm 的测试根本没跨过边界，**这一项一直是未验证状态**；现在有了真机证据。

**两次运行的 homing 一致性**（互相印证）

| | 第 1 次 | 第 2 次 |
|---|---|---|
| 起始 tick | 2894 | 2941 |
| 下行 tick | +130 | +77 |
| 下行行程 | 2.7 mm | **1.6 mm** |
| 回弹 | 2.6 mm | 2.5 mm |
| 堵转电流 | 1176.5 mA | 1131.0 mA |
| 净位移 `z0_deg` | −0.35° | +3.87° |

两次都只走了 1–3 mm 就撞到硬限位 ⇒ **升降台在两次运行开始时都已经停在底部**，不是偶发。

**⚠️ 由此得出 3 条新的待办**

1. **机械行程上限仍未知（已确认 ≥ 300 mm，`soft_max_mm=600` 未验证）**
   若真实上限低于 600 mm，Host 下发 600 mm 的目标会像 homing 一样**顶死在上限硬限位**。
   目标循环有 `--current-cutoff` 兜底（会触发停机），但仍应先探出真实上限。

2. **下降段电流恒为 0（上升段 117–156 mA）—— 下降方向没有负载反馈**
   300 → 80 mm 整段下降，30+ 次采样电流全是 `0.0 mA`（偶发 6.5 mA）；10 mm 段同样全 0。
   与此同时**下降速度与上升完全相同**（都是 345 tick/采样间隔），说明**伺服确实按指令速度在控速，不是自由落体**。
   两种可能：
   - (a) 台面靠重力下行，伺服只做微调 → 电流本来就很小（< 6.5 mA 分辨率），**但意味着速度环没在真正控速**；
   - (b) 该固件在这个方向不报告电流 → 读数不可用。

   **两种情况的共同后果：`--current-cutoff` 在下降方向是瞎的** —— 下降途中卡死不会触发保护。
   判定方法见下面「诊断下降段电流」。

3. **homing 堵转电流 1131 mA = 额定值的 1.26 倍**（STS3215 额定 900 mA / 持续 2700 mA）。
   `home_stall_current_ma=300` 越过阈值后还要再确认 1 个采样（100 ms）才停，所以冲到 1131 mA。
   时间很短、可接受，但**homing 不受 `--current-cutoff` 保护**（那是目标循环的阈值），要压低只能调 `home_stall_current_ma`。

**诊断下降段电流（`lift.py` 已加 `--show-registers`）**

```bash
python examples/debug/lift.py \
  --port /dev/am_arm_follower_left \
  --heights 300,80 --dwell 15 --show-registers
```
会多打两列：`实际速度`（`Present_Velocity`，tick/s）与 `负载`（`Present_Load`）。
- 若 `实际速度` ≈ ±1300 ⇒ 伺服在控速，而 `Present_Current` 在该方向不反映负载 ⇒ 情况 (b)，**功能正常但缺负载反馈**；
- 若 `实际速度` ≈ 0 或明显偏离 ⇒ 伺服没在控速，下行是重力驱动 ⇒ 情况 (a)，**这是真问题，Host 遥操作前必须解决**。

> ℹ️ `--show-registers` 默认关闭：每多读一个寄存器都会拉长控制循环周期、改变打印间隔，
> 进而改变「每采样多少 tick」的换算基准。关闭时循环时序与前两次运行完全一致，数据可直接对比。

**下一轮建议命令（探机械行程上限）**

```bash
python examples/debug/lift.py \
  --port /dev/am_arm_follower_left \
  --heights 0,400,500 --dwell 20 --show-registers
```
- `--dwell 20`：0 → 500 mm 需要 500 ÷ 27 ≈ 18.5 s
- **电流一旦升到 400–500 mA 就说明快到顶了**，把那个高度记下来
- 建议同时带 `--show-registers`，顺便把下降段的电流问题一起看清

---

### 6.8 从臂 `jog`：使能瞬间的跳变隐患（已修）

**问题**：`arms.py --mode jog` 走 `open_bus(..., enable_torque=True)`，会**一次性使能整条手臂的 6 个关节**，
但只给被点动的那个关节写新的 `Goal_Position`。

Feetech 在**位置模式**下是伺服到 `Goal_Position` 寄存器走，而该寄存器是 **SRAM**、保留上次写入的旧值；
`enable_torque()` 本身只写 `Torque_Enable=1` 和 `Lock=1`（`feetech.py:302-305`），**不碰 `Goal_Position`**。
→ 使能瞬间，其余 5 个关节会朝**陈旧目标**（常常是出厂值）猛跳。

**这个隐患在 AlohaMini 上比上游更严重**：从臂标定时手写入了 `Homing_Offset`，
`Present_Position` 的坐标系因此变了，而 `Goal_Position` 里存的还是**标定前**那个坐标系下的旧值。

**上游怎么处理的**：`so_follower.py` 是同样的顺序（先 `torque_disabled()` 上下文退出时使能，再由 `send_action` 写 `Goal_Position`），
靠 `ensure_safe_goal_position(goal_present_pos, max_relative_target)` 限幅兜底。
但 `max_relative_target` 在**全仓库默认值都是 `None`**（`config_alohamini.py:76`、`config_so_follower.py:36` 等），
也就是这层保护默认不生效 —— 属上游惯例，不是 AlohaMini 的漏项。

**已做的修复**（`examples/debug/`，纯脚本层，不碰 Host 主链路）

| 文件 | 改动 |
|---|---|
| `examples/debug/_common.py` | `open_bus()` 新增 `sync_goal_positions: bool = False`；为 `True` 时，在 `enable_torque()` **之前**把每个电机的 `Present_Position` 写进 `Goal_Position` |
| `examples/debug/arms.py` | `jog` 模式传 `sync_goal_positions=True`；修正了原来那句错误注释（「没被点动的关节会保持当前位置」） |

效果：使能后 6 个关节**原地保持**，只有被点动的关节按 `--delta-deg` 移动。

> ℹ️ AlohaMini 还有一层原生兜底：`alohamini.py:527/533` 给手臂写了 Feetech 原生运动档案
> （`Goal_Velocity=2000` tick/s ≈ 176°/s、`Acceleration=100`），
> 所以即使目标很离谱，物理速度也被限住 —— 但 176°/s 对机械臂仍然很快，**不能**当成安全保证。

**跑 `jog` 的建议顺序**（先小后大）：

```bash
# 1) 先 read，确认标定状态和限位（不动）
python examples/debug/arms.py --port /dev/am_arm_follower_left --arm left --mode read

# 2) 点动一个关节，小角度
python examples/debug/arms.py --port /dev/am_arm_follower_left --arm left \
  --mode jog --joint shoulder_pan --delta-deg 5
```

---

## 7. 后续阶段命令（`alohamini1` 版，已填好）

### 从臂标定（树莓派，**必须在启动 Host 之前**）

```bash
python -m lerobot.robots.alohamini.alohamini_calibrate --robot_model alohamini1
```
流程：左臂摆机械中位 → 回车 → 转过完整 ROM → 回车；右臂同理。
脚本结束会自动执行**升降轴回零**（输出 `Lift axis homed to 0mm.`）。
⚠️ **标定后给双臂断电重启**。

### 底盘 / 升降单独测试（树莓派）

> 前置：**Host 必须已停**。调试脚本与 Host 争用同一个串口 `/dev/am_arm_follower_left`。

底盘（✅ **已通过**，2026-10-28 首测，2026-10-29 复测确认，见 §6.1）：

```bash
python examples/debug/base_pulse.py \
  --port /dev/am_arm_follower_left \
  --steps fwd:1,back:1,left:1,right:1,rotl:1,rotr:1
```
> `wheels.py` 依赖 pynput 抓键盘，在树莓派上曾因无 X11 而收不到按键；
> 最终用**固定动作序列**（前进/后退/横移/旋转各 1 s，直接写 `Goal_Velocity`）验证通过。
> 该脚本已固化为 `examples/debug/base_pulse.py`（不依赖键盘，SSH 可跑）。
>
> **调速**：`--lin-speed`（m/s，默认 0.2）/ `--ang-speed`（deg/s，默认 80）。
> 注意 `MAX_RAW = 3000` 的削峰：平移 > 0.2301 m/s、旋转 > 105.5 deg/s 后
> **实际速度不再增加**（脚本会打印 `raw=3000` 提示顶到上限），要更快需同时改 `MAX_RAW`。

升降台（⏳ **待跑**，2026-10-29 环境阻塞已解除，见 §6.2）：

```bash
python examples/debug/lift.py --port /dev/am_arm_follower_left --heights 0,80,200,80,10
```

`lift.py`（`examples/debug/lift.py`）复用仓库自带的 `LiftAxis`：

1. **homing** —— 下行到底部硬限位，触底位置置为 0 mm，打印**下行行程**与**释放力矩后的回弹量**；
2. **高度序列** —— 按 mm 目标闭环运动，逐步打印 目标/实测高度、ticks、电流；
3. 过流保护（默认 1000 mA 触发即停），结束时关闭力矩。

**首次运行的实测结论（2026-10-28）**：

| 现象 | 结论 |
|---|---|
| `AttributeError: 'LiftAxis' object has no attribute 'stop'` | 树莓派上的仓库代码比 PC 旧，`LiftAxis.stop()` 是 2026-06-19 之后才加的。**必须先 `git pull` 同步**（脚本已加兼容回退，但同步才是正解） |
| 旧脚本打印"实际行程 0.0 mm / 升降台没动" | **误报**：homing 之前没有高度基准，`get_height_mm()` 恒为 0。现改为打印真实下行行程 |
| ticks 2914 → 2990 后停在 500 mA | 电机确实下压到硬限位。76 ticks × (84 mm / 4096 ticks) = **1.56 mm**，说明启动时升降台**已经在底部** |
| homing 后 `Extended ticks = -21`、z0_deg = 1.85 | `home()` 释放力矩后有 1 s 空窗，轴在负载下**回弹 97 ticks ≈ 2.0 mm**，所以 0 mm 参考点比机械底限高约 2 mm |

> ⚠️ 旧脚本 `examples/debug/axis.py` **已删除**：它硬编码 `sts3215` + `RANGE_0_100`
> （真实配置是 `DEGREES`），没有 homing、也没有 mm 闭环，而且退出时断连逻辑与力矩策略
> 相互矛盾（有 `NameError` 风险）。统一用 `lift.py`。

### 相机 / 从臂单独测试（树莓派，2026-10-28 新增脚本）

> 2026-10-29 实测：`arms.py`（read 模式）✅ 通过；`cameras.py` / `lift.py` 的版本阻塞已解除（§6.2），待跑。

```bash
# 相机：测 fourcc / 帧率 / 曝光，并存几帧 PNG 确认视角
python examples/debug/cameras.py
python examples/debug/cameras.py --camera head_top --save-dir /tmp/cam_frames --frames 10

# 从臂：只读，看关节角 / EEPROM 限位 / 标定状态
python examples/debug/arms.py --port /dev/am_arm_follower_left --arm left

# 从臂：单关节点动
python examples/debug/arms.py --port /dev/am_arm_follower_left --arm left \
  --mode jog --joint shoulder_pan --delta-deg 5
```

| 脚本 | 覆盖 | 关键验收点 | 实测 |
|---|---|---|---|
| `cameras.py` | `head_front` + `head_top` | 实际 fourcc = `MJPG`（库里协商失败只 warning，必须自己读 `CAP_PROP_FOURCC` 复核）；实测 FPS ≈ 30；画面 `mean` 在 20–200、`std` ≤ 60（防伪节点噪点） | ✅ **两台全通过**（§6.5）；⏳ 视角待确认 |
| `arms.py` | 从臂 ID 1–6 | `read` 模式打印 ticks/角度/EEPROM 限位/电流；`Homing_Offset` 全 0 → 提示「尚未标定」；`jog` 只动指定关节且目标被夹在 EEPROM 限位内 | ✅ read 通过（§6.3）；⏳ jog 未跑 |

> 四个新脚本（`base_pulse.py` / `lift.py` / `arms.py` / `cameras.py`）共用
> `examples/debug/_common.py` 的总线生命周期与过流保护，退出码统一为
> `0` = 通过 / `1` = 过流或异常 / `2` = 参数错误。

### 启动 Host（树莓派，常开终端）

```bash
python -m lerobot.robots.alohamini.alohamini_host \
  --robot_model alohamini1 --profile_timing
```
需要 ROS 相机流时加 `--camera-stream`（TCP 5557）。

### PC 端：主臂标定

```bash
python examples/alohamini/calibrate_bi.py \
  --teleop.id so101_leader_bi --teleop.arm_profile so-arm-5dof
```
（Leader 臂型号待确认；若 PC 上是 AM-ARM 6 自由度，改用 `--teleop.id am_leader_bi --teleop.arm_profile am-leader-6dof`）
⚠️ **标定后给 Leader 臂断电重启**。

### 遥操作验收（PC）

```bash
python examples/alohamini/teleoperate_bi.py \
  --robot.remote_ip <Pi_IP> \
  --robot.robot_model alohamini1 \
  --teleop.id so101_leader_bi --teleop.arm_profile so-arm-5dof \
  --fps 50 --camera-fps 30
```
键盘：`W/S` 前后 · `Z/X` 横移 · `A/D` 旋转 · `T/G` 调速 · `U/J` 升降 · `Q` 退出。

### 数据采集（PC）

```bash
# 先冒烟
python examples/alohamini/record_bi.py \
  --dataset.repo_id $HF_USER/am1_smoke_test --dataset.num_episodes 1 \
  --dataset.fps 10 --dataset.episode_time_s 10 --dataset.reset_time_s 3 \
  --dataset.single_task "smoke test" \
  --robot.remote_ip <Pi_IP> --robot.robot_model alohamini1 \
  --teleop.id so101_leader_bi --teleop.arm_profile so-arm-5dof

# 正式（多速率：50 Hz 控制 + 数据集频率采样新鲜帧）
python examples/alohamini/record_bi_multirate.py \
  --dataset.repo_id $HF_USER/am1_bi_test --dataset.num_episodes 50 \
  --dataset.fps 30 --dataset.episode_time_s 45 --dataset.reset_time_s 8 \
  --dataset.single_task "pickup1" \
  --robot.remote_ip <Pi_IP> --robot.robot_model alohamini1 \
  --teleop.id so101_leader_bi --teleop.arm_profile so-arm-5dof
```

---

## 8. 待办 / 风险备忘

**阻塞项（2026-10-29 新增）**

- [x] ~~**Pi 上的 `lerobot` 版本过旧**~~ —— ✅ **2026-10-29 已修复**：重建 3.12 环境 + `git pull` + `pip install -e .`（清华镜像源），`descent_floor_mm` 与 `config_alohamini` 均导入验证通过（§6.2）
- [x] ~~**Pi 的 Python 环境是 3.10，需重建为 3.12**~~ —— ✅ **2026-10-29 已重建为 3.12**（先建 `lerobot_alohamini_312`，验证通过后改名为 `lerobot_alohamini`，与 PC 同名；清华镜像源，完整步骤见 §1.1）
- [x] ~~**`lift_axis.py` 的未提交改动没同步到 Pi**~~ —— ✅ **2026-10-29 已同步并验证生效**：SCP 单文件后，Pi 上第 186 行已是生效的 `self._bus.write("Goal_Velocity", name, 0)`（旧版是第 134 行的注释版），`home_travel_mm` 计数 3。`lift.py` 真机跑通，4 个新诊断量全部打印（§6.7）—— **这是修复生效的直接证据**
- [x] ~~**Pi 磁盘满**~~ —— ✅ **2026-10-29 已解决**：清理后余量充足，`conda env rename` 也成功了（环境名现在是 `lerobot_alohamini`，Python 3.12，与 PC 同名）。原始数据与修复步骤见 §6.6
- [ ] ⚠️ **SD 卡容量会成为后续瓶颈** —— 29 G 的卡清完也只有 ~13 G 空闲，而数据采集（`lerobot-record`）写的是视频+parquet，几小时就能吃掉几个 G。做采集前先规划：换大容量卡 或 外接 SSD
- [x] ~~**PC 与 Pi 的 `lerobot` commit 是否一致未核对**~~ —— ✅ **2026-10-29 已核对，两端等价**：Pi `2a1051b2` / PC `d4d1dd1d` 的**树对象 hash 相同**（`00475ebd...`），中间的 4 个 commit 是「fix + 立刻 revert」「docs + 立刻 revert」，净效果为零。真正要同步的只有**未提交的工作区改动**，其中有运行时影响的只有 `lift_axis.py`（见上一条）
- [ ] **Host 路径的力矩未使能** —— `alohamini.py:545`/`:567` 的 `enable_torque()` 被注释，而 `configure()` 调了 `disable_torque()`；`alohamini_host.py:217` 只 `robot.connect()` 从不重新使能 → Host 起来后 `Goal_Position`/`Goal_Velocity` 不生效。**遥操作验收前必须解决**。
  ⚠️ **不能只把这两行注释解开**（2026-10-29 复核 `alohamini.py:configure()` 得出）—— `bus.enable_torque()` 不带参数会**使能左总线上的全部电机**，而此时三个寄存器的状态都不对：
  | 电机 | 使能瞬间会怎样 | 必须先做什么 |
  |---|---|---|
  | 手臂 6 关节（位置模式） | 朝 **SRAM 里陈旧的 `Goal_Position`** 走；标定改过 `Homing_Offset` 后这值坐标系还是旧的 → 猛冲（速度被原生档案限到 2000 tick/s ≈ 176°/s） | 先把 `Present_Position` 写进 `Goal_Position`（与 `examples/debug/_common.py` 的 `sync_goal_positions` 同一手法，见 §6.8） |
  | 底盘 3 轮（速度模式，`alohamini.py:541` 已写 `Operating_Mode=VELOCITY`） | 朝**陈旧的 `Goal_Velocity`** 转 → 底盘自己跑掉 | 先写 `Goal_Velocity=0` |
  | 升降（`# self.lift.configure()` 也被注释，`alohamini.py:567`） | 若仍在**出厂默认的位置模式** → 朝陈旧 `Goal_Position` 撞到底 | 先 `lift.configure()`（切速度模式）并写 `Goal_Velocity=0` |

  建议改法：`configure()` 末尾按电机类别分别处理（手臂：同步目标→使能；底盘/升降：清零速度→使能），而不是一行 `enable_torque()` 了事。
- [ ] **从臂 `jog` 模式还没跑** —— 脚本层的使能顺序隐患已修（§6.8），可以安全跑；跑完即可补齐第 4 步的全部单硬件测试
- [ ] **从臂 EEPROM 限位过宽** —— `shoulder_lift` / `elbow_flex` 记成 ±180°，`wrist_roll` 与当前代码写出的 [0, 4095] 不符 → EEPROM 是旧版标定代码写的。核对后可能要重做标定（§6.4）
- [ ] **升降机械行程上限未探明** —— 真机已确认 ≥ 300 mm（§6.7），但 `soft_max_mm=600` **未经验证**。若真实上限更低，Host 下发 600 mm 会像 homing 一样顶死在上限硬限位。跑 `lift.py --heights 0,400,500 --dwell 20 --show-registers` 探明，并按实测值回填 `soft_max_mm`
- [ ] **下降段没有负载反馈** —— 300 → 80 mm 下降全程电流恒为 `0.0 mA`（上升段 117–156 mA），而下降速度与上升完全相同（都是 345 tick/采样）。两种可能：(a) 台面靠重力下行、伺服只做微调 ⇒ 速度环没真正控速；(b) 该固件在这个方向不报告电流。**共同后果：`--current-cutoff` 在下降方向失效，下降途中卡死不会触发保护。** 用 `--show-registers` 看 `Present_Velocity` 判定（§6.7）
- [ ] **右臂标定状态未确认** —— 2026-10-29 只测了左臂

**原有待办**

- [ ] 相机**元数据节点**（video1/3/5）的 `ID_V4L_CAPABILITIES` 未确认 —— 决定相机的 udev 过滤条件是否唯一
- [x] ~~相机 udev 别名未建（5-2）~~ —— ✅ **不需要建**，厂商已预装全部 `am_camera_*` 别名（§5-1）；配置同步也已完成（§5-2），余下"实际开图"由 `cameras.py` 验证
- [ ] 相机视角未确认（5-3）—— 可直接用 `python examples/debug/cameras.py --camera head_top --save-dir /tmp/cam_frames --frames 10` 存 PNG 代替 `v4l2-ctl`
- [ ] `config_alohamini.py` 未改（5-4）—— 键名已定为 `head_front` / `head_top`，待 5-3 确认视角后决定是否再改
- [ ] **PC 上 Leader 臂的型号/ID 未确认** —— 决定 `--teleop.id` 和 `--teleop.arm_profile`
- [ ] PC 端 udev 规则（Leader 臂别名）未建
- [ ] `alohamini_sim` 不可用（缺 URDF + LFS 未拉 + 43 处硬编码路径），与真机上手无关，但别指望仿真

> ℹ️ **`feetech-servo-sdk` 的 import 名是 `scservo_sdk`**，不是 `feetech_servo_sdk`
> （见 `src/lerobot/utils/import_utils.py:114`）。用 `python -c "import scservo_sdk"` 验证。

---

## 9. 相关文件

| 文件 | 用途 |
|---|---|
| [getting_started.md](getting_started.md) | 完整开箱流程（12 阶段 + 检查清单） |
| [udev/90-alohamini.rules](udev/90-alohamini.rules) | 可直接安装的 udev 规则（手臂部分已填序列号，相机部分待填） |
| [commands.md](commands.md) | 命令速查 |
| [profiles.md](profiles.md) | 硬件型号对照 |
| `examples/debug/README.md` | 调试脚本族总览（前置条件 / 脚本一览 / 已知坑） |
| `src/lerobot/robots/alohamini/config_alohamini.py` | 相机配置（待改） |
| `src/lerobot/robots/alohamini/lift_axis.py` | 升降轴功能库（`lift.py` 的被调用方，改动会影响 Host 主链路） |
| `src/lerobot/robots/alohamini/model_specs.py` | 型号 → 硬件规格的权威定义 |
