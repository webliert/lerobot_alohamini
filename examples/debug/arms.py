#!/usr/bin/env python3
"""从臂（follower arm）测试脚本（Feetech STS3215，ID 1-6）。

两种模式：

``read``（默认，只读不动）
    逐关节打印当前位置（ticks / 角度）、EEPROM 里的真实限位、实测电流，并检查
    ``Homing_Offset`` 判断**标定有没有生效**。这是标定 + 断电重启之后的验收手段。

``jog``（单关节点动）
    ``--joint`` 指定一个关节，``--delta-deg`` 指定相对当前的角度增量（可正可负）。
    目标位置会被夹到 EEPROM 的 ``Min/Max_Position_Limit`` 之内，只动这一个关节。

前置条件：**Host 必须已经停掉**（本脚本与 Host 争用同一个串口）。

用法::

    # 只读：看关节角、限位、标定状态
    python examples/debug/arms.py --port /dev/am_arm_follower_left --arm left

    # 点动：肩关节往上抬 5 度
    python examples/debug/arms.py --port /dev/am_arm_follower_left --arm left \
        --mode jog --joint shoulder_pan --delta-deg 5

角度换算与仓库一致（``motors_bus.py`` 的 ``_normalize``）::

    deg = (tick - (min_limit + max_limit) / 2) * 360 / 4095

即**零点 = 标定记录的 ROM 中点**，不是关节的机械零位。限位值直接读 EEPROM，
因为伺服真正强制的就是 EEPROM 里那两个值，写超限目标会被伺服自己裁掉。

退出码：0 = 正常；1 = 过流 / 运行异常；2 = 参数错误。
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import time

from _common import add_common_args, open_bus, overcurrent_tripped, read_current_ma

from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus, OperatingMode

# so-arm-5dof 的关节表，与 alohamini.py 的 _ARM_PROFILES["so-arm-5dof"] 一致。
# 注意：不要用 examples/debug/motors.py 里那份注释掉的 ID 对照表，那是 SO-101 的
# 布局（gripper=8），和 AlohaMini 的 ID 1-6 不一样。
JOINTS: tuple[tuple[str, int], ...] = (
    ("shoulder_pan", 1),
    ("shoulder_lift", 2),
    ("elbow_flex", 3),
    ("wrist_flex", 4),
    ("wrist_roll", 5),
    ("gripper", 6),
)

GRIPPER = "gripper"

# STS3215 每圈 4096 tick；仓库的换算式用的是 resolution - 1。
RESOLUTION = 4096
MAX_RES = RESOLUTION - 1

DEFAULT_SETTLE_S = 5.0
DEFAULT_TOLERANCE_DEG = 1.0
DEFAULT_DELTA_DEG = 5.0
POLL_RATE = 20.0


def motor_names(side: str) -> dict[str, str]:
    """Map joint names to bus motor names for the given arm side.

    Args:
        side: ``"left"`` or ``"right"``.

    Returns:
        Joint name -> motor name.
    """
    prefix = f"arm_{side}_"
    return {joint: f"{prefix}{joint}" for joint, _ in JOINTS}


def ticks_to_degrees(tick: float, min_tick: float, max_tick: float) -> float:
    """Convert a raw position to degrees, using the EEPROM limits as the reference.

    与 ``motors_bus.py`` 的 ``_normalize`` 里 DEGREES 分支同式。

    Args:
        tick: Raw position in ticks.
        min_tick: ``Min_Position_Limit`` from EEPROM.
        max_tick: ``Max_Position_Limit`` from EEPROM.

    Returns:
        Angle in degrees, zero at the middle of the recorded range of motion.
    """
    mid = (min_tick + max_tick) / 2.0
    return (tick - mid) * 360.0 / MAX_RES


def read_limits(bus: FeetechMotorsBus, motor: str) -> tuple[float, float] | None:
    """Read the EEPROM position limits of one motor.

    Args:
        bus: The bus to read from.
        motor: Motor name.

    Returns:
        ``(min_tick, max_tick)``, or ``None`` when the read failed.
    """
    try:
        min_tick = bus.read("Min_Position_Limit", motor, normalize=False)
        max_tick = bus.read("Max_Position_Limit", motor, normalize=False)
    except Exception:
        return None
    if min_tick is None or max_tick is None:
        return None
    return float(min_tick), float(max_tick)


def read_homing_offset(bus: FeetechMotorsBus, motor: str) -> int:
    """Read ``Homing_Offset`` from EEPROM (protocol 0 / STS3215 only).

    Args:
        bus: The bus to read from.
        motor: Motor name.

    Returns:
        The stored homing offset, or 0 when it is unavailable.
    """
    if getattr(bus, "protocol_version", 0) != 0:
        return 0
    try:
        value = bus.read("Homing_Offset", motor, normalize=False)
    except Exception:
        return 0
    return 0 if value is None else int(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AlohaMini follower-arm test")
    add_common_args(parser)
    parser.add_argument("--arm", type=str, choices=("left", "right"), default="left", help="哪条手臂")
    parser.add_argument("--mode", type=str, choices=("read", "jog"), default="read", help="模式")
    parser.add_argument(
        "--joint",
        type=str,
        choices=tuple(joint for joint, _ in JOINTS),
        help="要点动的关节（jog 模式必填）",
    )
    parser.add_argument(
        "--delta-deg", type=float, default=DEFAULT_DELTA_DEG, help="点动角度增量（度，可为负）"
    )
    parser.add_argument("--settle", type=float, default=DEFAULT_SETTLE_S, help="点动最长等待时间（秒）")
    parser.add_argument(
        "--tolerance-deg", type=float, default=DEFAULT_TOLERANCE_DEG, help="判定到位的角度误差（度）"
    )
    return parser.parse_args()


def run_read(bus: FeetechMotorsBus, names: dict[str, str], side: str) -> int:
    """Print a per-joint state table and report whether calibration is in effect.

    Args:
        bus: The connected bus.
        names: Joint name -> motor name.
        side: Arm side, for display.

    Returns:
        Process exit code.
    """
    print(f"=== {side} 臂 ===")
    print(f"{'关节':<26} {'ticks':>7} {'deg':>8}   {'限位(ticks)':>17}   {'限位(deg)':>15}  {'电流(mA)':>9}")
    print("-" * 96)

    all_zero_offsets = True
    for joint, _ in JOINTS:
        motor = names[joint]
        limits = read_limits(bus, motor)
        try:
            tick = float(bus.read("Present_Position", motor, normalize=False))
        except Exception:
            tick = float("nan")

        if limits is None:
            print(f"{motor:<26} {'?':>7} {'?':>8}   {'读取失败':>17}")
            continue

        min_tick, max_tick = limits
        deg = ticks_to_degrees(tick, min_tick, max_tick)
        lo_deg = ticks_to_degrees(min_tick, min_tick, max_tick)
        hi_deg = ticks_to_degrees(max_tick, min_tick, max_tick)
        current = read_current_ma(bus, motor)

        offset = read_homing_offset(bus, motor)
        if offset != 0:
            all_zero_offsets = False

        extra = ""
        if joint == GRIPPER and max_tick > min_tick:
            opening = (tick - min_tick) / (max_tick - min_tick) * 100.0
            extra = f"  开合={opening:5.1f}%"

        print(
            f"{motor:<26} {tick:>7.0f} {deg:>+8.2f}   "
            f"[{min_tick:>6.0f},{max_tick:>6.0f}]   [{lo_deg:>+6.1f},{hi_deg:>+6.1f}]  "
            f"{'n/a' if current is None else format(current, '9.1f')}{extra}"
        )

    if all_zero_offsets:
        print("\n!! 所有关节的 Homing_Offset 都是 0 —— 从臂**尚未标定**（或标定后没断电重启）。")
        print("   标定命令: python -m lerobot.robots.alohamini.alohamini_calibrate --robot_model alohamini1")
        print("   标定后必须给双臂断电重启，Homing_Offset 才会生效。")
    else:
        print("\n标定状态: 已标定（存在非零 Homing_Offset）。")
    return 0


def run_jog(bus: FeetechMotorsBus, names: dict[str, str], args: argparse.Namespace) -> int:
    """Move a single joint by a relative angle.

    Args:
        bus: The connected bus.
        names: Joint name -> motor name.
        args: Parsed CLI arguments.

    Returns:
        Process exit code.
    """
    joint = args.joint
    motor = names[joint]
    limits = read_limits(bus, motor)
    if limits is None:
        print(f"!! 读取 {motor} 的 EEPROM 限位失败，无法保证安全")
        return 1
    min_tick, max_tick = limits

    try:
        current_tick = float(bus.read("Present_Position", motor, normalize=False))
    except Exception as exc:
        print(f"!! 读取 {motor} 当前位置失败: {exc}")
        return 1

    target_tick = current_tick + args.delta_deg * (MAX_RES / 360.0)
    target_tick = max(min_tick, min(max_tick, target_tick))

    cur_deg = ticks_to_degrees(current_tick, min_tick, max_tick)
    tgt_deg = ticks_to_degrees(target_tick, min_tick, max_tick)
    print(f"=== 点动 {motor} ===")
    print(
        f"  当前 {current_tick:.0f} ticks ({cur_deg:+.2f}°)，"
        f"目标 {target_tick:.0f} ticks ({tgt_deg:+.2f}°)，"
        f"增量 {args.delta_deg:+.2f}°"
    )
    if abs(target_tick - current_tick) < 1:
        print("  目标被限位夹住，没有可执行的位移")
        return 0

    deadline = time.perf_counter() + args.settle
    period = 1.0 / POLL_RATE
    reached = False
    exit_code = 0
    try:
        while time.perf_counter() < deadline:
            bus.write("Goal_Position", motor, int(round(target_tick)), normalize=False)

            current = read_current_ma(bus, motor)
            if overcurrent_tripped(current, args.current_cutoff):
                print(f"!! 过流保护触发: {motor}={current:.0f} mA（阈值 {args.current_cutoff} mA），停止")
                exit_code = 1
                break

            try:
                actual = float(bus.read("Present_Position", motor, normalize=False))
            except Exception:
                actual = current_tick
            if abs(ticks_to_degrees(actual, min_tick, max_tick) - tgt_deg) <= args.tolerance_deg:
                reached = True
                break
            time.sleep(period)
    finally:
        # 正常结束时回到原点，避免手离开后关节还停在偏移位置；
        # 过流时不再下发任何位移指令，直接退出让上层关力矩。
        if exit_code == 0:
            with contextlib.suppress(Exception):
                bus.write("Goal_Position", motor, int(round(current_tick)), normalize=False)
                time.sleep(0.3)
                print(f"  -> 已回到起点 {current_tick:.0f} ticks ({cur_deg:+.2f}°)")

    if reached:
        print(f"  -> 已到位 {target_tick:.0f} ticks ({tgt_deg:+.2f}°)")
    elif exit_code == 0:
        print(f"  -> 超时未到位（{args.settle} s）")
    return exit_code


def main() -> int:
    args = parse_args()
    if args.mode == "jog" and not args.joint:
        print("参数错误: jog 模式必须用 --joint 指定关节")
        return 2

    names = motor_names(args.arm)
    motors = {
        names[joint]: Motor(motor_id, "sts3215", MotorNormMode.RANGE_M100_100) for joint, motor_id in JOINTS
    }
    bus = FeetechMotorsBus(port=args.port, motors=motors)

    print(f"连接 {args.port}，{args.arm} 臂关节 ID={[jid for _, jid in JOINTS]}")

    try:
        if args.mode == "read":
            # 只读：完全不碰力矩，机械臂保持当前姿态不掉下来。
            with open_bus(
                bus,
                operating_mode=None,
                enable_torque=None,
                disable_torque_first=False,
                disable_torque_on_exit=False,
            ):
                return run_read(bus, names, args.arm)

        # 点动：给整条手臂使能。位置模式下伺服会朝 Goal_Position 走，而该寄存器
        # 是 SRAM、保留着上次的旧值 —— 所以必须让 open_bus 在使能前把每个关节的
        # 当前位置写进 Goal_Position（sync_goal_positions=True），否则没被点动的
        # 关节会朝陈旧目标猛跳。随后只给目标关节写新的 Goal_Position。
        with open_bus(
            bus,
            operating_mode=OperatingMode.POSITION,
            enable_torque=True,
            disable_torque_first=True,
            disable_torque_on_exit=True,
            sync_goal_positions=True,
        ):
            return run_jog(bus, names, args)
    except Exception as exc:  # noqa: BLE001 - 调试脚本，异常直接报出来
        print(f"!! 运行异常: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
