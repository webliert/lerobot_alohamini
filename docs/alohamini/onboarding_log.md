# AlohaMini 上手进度记录

> **用途**：记录实体设备上手过程中的**实测结论**，供下次接手时直接续做，避免重复排查。
> 配套手册：[getting_started.md](getting_started.md)（流程）· [profiles.md](profiles.md)（型号）· [commands.md](commands.md)（命令速查）
>
> 最后更新：**2026-10-28**

---

## 状态摘要

| 项 | 状态 |
|---|---|
| **当前阶段** | 第 5 步 · **从臂标定**（相机这步已收口） |
| **下一步** | §6 从臂标定 → 双臂断电重启 → 底盘/升降测试 → 启 Host |
| 机器人型号 | ✅ **已确定：`alohamini1`** |
| 手臂串口 | ✅ 已确认（含序列号映射） |
| 相机 | ✅ **全部完成**：别名已建 · 配置已改并同步到 Pi · 三台视角已抓图确认无镜像/倒置 · 启用 `head_front`+`head_top`（MJPG） |
| 从臂标定 | ⬜ 未开始 |
| 底盘/升降测试 | ⬜ 未开始 |
| Host 启动 | ⬜ 未开始 |
| 主臂标定（PC） | ⬜ 未开始 |
| 遥操作验收 | ⬜ 未开始 |
| 数据采集 | ⬜ 未开始 |

---

## 1. 环境

| 项 | 值 |
|---|---|
| 树莓派 | `pi5@raspberrypi`，主机名 `raspberrypi` |
| **树莓派 IP** | **`10.168.1.110`**（`<Pi_IP>`） |
| 树莓派仓库路径 | **`/home/pi5/lxy_ws/lerobot_alohamini`**（2026-10-28 实测；此前记的 `~/lerobot_alohamini` 不准） |
| 树莓派 Python 环境 | conda env `lerobot_alohamini`（已激活），**实际是 Python 3.10** |
| 树莓派串口权限 | ✅ 可正常访问 `/dev/ttyACM*`（`dialout` 已生效） |
| PC 终端环境（2026-10-28 起） | 原生 Linux `szxx`，仓库路径 `/home/szxx/lxy_ws/lerobot_alohamini`（此前是 WSL2 `/home/trolorm/...`） |
| PC 网段 | `10.211.232.66/24`（路由器 `10.211.232.39`）→ **与树莓派不同网段** |
| PC 角色 | Leader 臂 + 策略推理/训练（**Leader 臂尚未接入**） |
| 网络 | ⚠️ 树莓派 `10.168.1.110` 在 `10.168.1.0/24`，**从当前 PC 不可达**（ping 100% 丢包、ssh 22 超时）→ 需把 PC 接到机器人局域网，或提供新的 `<Pi_IP>` |

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

→ **旧默认配置必然开不了相机**，Host 会在 `cam.connect()` 处抛异常。
→ 仓库侧已修（`cfd8feba`）：改为 `head_front` + `head_top`，并加 `fourcc="MJPG"`；`head_back` 保留为注释备用。
→ **Pi 上的那份还是旧的** → 同步（§5-2）之前启动 Host 仍会失败。
→ 相机键名会进入数据集 schema（`observation.images.<key>`），一旦开始采集就固定。

### 4.5 建议：强制 MJPG

`OpenCVCameraConfig` 有 `fourcc` 参数但 AlohaMini 配置未使用，实测默认协商到 **YUYV**。
640×480 YUYV@30fps ≈ **18 MB/s/台**，3 台 ≈ 55 MB/s，单 USB 2.0 带宽就吃满了 → 控制循环会掉帧。
MJPG 约几百 KB/s。**配置里应加 `fourcc="MJPG"`**。

---

## 5. 下一步（续做从这里开始）

### 5-0 仓库侧状态（2026-10-28 已完成的部分）

分支 `feat/alohamini-onboarding`（已推送 `origin/feat/alohamini-onboarding`）：

| 提交 | 内容 |
|---|---|
| `cfd8feba` | `config_alohamini.py` 相机改绑 `head_front` / `head_top` + `fourcc="MJPG"`，删掉未接的 `wrist_right` |
| `2a1051b2` | 本手册 + 中文 README + udev 参考件 |

