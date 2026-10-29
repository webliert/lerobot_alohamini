# AlohaMini 新设备开箱手册

> 从一台**刚到货的机器人**到**采出第一批可用数据**的完整检查清单。
> 按顺序执行，每一步都有明确的「通过标准」。
>
> 相关文档：[install.md](install.md)（环境安装细节）· [alohamini.md](alohamini.md)（双机工作流）· [am-arm200.md](am-arm200.md)（单臂工作流）· [profiles.md](profiles.md)（硬件型号）· [commands.md](commands.md)（命令速查）· [onboarding_log.md](onboarding_log.md)（**实测进度记录 / 续做入口**）

---

## 目录

- [0. 适用范围](#0-适用范围)
- [1. 开工前清单](#1-开工前清单)
- [2. 阶段一 — 硬件装配与接线](#2-阶段一--硬件装配与接线)
- [3. 阶段二 — 设备识别与检查](#3-阶段二--设备识别与检查)
- [4. 阶段三 — 树莓派环境配置](#4-阶段三--树莓派环境配置)
- [5. 阶段四 — 固定设备名与相机配置](#5-阶段四--固定设备名与相机配置)
- [6. 阶段五 — 从臂标定](#6-阶段五--从臂标定)
- [7. 阶段六 — 底盘与升降轴单独测试](#7-阶段六--底盘与升降轴单独测试)
- [8. 阶段七 — 启动 Host](#8-阶段七--启动-host)
- [9. 阶段八 — PC 端环境与主臂标定](#9-阶段八--pc-端环境与主臂标定)
- [10. 阶段九 — 遥操作验收](#10-阶段九--遥操作验收)
- [11. 阶段十 — 数据采集](#11-阶段十--数据采集)
- [12. 阶段十一 — 数据校验](#12-阶段十一--数据校验)
- [13. 阶段十二 — 训练与评估](#13-阶段十二--训练与评估)
- [14. 故障排查速查表](#14-故障排查速查表)
- [15. 完整检查清单](#15-完整检查清单)

---

## 0. 适用范围

本手册针对 **AlohaMini 整机**（双臂 + 全向移动底盘 + 升降轴，树莓派 + PC 双机架构）。

**单臂 AM-ARM200（无需树莓派）请看 [am-arm200.md](am-arm200.md)**，流程更短：一台 PC，leader 和 follower 直接 USB 相连。

本手册用 `<Pi_IP>` 表示树莓派 IP，`<Pi>` 表示在树莓派上执行，`<PC>` 表示在 PC 上执行。**机器人型号请全程替换为你的实际型号**（`alohamini1` / `alohamini2` / `alohamini2pro`），三处必须一致：

- Host 的 `--robot_model`
- Client 的 `--robot.robot_model`
- 标定命令的 `--robot_model`

---

## 1. 开工前清单

### 硬件

- [ ] 树莓派（或等效主机）+ PC，**两台机器在同一局域网**
- [ ] 左臂控制器板（随动臂）
- [ ] 右臂控制器板（随动臂）
- [ ] Leader 臂控制器板 ×2（装在 PC 上）
- [ ] 底盘三轮电机 + 升降轴电机（**与左臂同总线**，见 §2）
- [ ] 相机 ≥1（**每台独占一个 USB 口**）
- [ ] USB 供电/电源适配器（注意 5V/7.4V 与 12V 两种电机版本**不可互换**）

### 账号与网络

- [ ] Hugging Face 账号 + **具备 read & write 权限**的 token
- [ ] 两台机器能互通：`ping <Pi_IP>` 通
- [ ] WiFi/网线带宽足够（相机图像实时回传）

---

## 2. 阶段一 — 硬件装配与接线

### 2.1 总线拓扑（重要）

底盘和升降轴**没有独立串口**，它们与**左臂串在同一条总线**上：

```
/dev/am_arm_follower_left          /dev/am_arm_follower_right
├─ ID 1..7   左臂（6 或 7 关节）     └─ ID 1..7   右臂（6 或 7 关节）
├─ ID 8      base_left_wheel
├─ ID 9      base_back_wheel
├─ ID 10     base_right_wheel
└─ ID 11     lift_axis（升降轴）
```

整机只有 **两条串口**。底盘三轮和升降轴要**菊花链**在左臂控制器之后。

### 2.2 接线检查

- [ ] 左右臂电机按 ID 顺序串接，两条总线各自独立
- [ ] 底盘三轮 + 升降轴串在左臂总线尾部
- [ ] 电机**完全卡入**接插件（听到"咔哒"声）
- [ ] 电源电压与电机型号匹配（5V/7.4V 版 vs 12V 版**不可互换**）
- [ ] 每台相机独占一个 USB 口，**不要共用 USB Hub**

> **LED 速查**：全部稳定红灯 = 接线正常；部分熄灭 / 链中断 = 接线或供电问题；闪烁 = 电机报错（过载或供电电压不对）。

---

## 3. 阶段二 — 设备识别与检查

**在 `<Pi>` 上执行**（电机和相机都接在树莓派上）。

### 3.1 找串口

```bash
lerobot-find-port
ls /dev/ttyACM*
ls /dev/serial/by-id/
```

> **一次只插一个设备**再跑 `lerobot-find-port`，否则无法区分哪个是哪个。

**通过标准**：能看到两条串口（对应左右臂总线）。

### 3.2 找相机

```bash
lerobot-find-cameras
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext
```

`lerobot-find-cameras` 会实际抓帧并把截图存到 `outputs/captured_images/`，**确认画面是当前视角**（不是黑屏、不是上次会话的旧图）。

**通过标准**：每台相机都能抓到清晰、方向正确的画面。

### 3.3 电机 ID 与状态体检（可选但推荐）

```bash
python examples/debug/motors.py get_motors_states --port /dev/ttyACM0
```

确认 ID 分布：左总线应为臂 1–7 + 底盘 8/9/10 + 升降 11。ID 不对可修正：

```bash
python examples/debug/motors.py configure_motor_id --id 1 --set_id 8 --port /dev/ttyACM0
```

---

## 4. 阶段三 — 树莓派环境配置

**在 `<Pi>` 上执行**。

```bash
# 1) Python 环境（本项目统一用 conda，不建 uv 的 .venv）
conda create -y -n lerobot_alohamini python=3.12
conda activate lerobot_alohamini
pip install -e ".[all]"
pip install pyzmq feetech-servo-sdk
conda install -y ffmpeg=7.1.1 -c conda-forge

# 2) 串口权限（必须重启才生效）
sudo usermod -a -G dialout $USER
sudo reboot

# 3) Hugging Face 登录
git config --global credential.helper store
hf auth login --token <your_token> --add-to-git-credential
export HF_USER=$(hf auth whoami | sed 's/^user=//')
```

**通过标准**：`python -c "import lerobot, zmq, feetech_servo_sdk; print('ok')"` 无报错；`ls -l /dev/ttyACM*` 显示当前用户有 `dialout` 组权限。

---

## 5. 阶段四 — 固定设备名与相机配置

### 5.1 固定设备名（udev）——强烈建议

否则每次重插 USB 或重启，端口号都会变，配置文件得跟着改。

```bash
# 查序列号
udevadm info --attribute-walk --name=/dev/ttyACM0 | awk -F'"' '/ATTRS{serial}/{print $2; exit}'
```

```udev
# /etc/udev/rules.d/90-mydevice.rules
SUBSYSTEM=="tty", ATTRS{serial}=="<follower_left_serial>",  SYMLINK+="am_arm_follower_left"
SUBSYSTEM=="tty", ATTRS{serial}=="<follower_right_serial>", SYMLINK+="am_arm_follower_right"
SUBSYSTEM=="tty", ATTRS{serial}=="<leader_left_serial>",    SYMLINK+="am_arm_leader_left"
SUBSYSTEM=="tty", ATTRS{serial}=="<leader_right_serial>",   SYMLINK+="am_arm_leader_right"
```

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
ls /dev/am*
```

### 5.2 相机配置

编辑 [src/lerobot/robots/alohamini/config_alohamini.py](../../src/lerobot/robots/alohamini/config_alohamini.py) 的 `alohamini_cameras_config()`：

```python
def alohamini_cameras_config() -> dict[str, CameraConfig]:
    return {
        "forward": OpenCVCameraConfig(
            index_or_path="/dev/am_camera_forward",
            fps=30, width=640, height=480, rotation=Cv2Rotation.NO_ROTATION,
        ),
        "wrist_right": OpenCVCameraConfig(
            index_or_path="/dev/am_camera_wrist_right",
            fps=30, width=640, height=480, rotation=Cv2Rotation.NO_ROTATION,
        ),
        # "backward" / "chest" / "wrist_left" 默认注释掉，按需启用
    }
```

- 设备名要和 §5.1 的 udev 规则一致
- **改完必须重启 Host**（见 §8）
- 建议**两台相机**：1 台固定前方 + 1 台腕部。多视角通常优于单视角

**通过标准**：配置文件里的相机路径与 `ls /dev/am_camera_*` 一一对应。

---

## 6. 阶段五 — 从臂标定

> **在启动 Host 之前做。** 标定脚本结束后会自动完成升降轴回零。
> 见 [alohamini.md §4 Step 1](alohamini.md)。

**在 `<Pi>` 上执行**：

```bash
python -m lerobot.robots.alohamini.alohamini_calibrate --robot_model alohamini2
```

交互流程（每条臂重复）：

1. 把该臂所有关节摆到**机械行程中位** → 回车
2. 依次把关节转过**完整 ROM** → 回车结束
3. 脚本自动写入标定文件（路径见输出）
4. 最后自动执行升降轴回零，输出 `Lift axis homed to 0mm.`

**如果标定文件已存在**，脚本会提示：

```
Press ENTER to use provided calibration file associated with the id AlohaMiniRobot,
or type 'c' and press ENTER to run calibration:
```

直接回车 = 复用现有标定；输入 `c` = 重新标定。

**通过标准**：

- [ ] 左臂、右臂都能顺畅转过整个行程，无卡死
- [ ] 输出 `AlohaMini calibration complete.`
- [ ] 输出 `Lift axis homed to 0mm.`

> ⚠️ **标定后必须给双臂断电重启**，标定才生效。

---

## 7. 阶段六 — 各硬件单独测试

标定完成后，先逐个验证底盘、升降轴、相机、从臂，避免等整套跑起来再排查。

> ⚠️ **前置条件（所有调试脚本都适用）**：**Host 必须已停** —— 脚本与 Host 争用同一个串口
> `/dev/am_arm_follower_left`。新脚本（`base_pulse.py` / `lift.py` / `arms.py` / `cameras.py`）
> **不依赖键盘**，SSH 到无 X11 的树莓派上可以直接跑。

### 7.1 底盘

**在 `<Pi>` 上执行**（电机接在树莓派上）：

```bash
python examples/debug/base_pulse.py \
  --port /dev/am_arm_follower_left \
  --steps fwd:1,back:1,left:1,right:1,rotl:1,rotr:1
```

固定动作序列：每一步跑完自动停车，并打印三轮的 raw 速度与实测电流。
电流超过 `--current-cutoff`（默认 1000 mA）立即停机并以退出码 1 结束。

键盘版（需要 pynput 抓键盘，SSH 场景用上面的固定序列）：

```bash
python examples/debug/wheels.py --port /dev/am_arm_follower_left
```

按键：`W/S` 前进后退 · `Z/X` 左右横移 · `A/D` 旋转 · `Q` 退出（`ESC` 也会触发退出）。

**通过标准**：三个轮子都转，方向正确（前进应该是前进，不是后退），旋转方向正常。

### 7.2 升降轴

```bash
python examples/debug/lift.py \
  --port /dev/am_arm_follower_left \
  --heights 0,80,200,80,10
```

`lift.py` 先 homing（下行到底部硬限位 → 0 mm），再按 mm 目标闭环运动，逐步打印目标/实测高度、ticks、电流。
不需要键盘，SSH 无 X11 也能跑。

**通过标准**：

- [ ] homing 后打印 `homing 后高度 = 0.0 mm`，且 `实际行程` 是个合理值（如果 < 1 mm，说明启动时升降台已经在底部，属正常）
- [ ] 每个目标高度 5 s 内到位（`-> 已到位`），实测值与目标相差 ≤ 1 mm
- [ ] 电流读数平稳，没有频繁触发 `--current-cutoff`（默认 1000 mA）

> 低于下行地板（`--descent-floor`，默认 5 mm）的目标会被**直接跳过**并标成
> `被下行保护拦截`，不会空跑一轮再误报「超时，未到位」。
> homing 之后高度本来就是 0 mm，所以 `--heights 0,...` 的第一项被跳过是正常的。

**参数按型号**：`alohamini1` 用 `sts3215` + 导程 84 mm/转（脚本默认值即匹配）；
`alohamini2` / `2pro` 用 `sts3095` + 导程 131 mm/转，需加 `--model sts3095 --lead-mm-per-rev 131`。

> ⚠️ 树莓派上的仓库代码要更新到最新（`LiftAxis.stop()` 是后加的，旧版本会在脚本结束时抛 `AttributeError`）：
> ```bash
> git -C ~/lerobot_alohamini pull
> ```

### 7.3 相机

```bash
# 测配置里的两台相机（head_front + head_top）
python examples/debug/cameras.py

# 只测一台，并把 10 帧存成 PNG
python examples/debug/cameras.py --camera head_top \
  --save-dir /tmp/cam_frames --frames 10
```

默认不开 GUI（树莓派通常是 headless），报告协商到的 fourcc、实测帧率、分辨率、曝光/增益，
以及画面亮度统计（用来区分「正常画面」「全黑」「满屏噪点」）。

**通过标准**：

- [ ] 两台相机都能连上，`实测 FPS` 接近 30
- [ ] `fourcc` 实际是 `MJPG` —— 如果是 `YUYV`，说明协商失败（库里只 warning 不报错），
      YUYV 640x480@30 约 18 MB/s/台，多台会挤爆 USB 带宽
- [ ] 画面统计 `mean` 在 20–200 之间、`std` 不超过 60；存下来的 PNG 用看图软件确认视角正确

### 7.4 从臂

**在 `<Pi>` 上执行**（右臂把 `--arm left` 换成 `--arm right`）：

```bash
# 只读：看关节角、限位、标定状态（完全不动机械臂）
python examples/debug/arms.py --port /dev/am_arm_follower_left --arm left

# 单关节点动：肩关节抬 5 度
python examples/debug/arms.py --port /dev/am_arm_follower_left --arm left \
  --mode jog --joint shoulder_pan --delta-deg 5
```

从臂 6 个关节的 ID 是 **1–6**（`shoulder_pan` … `gripper`），左臂挂左总线、右臂挂右总线。

**通过标准**：

- [ ] `read` 模式逐关节打印出 ticks / 角度 / EEPROM 限位 / 电流，没有「读取失败」
- [ ] 标定 + 断电重启后，`Homing_Offset` 全部非 0（脚本会打印「已标定」）；
      标定前或没断电重启时会打印「尚未标定」
- [ ] `jog` 模式只动指定关节，目标被夹在 EEPROM 限位内，结束后自动回到起点

### 7.5 组合模式（可选）

只测底盘 + 升降、完全不接随动臂：

```bash
# <Pi>
python -m lerobot.robots.alohamini.alohamini_host --robot_model alohamini2 --no_follower
# <PC>
python examples/alohamini/teleoperate_bi.py --no_leader ...
```

---

## 8. 阶段七 — 启动 Host

**在 `<Pi>` 上执行**，保持终端常开。

```bash
python -m lerobot.robots.alohamini.alohamini_host --robot_model alohamini2
```

常用选项：

| 选项 | 作用 |
|---|---|
| `--robot_model` | `alohamini1` / `alohamini2` / `alohamini2pro`，**必须与实际硬件一致** |
| `--no_follower` | 只运行底盘 + 升降，不接随动臂 |
| `--camera-stream` | 开启 ROS 兼容的独立相机流（TCP 5557），**选配** |
| `--camera-stream-port` | 覆写相机流端口 |
| `--profile_timing` | 每秒打印分段耗时（命令/观测/动作/JPEG/网络），排查性能问题用 |

预期输出：

```
Configuring AlohaMini
Connecting AlohaMini
Starting HostAgent
Waiting for commands...
```

**通过标准**：

- [ ] 没有弹出标定提示（说明标定文件已生效）
- [ ] 电机上电后无异常抖动
- [ ] 加 `--profile_timing` 时能看到 `Hz=50.0` 附近的稳定循环频率

> Host 的控制循环是 **50 Hz**，相机请求独立跑 **30 Hz**。两者是解耦的。

---

## 9. 阶段八 — PC 端环境与主臂标定

### 9.1 PC 环境

**在 `<PC>` 上执行**，与 §4 步骤相同（统一用 conda env `lerobot_alohamini`），**同样需要** `dialout` 权限和 `hf auth login`。

### 9.2 主臂标定

Leader 臂接在 **PC** 上：

```bash
python examples/alohamini/calibrate_bi.py \
  --teleop.id am_leader_bi \
  --teleop.arm_profile am-leader-6dof
```

> `am-leader-6dof` 用于 AM-ARM200 / AM-ARM200 Pro；SO-ARM 5 自由度主臂用 `so-arm-5dof`。

这一步**只连主臂**，所以树莓派 Host 不必在运行（当然在运行也没关系）。它的作用是生成标定文件，供后续 `teleoperate_bi.py` / `record_bi.py` 加载——**务必用同一个 `--teleop.id` 和 `--teleop.arm_profile`**。

**通过标准**：

- [ ] 主臂能顺畅转过整个行程
- [ ] 标定文件已生成
- [ ] **双臂断电重启**

---

## 10. 阶段九 — 遥操作验收

Host 已在运行的前提下，**在 `<PC>` 上执行**：

```bash
python examples/alohamini/teleoperate_bi.py \
  --robot.remote_ip <Pi_IP> \
  --robot.robot_model alohamini2 \
  --teleop.id am_leader_bi \
  --teleop.arm_profile am-leader-6dof \
  --fps 50 --camera-fps 30
```

网络/CPU 吃紧时先降频调试：

```bash
  --fps 10 --camera-fps 10
```

键盘按键（底盘 + 升降）：

| 按键 | 动作 |
|---|---|
| `W` / `S` | 前进 / 后退 |
| `Z` / `X` | 左移 / 右移 |
| `A` / `D` | 左转 / 右转 |
| `T` / `G` | 调高 / 调低速度档位 |
| `U` / `J` | 升降轴上升 / 下降 |
| `Q` | 退出遥操作 |

**验收清单**：

- [ ] 主臂动 → 从臂同步跟随，方向一致
- [ ] 键盘能驱动底盘前进/旋转/横移
- [ ] `U`/`J` 能升降轴，且松手即停
- [ ] 相机画面实时显示且**方向正确**（前视相机画面里物体没镜像）
- [ ] 动作无明显抖动、无延迟积累（加 `--profile_timing` 看 Host 侧耗时）

---

## 11. 阶段十 — 数据采集

### 11.1 单速率（默认）

**在 `<PC>` 上执行**：

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

| 参数 | 说明 |
|---|---|
| `--dataset.push_to_hub=false` | 只存本地，不上传 |
| `--dataset.root /path/to/dataset` | 指定本地工作目录 |
| `--resume` | 续录已有数据集 |
| `--profile-timing` | 每秒打印采集耗时分解 |
| `--display-data` | Rerun 可视化 |

首次建议先跑**冒烟测试**（1 集 / 10 fps / 10 秒），确认整条链路通了再正式录：

```bash
python examples/alohamini/record_bi.py \
  --dataset.repo_id $HF_USER/alohamini_smoke_test \
  --dataset.num_episodes 1 --dataset.fps 10 \
  --dataset.episode_time_s 10 --dataset.reset_time_s 3 \
  --dataset.single_task "smoke test" \
  --robot.remote_ip <Pi_IP> --robot.robot_model alohamini2 \
  --teleop.id am_leader_bi --teleop.arm_profile am-leader-6dof
```

### 11.2 多速率（推荐用于正式采集）

控制跑 50 Hz，数据集仍按 `--dataset.fps` 采样新鲜帧：

```bash
python examples/alohamini/record_bi_multirate.py \
  --dataset.repo_id $HF_USER/am2_bi_test \
  --dataset.num_episodes 50 --dataset.fps 30 \
  ...（其余参数同上）
```

多速率录制器会**强制校验**（不满足直接报错，而不是静默写重复帧）：

- 所有相机时间戳都在推进
- 相机间偏斜 ≤ 50 ms
- 状态对齐误差 ≤ 100 ms
- 实际帧率 ≥ 目标帧率的 90%

> CLI 与 `record_bi.py` 完全相同；`control_fps` 固定 50，**没有 CLI 旋钮**。若 `--dataset.fps > 50` 会直接报错。

### 11.3 采集建议

- **先录 5–10 遍不记录**，把操作策略练熟再正式录
- **一致性 > 速度**：固定抓法、固定接近方向、固定节奏
- **先小后大**：第一批固定单物体/固定位置/固定光照，训完看失败点，再**一次只加一个维度**（位置 → 光照 → 物体数量 → 操作者）
- 任务描述用一句**动作导向**的短句，且**训练与评估必须完全一致**

**通过标准**：

- [ ] 录完的 episode 数正确
- [ ] 每集都有图像、状态、动作、task 字段
- [ ] 采集过程中相机没有触发停滞保护

---

## 12. 阶段十一 — 数据校验

> **训练之前一定要做。** 好的数据胜过聪明的模型。

### 12.1 可视化检查

```bash
lerobot-dataset-viz \
  --repo-id $HF_USER/am2_bi_test \
  --episode-index 0 \
  --display-compressed-images
```

逐项检查：

- [ ] 图像没有大面积模糊 / 撕裂 / 运动拖影
- [ ] 目标物体在画面里始终可见
- [ ] 帧率稳定，没有长时间静止或跳帧
- [ ] 物体位置在整个数据集里是多样的（不是每集完全一样）
- [ ] 动作与画面**对得上**（手往左，动作也往左）

### 12.2 回放验证

```bash
python examples/alohamini/replay_bi.py \
  --dataset.repo_id $HF_USER/am2_bi_test \
  --dataset.episode 0 \
  --robot.remote_ip <Pi_IP> \
  --robot.robot_model alohamini2
```

**通过标准**：机器人能按记录的动作复现出与录制时相似的轨迹。若偏差巨大，说明动作/状态对不上——先别训练。

### 12.3 数据集完整性检查（可选）

```bash
python scripts/check_lerobot_dataset_integrity.py \
  --dataset.root $HF_LEROBOT_HOME/$HF_USER/am2_bi_test \
  --decode-videos \
  --output-json integrity_report.json
```

退出码 0 = 无错误，1 = 数据集有问题。

### 12.4 视觉-only 数据集（配合 AM-ACT）

```bash
python -m lerobot.scripts.create_alohamini_visual_only_dataset \
  --source $HF_LEROBOT_HOME/$HF_USER/am2_bi_test \
  --target /path/to/visual_only \
  --keep-camera wrist_right --drop-state
```

---

## 13. 阶段十二 — 训练与评估

### 13.1 训练

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

**训练时长怎么定**（详见 [AGENT_GUIDE.md](../../AGENT_GUIDE.md)）：

```
total_frames    = 集数 × 每集秒数 × fps
steps_per_epoch = ceil(total_frames / batch_size)
total_steps     = epochs × steps_per_epoch
```

- 模仿学习通常 **5–10 个 epoch** 就收敛，不是几十万步
- 短训练要同步调小调度器：`--steps=5000 --policy.scheduler_decay_steps=5000 --save_freq=5000`
- 显存不足用**梯度累积**抬有效 batch，而不是硬塞大 batch

### 13.2 评估

```bash
python examples/alohamini/evaluate_bi.py \
  --eval.n_episodes 10 \
  --fps 20 \
  --eval.episode_time_s 45 \
  --dataset.single_task "pickup1" \
  --policy.path outputs/train/act_am2_bi_test/checkpoints/020000/pretrained_model \
  --dataset.repo_id $HF_USER/eval_act_am2_bi_test \
  --dataset.push_to_hub=false \
  --robot.remote_ip <Pi_IP> \
  --robot.robot_model alohamini2 \
  --inference.type sync \
  --interpolation_multiplier 3
```

- `--interpolation_multiplier 3` 表示控制循环跑 `fps × 3`（20×3 = 60 Hz），动作线性插值
- SmolVLA 等支持 RTC 的策略可用 `--inference.type rtc`；**ACT 必须用 `sync`**
- 每次评估用**新的** `--dataset.repo_id`（本地输出目录不能已存在）

**目标成功率**：50 集干净数据 + 单任务抓放，ACT 应达到 **> 70%**。低于此值通常是**数据问题**而非模型问题——回到 §11.3 补数据。

---

## 14. 故障排查速查表

### 电机不动 / 超时

| 现象 | 排查 |
|---|---|
| 全部稳定红灯 | 接线正常 |
| 部分熄灭、链中断 | 重新插拔 3 针线缆、检查控制器供电、确认电机完全卡入 |
| LED 闪烁 | 电机报错：**过载**（关节顶过限）或**供电电压不对**（5V/7.4V 与 12V 版不可混用） |
| `timeout` / 通信错误 | **大多是物理问题，不是代码问题**——先查 LED 和供电 |

### 权限 / 端口

```bash
sudo usermod -a -G dialout $USER && sudo reboot   # 权限（必须重启）
ls -l /dev/ttyACM*                                  # 确认 dialout 组
ls /dev/am*                                         # udev 别名是否生效
```

### 相机

```bash
lerobot-find-cameras                                # 抓帧确认
v4l2-ctl -d /dev/video0 --list-formats-ext          # 支持的分辨率/FPS
```

- 画面黑 → 检查设备路径与 `config_alohamini.py` 是否一致
- 帧率低 → 检查是否共用了 USB Hub
- 改了相机配置**没生效** → **重启 Host**

### 网络

```bash
ping <Pi_IP>
iw dev wlan0 link            # WiFi 信号
iperf3 -s   # Pi 端      iperf3 -c <Pi_IP>   # PC 端
```

### 性能

```bash
# Host 侧
python -m lerobot.robots.alohamini.alohamini_host --robot_model alohamini2 --profile_timing
# PC 侧
python examples/alohamini/record_bi.py ... --profile-timing
```

### 标定相关

| 现象 | 处理 |
|---|---|
| 标定后行为异常 | **忘记断电重启双臂** → 断电重启 |
| 提示已有标定文件 | 回车复用，或输入 `c` 重标 |
| 关节方向反了 | 检查 `robot_model` 是否与硬件一致；重新标定 |

### 底盘 / 升降

| 现象 | 处理 |
|---|---|
| 底盘方向反了 | 三全向轮安装朝向问题，交换电机相序或调整 `wheels.py` 常量 |
| 升降轴响应不对 | `lift.py` 的电机型号默认 `sts3215`，**AlohaMini 2/2Pro 用的是 STS3095**，请加 `--model sts3095 --lead-mm-per-rev 131` |
| 升降轴顶死不动 | 下降地面保护（`descent_floor_mm`）生效，属正常保护行为 |

### 控制权 / 安全

| 现象 | 说明 |
|---|---|
| 客户端发了指令但机器人不动 | 控制权被其他客户端持有 → 停掉另一个控制端并等待释放 |
| Host 日志 `command watchdog expired` | 1 秒内没收到有效命令 → 主动停车并释放控制权，属保护行为 |
| `joint holds` 非空 | 关节保护触发（电流超限）→ 停下检查是否卡住/碰撞 |

---

## 15. 完整检查清单

按顺序逐项打勾（在 GitHub / VS Code 预览里可直接点击勾选）。

### 硬件

- [ ] 总线拓扑正确（左臂 + 底盘 + 升降 = 左总线，右臂 = 右总线）
- [ ] 电机完全卡入，供电电压与型号匹配
- [ ] 每台相机独占 USB 口

### 树莓派

- [ ] 串口可识别（2 条）
- [ ] 相机可抓帧，方向正确
- [ ] 环境安装完成（lerobot / pyzmq / feetech / ffmpeg）
- [ ] dialout 权限生效（已重启）
- [ ] hf auth login 成功
- [ ] udev 别名生效（`ls /dev/am*`）
- [ ] 相机配置已改（`config_alohamini.py`）
- [ ] 从臂标定完成（含升降轴回零）
- [ ] 双臂已断电重启
- [ ] 底盘测试通过（方向正确）
- [ ] 升降轴测试通过
- [ ] Host 启动无报错，50 Hz 稳定

### PC

- [ ] 环境安装完成
- [ ] dialout 权限生效（已重启）
- [ ] hf auth login 成功
- [ ] 主臂标定完成
- [ ] 双臂已断电重启

### 联调

- [ ] 遥操作：主臂 → 从臂跟随方向正确
- [ ] 键盘驱动底盘正常
- [ ] 升降轴正常
- [ ] 相机画面实时且方向正确

### 数据

- [ ] 冒烟测试（1 集 / 10 fps）通过
- [ ] 正式采集完成，episode 数正确
- [ ] 可视化检查通过（无模糊 / 丢帧 / 动作对不上）
- [ ] 回放验证通过
- [ ] 训练完成并保存 checkpoint
- [ ] 评估完成，记录成功率

---

## 相关文档

| 文档 | 内容 |
|---|---|
| [install.md](install.md) | 安装与配置（conda / uv / 串口 / HF） |
| [alohamini.md](alohamini.md) | 双机工作流详解（架构、端口、相机、标定、遥操、录制、训练、评估） |
| [am-arm200.md](am-arm200.md) | 单臂 AM-ARM200 工作流 |
| [profiles.md](profiles.md) | 硬件型号对照表 |
| [commands.md](commands.md) | 命令速查（udev、性能调优、全部调试命令） |
| [onboarding_log.md](onboarding_log.md) | 实体设备实测进度记录（序列号、型号判定、下一步） |
| [udev/90-alohamini.rules](udev/90-alohamini.rules) | 可直接安装的 udev 规则 |
| [AGENT_GUIDE.md](../../AGENT_GUIDE.md) | 选策略、训练时长、评估基准（面向所有机器人） |
