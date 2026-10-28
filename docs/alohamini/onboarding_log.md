# AlohaMini 上手进度记录

> **用途**：记录实体设备上手过程中的**实测结论**，供下次接手时直接续做，避免重复排查。
> 配套手册：[getting_started.md](getting_started.md)（流程）· [profiles.md](profiles.md)（型号）· [commands.md](commands.md)（命令速查）
>
> 最后更新：**2026-10-27**

---

## 状态摘要

| 项 | 状态 |
|---|---|
| **当前阶段** | 第 3 步 · 设备名固定 + 相机视角确认（**进行中**） |
| **下一步** | 执行 §5 的 3-B（拿相机序列号）和 3-C（抓 3 张图） |
| 机器人型号 | ✅ **已确定：`alohamini1`** |
| 手臂串口 | ✅ 已确认（含序列号映射） |
| 相机 | ⚠️ 已枚举出 3 台，但**视角未确认**、**udev 别名未建** |
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
| 树莓派仓库路径 | `~/lerobot_alohamini`（即 `/home/pi5/lerobot_alohamini`） |
| 树莓派 Python 环境 | conda env `lerobot_alohamini`（已激活） |
| 树莓派串口权限 | ✅ 可正常访问 `/dev/ttyACM*`（`dialout` 已生效） |
| PC 终端环境 | WSL2，`/home/trolorm/lxy_ws/lerobot_alohamini` |
| PC 角色 | Leader 臂 + 策略推理/训练（**Leader 臂尚未接入**） |
| 网络 | 树莓派与 PC 需同局域网，**IP 待确认**（后续所有命令要用 `<Pi_IP>`） |

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

### 5-2 同步相机配置到树莓派 + 验证

Pi 上那份 `src/lerobot/robots/alohamini/config_alohamini.py` 还是旧的，
需要把仓库里的新版同步过去（PC 侧这份已是新的）。

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

## 6. 后续阶段命令（`alohamini1` 版，已填好）

### 从臂标定（树莓派，**必须在启动 Host 之前**）

```bash
python -m lerobot.robots.alohamini.alohamini_calibrate --robot_model alohamini1
```
流程：左臂摆机械中位 → 回车 → 转过完整 ROM → 回车；右臂同理。
脚本结束会自动执行**升降轴回零**（输出 `Lift axis homed to 0mm.`）。
⚠️ **标定后给双臂断电重启**。

### 底盘 / 升降单独测试（树莓派）

```bash
python examples/debug/wheels.py --port /dev/am_arm_follower_left
python examples/debug/axis.py   --port /dev/am_arm_follower_left
```
> ⚠️ `axis.py` 硬编码 `sts3215` + `RANGE_0_100`；`alohamini1` 的升降电机确实是 STS3215，但真实配置用的是 `DEGREES` 归一化 —— 该脚本测出来的数值**不要当作真值**，只用来确认「能升降、不顶死」。

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

- [ ] 相机**元数据节点**（video1/3/5）的 `ID_V4L_CAPABILITIES` 未确认 —— 决定相机的 udev 过滤条件是否唯一
- [ ] 相机 udev 别名未建（5-2）
- [ ] 相机视角未确认（5-3）
- [ ] `config_alohamini.py` 未改（5-4）
- [ ] **PC 上 Leader 臂的型号/ID 未确认** —— 决定 `--teleop.id` 和 `--teleop.arm_profile`
- [ ] PC 端 udev 规则（Leader 臂别名）未建
- [ ] `alohamini_sim` 不可用（缺 URDF + LFS 未拉 + 43 处硬编码路径），与真机上手无关，但别指望仿真

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