**相机键名的影响面已核实**：`grep` 全仓库只有键盘映射用到字符串 `"forward"`（`config_alohamini.py:148` 速度键、`alohamini_client.py:567` 前进键），
**没有任何代码硬编码相机键名**。图像由 Pi 上的 Host 按配置打开、经 ZMQ 传到 PC，
PC 侧 `record_bi*.py` 不本地开相机 → **相机键名只需在 Pi 侧一致即可**，PC 侧会自动跟随。

⚠️ 唯一约束：键名会写进数据集 schema（`observation.images.<key>`），**开始采集后就固定**，改键名 = 换一套 schema。

### 5-1 ~~装 udev 规则~~ → **不需要，已由厂商预装** ✅

手臂和相机的别名**全部已存在且映射正确**，见 §4.1。
仓库里的 `docs/alohamini/udev/90-alohamini.rules` 只作为说明与备份，**不必安装**。

**唯一要做的**：把 `config_alohamini.py` 的相机路径改成厂商别名。

### 5-2 同步相机配置到树莓派 + 验证

仓库里的 `config_alohamini.py` **已经是新的**（`cfd8feba`），Pi 上那份还是旧的，需要同步。二选一：

**方式 A — 在 Pi 上 git 拉取（推荐）**

```bash
# <Pi>
cd ~/lerobot_alohamini
git fetch origin
git checkout feat/alohamini-onboarding
git pull
```

**方式 B — 只传这一个文件**

```bash
# <PC>
scp src/lerobot/robots/alohamini/config_alohamini.py \
    pi5@<Pi_IP>:~/lerobot_alohamini/src/lerobot/robots/alohamini/config_alohamini.py
```

同步后在 Pi 上验证（**用 Pi 的 conda 环境**：`conda activate lerobot_alohamini`）：

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

用**别名**抓（不要再用 `/dev/videoN`，插拔会移位）：

