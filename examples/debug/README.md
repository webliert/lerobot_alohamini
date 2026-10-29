# AlohaMini 硬件调试脚本

逐个验证 AlohaMini 各部件的独立脚本。每条命令都在**对应硬件独占**的前提下运行。

## 前置条件

1. **先停掉 Host。** 调试脚本与 Host 争用同一个串口（`/dev/am_arm_follower_left`），
   同时跑会串帧，还可能让机械臂在没预期的时候动。
   ```bash
   pgrep -af alohamini_host     # 没有输出才安全
   ```
2. **串口必须独占。** 同一个 `/dev/ttyACM*` 不能被两个进程同时打开。
3. **新脚本不需要键盘。** `base_pulse.py` / `lift.py` / `arms.py` / `cameras.py`
   都不依赖 pynput，SSH 到 headless 的树莓派上可以直接跑。
   `wheels.py` 和 `motors.py` 里的旧脚本依赖 pynput 抓键盘。
4. **串口路径。** 新脚本的 `--port` 默认值是 udev 别名 `/dev/am_arm_follower_left`
   ——插拔后不会漂移；`/dev/ttyACM0` 这种编号会变。
   `motors.py` / `wheels.py` 的默认值仍是 `/dev/ttyACM0`，用它们请**显式传 `--port`**。

## 脚本一览

| 脚本 | 测什么 | 需要键盘 | 默认 `--port` |
|---|---|---|---|
| `motors.py` | 低层工具箱：读电机状态、改 ID / 相位、开关力矩、回中点 | 否 | `/dev/ttyACM0` |
| `base_pulse.py` | 底盘三轮：固定动作序列（前进/后退/横移/旋转） | 否 | `/dev/am_arm_follower_left` |
| `wheels.py` | 底盘三轮：键盘实时遥操作 | **是**（pynput） | `/dev/ttyACM0` |
| `lift.py` | 升降轴（ID 11）：homing + mm 闭环 | 否 | `/dev/am_arm_follower_left` |
| `arms.py` | 从臂（ID 1–6）：关节读数 + 单关节点动 | 否 | `/dev/am_arm_follower_left` |
| `cameras.py` | 相机（head_front / head_top）：fourcc / 帧率 / 曝光 | 否 | — |

`base_pulse.py` / `lift.py` / `arms.py` / `cameras.py` 共用 `_common.py` 里的
总线生命周期与过流保护；退出码统一为：`0` = 通过，`1` = 过流或运行异常，`2` = 参数错误。

### 环境探针脚本（不需要硬件）

用来确认运行环境，不驱动任何硬件：

| 脚本 | 检查什么 |
|---|---|
| `test_cv.py` | OpenCV 是否装好、`cv2` 路径、能否打开相机 |
| `test_cuda.py` | PyTorch / CUDA 是否可用、GPU 型号 |
| `test_network.py` | 外网连通性（Google / HuggingFace） |
| `test_dataset.py` | 读一个 parquet 分片，验证 `datasets` 可用 |
| `test_input.py` | 无头 / Wayland 下键盘输入是否可用 |
| `test_mic.py` | 音频设备枚举与录音 |

---

## 底盘

### 固定动作序列（推荐，headless 可跑）

```bash
python examples/debug/base_pulse.py \
  --port /dev/am_arm_follower_left \
  --steps fwd:1,back:1,left:1,right:1,rotl:1,rotr:1
```

动作名：`fwd` 前进 · `back` 后退 · `left`/`right` 横移 · `rotl`/`rotr` 旋转。
每步跑完自动停车，并打印三轮的 raw 速度与实测电流；电流超过 `--current-cutoff`
（默认 1000 mA，STS3215 额定 900 mA）立即停机并以退出码 1 结束。

### 键盘遥操作

```bash
python examples/debug/wheels.py \
  --port /dev/am_arm_follower_left
```

按键：`W/S` 前进后退 · `Z/X` 左右横移 · `A/D` 旋转 · `Q` 退出（`ESC` 也会触发退出）。

> ⚠️ **已知问题**：`wheels.py` 退出时调用的 `stop()` 给 `write()` 传了电机**列表**，
> 而 `write()` 只接受电机**名字**，会抛 `TypeError` —— 而这个异常被 `except Exception: pass`
> 吞掉了。结果是**退出时轮子可能停不下来**。急停请直接 `Ctrl-C` 后断电，
> 或改用 `base_pulse.py`（它的 `finally` 里一定会写 `Goal_Velocity=0`）。
> 这个 bug 本轮没有改动代码，只在此记录。

---

## 升降轴

升降电机是 **ID 11**，在**左总线**上。

```bash
python examples/debug/lift.py \
  --port /dev/am_arm_follower_left \
  --heights 0,80,200,80,10
```

`lift.py` 先 homing（下行到底部硬限位，把触底位置定为 0 mm），再按 mm 目标闭环运动，
逐步打印目标/实测高度、ticks、电流。**不需要键盘**，SSH 无 X11 也能跑。

