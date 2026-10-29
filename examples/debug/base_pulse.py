#!/usr/bin/env python3
"""底盘固定动作序列测试脚本（Feetech STS3215，ID 8/9/10，左总线）。

与 ``examples/debug/wheels.py`` 的区别：

- **不依赖键盘**：不 import pynput，SSH 到树莓派上也能直接跑；
- **动作是预先排好的序列**，不是实时按键响应，每一步跑完自动停车；
- 每步打印三轮的 raw 速度与实测电流。

前置条件：**Host 必须已经停掉**（本脚本与 Host 争用同一个串口）。

用法::

    python examples/debug/base_pulse.py --port /dev/am_arm_follower_left \
        --steps fwd:1,back:1,left:1,right:1,rotl:1,rotr:1

动作名与 ``wheels.py`` 的键位约定一致：

===========  ===============================================
``fwd``      前进（车体 x 方向 +）
``back``     后退（x 方向 -）
``left``     左横移（车体 y 方向 +，对应 ``wheels.py`` 的 Z 键）
``right``    右横移（y 方向 -，对应 ``wheels.py`` 的 X 键）
``rotl``     左旋（角速度 +）
``rotr``     右旋（角速度 -）
===========  ===============================================

退出码：0 = 全部步骤跑完；1 = 过流保护触发或运行异常；2 = 参数错误。
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import time

import numpy as np
from _common import add_common_args, open_bus, overcurrent_tripped, read_currents_ma

from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus, OperatingMode

# 三轮的电机 ID，与 alohamini.py 里 _make_base_motors 一致。
LEFT_WHEEL_ID = 8
BACK_WHEEL_ID = 9
RIGHT_WHEEL_ID = 10

WHEEL_NAMES = ("base_left_wheel", "base_back_wheel", "base_right_wheel")

# 底盘几何参数，与 wheels.py 的全局常量保持一致。
WHEEL_RADIUS = 0.05  # m
BASE_RADIUS = 0.125  # m，轮心到车体中心的距离
MAX_RAW = 3000  # raw 速度上限

DEFAULT_LIN_SPEED = 0.2  # m/s
DEFAULT_ANG_SPEED = 80.0  # deg/s
DEFAULT_RATE = 20.0  # Hz
PRINT_INTERVAL_S = 0.25

#: 动作名 -> (x 方向系数, y 方向系数, 角速度系数)。
#: 系数乘以 --lin-speed / --ang-speed 得到实际车体速度。
#: 符号约定与 wheels.py 的键盘映射完全一致。
ACTIONS: dict[str, tuple[float, float, float]] = {
    "fwd": (1.0, 0.0, 0.0),
    "back": (-1.0, 0.0, 0.0),
    "left": (0.0, 1.0, 0.0),
    "right": (0.0, -1.0, 0.0),
    "rotl": (0.0, 0.0, 1.0),
    "rotr": (0.0, 0.0, -1.0),
}


def degps_to_raw(degps: float) -> int:
    """Angular speed (deg/s) -> steps/s (-32767..+32767), no sign-bit encoding.

    与 ``examples/debug/wheels.py`` 中的同名函数一致。
    """
    steps_per_deg = 4096.0 / 360.0
    mag = int(round(abs(degps) * steps_per_deg))
    if mag > 0x7FFF:
        mag = 0x7FFF
    return -mag if degps < 0 else mag


def body_to_wheel_raw(
    x_cmd: float,
    y_cmd: float,
    theta_cmd_degps: float,
    *,
    wheel_radius: float = WHEEL_RADIUS,
    base_radius: float = BASE_RADIUS,
    max_raw: int = MAX_RAW,
) -> dict[str, int]:
    """Body velocity -> per-wheel raw speed commands.

    这段运动学是从 ``examples/debug/wheels.py`` 复制过来的独立实现。之所以不直接
    import ``wheels``，是因为那个模块在顶层 ``from pynput import keyboard``，在
    没有 X11 的机器上会直接 ImportError —— 而本脚本正是为了能在 headless 的
    树莓派上跑。**改动时请同步两处。**

    Args:
        x_cmd: 车体前后速度（m/s）。
        y_cmd: 车体左右横移速度（m/s）。
        theta_cmd_degps: 车体角速度（deg/s）。
        wheel_radius: 轮子半径（m）。
        base_radius: 轮心到车体中心的距离（m）。
        max_raw: raw 速度上限。

    Returns:
        电机名 -> raw 速度。
    """
    theta_rad = theta_cmd_degps * (np.pi / 180.0)
    vel = np.array([-x_cmd, -y_cmd, theta_rad])

    # 轮子安装角（从 +y 方向顺时针）。沿用 wheels.py 里的取值：注意那里的注释
    # 写的是 [300, 180, 60]，但代码实际用的是 [240, 0, 120] - 90，这里跟随代码。
    angles = np.radians(np.array([240, 0, 120]) - 90)
    m = np.array([[np.cos(a), np.sin(a), base_radius] for a in angles])

    v_lin = m.dot(vel)  # m/s
    w_rad = v_lin / wheel_radius  # rad/s
    w_degps = w_rad * (180.0 / np.pi)  # deg/s

    steps_per_deg = 4096.0 / 360.0
    raw_abs = np.abs(w_degps) * steps_per_deg
    peak = float(np.max(raw_abs)) if raw_abs.size else 0.0
    if peak > max_raw and peak > 1e-6:
        w_degps = w_degps * (max_raw / peak)

    raw = [degps_to_raw(v) for v in w_degps]
    return dict(zip(WHEEL_NAMES, raw, strict=True))


def parse_steps(spec: str) -> list[tuple[str, float]]:
    """Parse the ``--steps`` argument into (action, seconds) pairs.

    Args:
        spec: Comma-separated ``action:seconds`` items, e.g. ``fwd:1,back:1``.

    Returns:
        List of (action, duration_s) pairs.

    Raises:
        ValueError: If the spec is malformed or names an unknown action.
    """
    steps: list[tuple[str, float]] = []
    for raw_item in spec.split(","):
        item = raw_item.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"步骤 '{item}' 缺少时长，应写成 动作:秒数")
        name, _, duration = item.partition(":")
        name = name.strip().lower()
        if name not in ACTIONS:
            raise ValueError(f"未知动作 '{name}'，可用: {', '.join(ACTIONS)}")
        seconds = float(duration)
        if seconds <= 0:
            raise ValueError(f"步骤 '{name}' 的时长必须为正数")
        steps.append((name, seconds))
    if not steps:
        raise ValueError("--steps 不能为空")
    return steps


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AlohaMini mobile-base fixed action sequence test")
    add_common_args(parser)
    parser.add_argument(
        "--steps",
        type=str,
        default="fwd:1,back:1,left:1,right:1,rotl:1,rotr:1",
        help="动作序列，动作:秒数，逗号分隔。可用动作: " + ", ".join(ACTIONS),
    )
    parser.add_argument("--lin-speed", type=float, default=DEFAULT_LIN_SPEED, help="平移速度（m/s）")
    parser.add_argument("--ang-speed", type=float, default=DEFAULT_ANG_SPEED, help="旋转速度（deg/s）")
    parser.add_argument("--rate", type=float, default=DEFAULT_RATE, help="下发频率（Hz）")
    return parser.parse_args()


def stop_wheels(bus: FeetechMotorsBus) -> None:
    """Write zero velocity to all three wheels."""
    bus.sync_write("Goal_Velocity", dict.fromkeys(WHEEL_NAMES, 0), normalize=False)


def format_currents(currents: dict[str, float | None]) -> str:
    """Render a current reading dict as a single readable line."""
    parts = []
    for name in WHEEL_NAMES:
        value = currents.get(name)
        parts.append(f"{name}={'n/a' if value is None else format(value, '7.1f')} mA")
    return "  ".join(parts)


def main() -> int:
    args = parse_args()
    try:
        steps = parse_steps(args.steps)
    except ValueError as exc:
        print(f"参数错误: {exc}")
        return 2

    motors = {
        name: Motor(motor_id, "sts3215", MotorNormMode.RANGE_M100_100)
        for name, motor_id in zip(WHEEL_NAMES, (LEFT_WHEEL_ID, BACK_WHEEL_ID, RIGHT_WHEEL_ID), strict=True)
    }
    bus = FeetechMotorsBus(port=args.port, motors=motors)

    period = 1.0 / args.rate if args.rate > 0 else 0.05
    cutoff = args.current_cutoff

    print(f"连接 {args.port}，底盘三轮 ID={LEFT_WHEEL_ID}/{BACK_WHEEL_ID}/{RIGHT_WHEEL_ID}")
    print(f"动作序列: {args.steps}")
    print(
        f"平移 {args.lin_speed} m/s，旋转 {args.ang_speed} deg/s，频率 {args.rate} Hz，过流阈值 {cutoff} mA"
    )

    exit_code = 0
    try:
        with open_bus(bus, operating_mode=OperatingMode.VELOCITY, enable_torque=True):
            try:
                for action, seconds in steps:
                    x_factor, y_factor, th_factor = ACTIONS[action]
                    x_cmd = x_factor * args.lin_speed
                    y_cmd = y_factor * args.lin_speed
                    th_cmd = th_factor * args.ang_speed
                    wheel_cmds = body_to_wheel_raw(x_cmd, y_cmd, th_cmd)

                    print(f"\n=== {action} ({seconds:.1f} s) ===")
                    print(
                        f"  车体速度 x={x_cmd:+.3f} m/s  y={y_cmd:+.3f} m/s  "
                        f"theta={th_cmd:+.1f} deg/s  raw={wheel_cmds}"
                    )

                    deadline = time.perf_counter() + seconds
                    last_print = 0.0
                    while time.perf_counter() < deadline:
                        bus.sync_write("Goal_Velocity", wheel_cmds, normalize=False)

                        currents = read_currents_ma(bus, list(WHEEL_NAMES))
                        tripped = [n for n, cur in currents.items() if overcurrent_tripped(cur, cutoff)]
                        if tripped:
                            detail = ", ".join(f"{n}={currents[n]:.0f} mA" for n in tripped)
                            print(f"!! 过流保护触发: {detail}（阈值 {cutoff} mA），停止")
                            exit_code = 1
                            break

                        now = time.perf_counter()
                        if now - last_print >= PRINT_INTERVAL_S:
                            last_print = now
                            print(f"  {format_currents(currents)}", flush=True)

                        time.sleep(period)

                    stop_wheels(bus)
                    if exit_code:
                        break
                    print(f"  -> {action} 完成，已停车")
            finally:
                # 无论正常结束还是抛异常，都先停车再断连。
                with contextlib.suppress(Exception):
                    stop_wheels(bus)
    except Exception as exc:  # noqa: BLE001 - 调试脚本，异常直接报出来
        print(f"!! 运行异常: {exc}")
        return 1

    if exit_code == 0:
        print("\n全部步骤执行完毕。")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