```bash
mkdir -p /tmp/camcheck
for n in head_front head_top head_back; do
  v4l2-ctl -d /dev/am_camera_$n \
    --set-fmt-video=width=640,height=480,pixelformat=MJPG \
    --stream-mmap=3 --stream-count=1 --stream-to=/tmp/camcheck/$n.jpg 2>/dev/null
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

> ✅ **2026-10-28 收口**：三张图已抓取并人工确认（画面正常、无上下颠倒、无左右镜像）。
> **键名沿用厂商别名**：`head_front` + `head_top`（`head_back` 保留注释，不启用）。
> 理由：厂商 USB product string 已把三台相机命名成 `am_camera_head_{front,top,back}`，
> 键名与硬件别名一一对应，换名只会徒增不一致；且键名会进数据集 schema，越早定越好。
> 仓库侧改动已在 `cfd8feba` 提交，Pi 侧已 `git pull` 同步并验证出图。

---

## 6. 后续阶段命令（`alohamini1` 版，已填好）

### 从臂标定（树莓派，**必须在启动 Host 之前**）

```bash
python -m lerobot.robots.alohamini.alohamini_calibrate --robot_model alohamini1
```
流程：左臂摆机械中位 → 回车 → 转过完整 ROM → 回车；右臂同理。
脚本结束会自动执行**升降轴回零**（输出 `Lift axis homed to 0mm.`）。
⚠️ **标定后给双臂断电重启**。

### 底盘 / 升降单独测试（树莓派）

> ⚠️ **必须先停掉 Host**（`Ctrl+C` 退出 `alohamini_host`）。
> 原因：`wheels.py` / `axis.py` 自己 `FeetechMotorsBus(port=...)` 直接打开 `/dev/am_arm_follower_left`，
> 而 Host 在 `connect()` 时也长期占用同一个端口 —— USB CDC 同一时刻只能被一个进程打开，
> 第二个会报 `Device or resource busy`；即使能打开，两个进程也会同时写同一批电机
> （Host 写 position、脚本写 velocity），动作互相打架、无法解释。
> 标定脚本同理，所以顺序是：**标定 → 断电重启 → 底盘/升降测试 → 启 Host**。

```bash
python examples/debug/wheels.py --port /dev/am_arm_follower_left
python examples/debug/axis.py   --port /dev/am_arm_follower_left
```
> ⚠️ `axis.py` 硬编码 `sts3215` + `RANGE_0_100`；`alohamini1` 的升降电机确实是 STS3215，但真实配置用的是 `DEGREES` 归一化 —— 该脚本测出来的数值**不要当作真值**，只用来确认「能升降、不顶死」。
> 依赖 `pynput`（含在 `hardware` extra，Pi 上 `.[all]` 已装）；报 `No module named 'pynput'` 就 `pip install pynput`。

> ### ⚠️ 无显示器（headless / SSH）下的键盘
>
> 2026-10-28 实测踩坑：`pynput` 在树莓派上**导入即失败**——
> `ImportError: this platform is not supported: ('failed to acquire X connection: Bad display name ""')`，
> 因为它要在 import 时绑定 X 显示，而 Pi 上没有 X server。
>
> **已修**：`examples/debug/wheels.py` 和 `axis.py` 改为
> 「有显示 → `pynput`（按住即动、松开即停）；无显示 → 仓库自带的 `TerminalKeyListener`
> 读控制终端（`lerobot.utils.keyboard_input`）」。
> 终端模式只有 key-down 没有 key-release，所以语义变成
> **按一下键开始动，停手约 0.4 s 后自动停，连按可保持运动**；`Q`/`ESC` 退出。
>
> ⚠️ `PYNPUT_BACKEND=uinput` 在 SSH 下**没用**：SSH 敲的键进的是远端 TTY，不经过内核 input 层，
> uinput 后端只能看到**插在 Pi 上的物理键盘**。

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

## 7. 待办 / 风险备忘

- [ ] 相机**元数据节点**（video1/3/5）的 `ID_V4L_CAPABILITIES` 未确认 —— 当前靠 `ATTR{index}=="0"` 已能区分采集/元数据节点，**非阻塞**
- [x] 相机 udev 别名 → 厂商已预装，不需要建（§5-1）
- [x] 仓库 `config_alohamini.py` 已改（`cfd8feba`：`head_front` + `head_top` + MJPG）
- [x] `config_alohamini.py` 已同步到 Pi 并验证出图（§5-2）
- [x] 相机视角已确认（§5-3 → §5-4）：无镜像、无倒置，键名定稿 `head_front` + `head_top`
- [ ] 从臂标定（§6）+ 双臂断电重启
- [ ] 底盘 / 升降轴单独测试
- [ ] Host 启动（50 Hz）
- [ ] **PC 上 Leader 臂的型号/ID 未确认** —— 决定 `--teleop.id` 和 `--teleop.arm_profile`
- [ ] PC 端 udev 规则（Leader 臂别名）未建 —— 三个脚本端口硬编码 `/dev/am_arm_leader_{left,right}`
- [ ] **PC ↔ Pi 网络不通**（当前 PC 在 `10.211.232.0/24`，Pi 在 `10.168.1.0/24`）→ 遥操/录制前必须解决
- [ ] `alohamini_sim` 不可用（缺 URDF + LFS 未拉 + 43 处硬编码路径），与真机上手无关，但别指望仿真
- ⚠️ **树莓派 conda env 是 Python 3.10，而 `pyproject.toml` 要求 `>=3.12`** —— 目前能跑，但装某些新依赖时可能解析失败；必要时重建 3.12 环境

> ℹ️ **`feetech-servo-sdk` 的 import 名是 `scservo_sdk`**，不是 `feetech_servo_sdk`
> （见 `src/lerobot/utils/import_utils.py:114`）。用 `python -c "import scservo_sdk"` 验证。

---

## 8. 相关文件

| 文件 | 用途 |
|---|---|
| [getting_started.md](getting_started.md) | 完整开箱流程（12 阶段 + 检查清单） |
| [udev/90-alohamini.rules](udev/90-alohamini.rules) | 可直接安装的 udev 规则（手臂部分已填序列号，相机部分待填） |
| [commands.md](commands.md) | 命令速查 |
| [profiles.md](profiles.md) | 硬件型号对照 |
| `src/lerobot/robots/alohamini/config_alohamini.py` | 相机配置（待改） |
| `src/lerobot/robots/alohamini/model_specs.py` | 型号 → 硬件规格的权威定义 |