参数按型号：`alohamini1` 用 `sts3215` + 导程 84 mm/转（脚本默认值即匹配）；
`alohamini2` / `2pro` 用 `sts3095` + 导程 131 mm/转，需加 `--model sts3095 --lead-mm-per-rev 131`。

---

## 从臂（follower arm）

从臂 6 个关节在总线上的 ID 是 **1–6**（`shoulder_pan` … `gripper`），
左臂挂左总线，右臂挂右总线，两侧 ID 同构。

### 只读（标定验收用，不动机械臂）

```bash
python examples/debug/arms.py --port /dev/am_arm_follower_left --arm left
```

逐关节打印 ticks / 角度 / EEPROM 里的真实限位 / 实测电流，并检查 `Homing_Offset`：

- 全部为 0 → 打印「**尚未标定**（或标定后没断电重启）」；
- 存在非零值 → 打印「已标定」。

标定 + 断电重启后再跑一次，这是标定是否生效的验收手段。

### 单关节点动

```bash
python examples/debug/arms.py --port /dev/am_arm_follower_left --arm left \
  --mode jog --joint shoulder_pan --delta-deg 5
```

只动 `--joint` 指定的那一个关节（增量 `--delta-deg` 度，可为负），
目标位置会被夹到 EEPROM 的 `Min/Max_Position_Limit` 之内，
其余关节使能保持但不下发位置指令。结束后自动回到起点。

---

## 相机

```bash
# 测配置里的两台相机（head_front + head_top）
python examples/debug/cameras.py

# 只测一台，并把 10 帧存成 PNG
python examples/debug/cameras.py --camera head_top \
  --save-dir /tmp/cam_frames --frames 10
```

默认**不开 GUI**（树莓派通常是 headless），只报告：

- **协商到的 fourcc** —— 仓库的 `_validate_fourcc` 协商失败时**只 warning 不报错**，
  所以脚本自己再读一遍 `CAP_PROP_FOURCC` 显式校验。
  实际是 `YUYV` 而不是 `MJPG` 时，USB 带宽会差一个数量级（YUYV 640x480@30 ≈ 18 MB/s/台）。
- **实测帧率**、实际分辨率、曝光 / 增益；
- **画面亮度统计** —— 用来区分「正常画面」「全黑」「满屏噪点」
  （树莓派 ISP 的伪节点 `/dev/video19`–`/dev/video35` 只会刷出噪点，不是真相机）。

加 `--show` 才会弹预览窗口。

---

## `motors.py`（低层工具箱）

#### 查看全部电机状态

```bash
python examples/debug/motors.py get_motors_states \
  --port /dev/am_arm_follower_left
```

#### 指定 ID 转动

```bash
python examples/debug/motors.py move_motor_to_position \
  --id 1 \
  --position 2 \
  --port /dev/am_arm_follower_left
```

#### 设置新 ID

```bash
python examples/debug/motors.py configure_motor_id \
  --id 1 \
  --set_id 8 \
  --port /dev/am_arm_follower_left
```

#### 设置指定舵机的相位

```bash
python examples/debug/motors.py configure_motor_phase \
  --id 1 \
  --set_phase 12 \
  --port /dev/am_arm_follower_left
```

#### 设置所有舵机的相位

```bash
python examples/debug/motors.py configure_motor_phase \
  --set_phase 12 \
  --port /dev/am_arm_follower_left
```

#### 把当前位置设为电机中点

```bash
python examples/debug/motors.py reset_motors_to_midpoint \
  --port /dev/ttyACM1
```

#### 关闭所有手臂电机的力矩

```bash
python examples/debug/motors.py reset_motors_torque \
  --port /dev/am_arm_follower_left
```

#### 执行动作脚本

```bash
python examples/debug/motors.py move_motors_by_script \
  --script_path action_scripts/test_dance.txt \
  --port /dev/am_arm_follower_left
```

> ⚠️ **两个必须知道的事实**：
>
> 1. **当前只会驱动夹爪。** `move_motors_by_script` 只注册了 `gripper` 一个电机，
>    其余关节行被**静默跳过**。`action_scripts/*.txt` 里 `shoulder_pan` / `shoulder_lift` /
>    `elbow_flex` / `wrist_flex` / `wrist_roll` 的行**不会执行**，
>    实际跑出来的只有夹爪动作和 `sleep`。
> 2. **这里的 `gripper` 是 ID 8 —— 在 AlohaMini 上那是底盘左轮，不是夹爪。**
>    AlohaMini 的夹爪在 ID 6。在左总线上跑这个脚本会往底盘左轮下发 `Goal_Position`。
>    用之前先确认总线拓扑，或改用 `arms.py`。
>
> 另外，`--script_path` 是**相对 `examples/debug/`** 解析的
> （见 `motors.py` 里的 `os.path.join(script_dir, script_path)`），
> 所以写 `action_scripts/test_dance.txt`，写成 `examples/debug/action_scripts/...` 会拼成
> `examples/debug/examples/debug/...` 直接 `FileNotFoundError`。
