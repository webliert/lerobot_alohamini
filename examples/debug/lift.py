#!/usr/bin/env python3
"""升降台（lift axis，Feetech ID 11）测试脚本。

复用仓库自带的 ``LiftAxis``，做两件事：

1. **homing**：下行到底部硬限位，把触底位置定义为 0 mm；
2. **高度序列**：按给定的 mm 目标做闭环运动，逐步打印目标/实测高度与电流。

特点：

- **不依赖键盘**（不 import pynput），可在 SSH / 无 X11 的机器上直接跑；
- 先 homing，否则高度没有意义（EEPROM 里 ``Homing_Offset`` 仍是出厂值 0）；
- 用 mm 闭环而不是裸速度，自带软限位（0–600 mm）和下行地板保护（默认 5 mm）；
- 过流保护（默认 1000 mA 触发即停），结束时关闭力矩。

前置条件：Host 必须已经停掉（本脚本与 Host 争用同一个串口）。

用法::

    python examples/debug/lift.py --port /dev/am_arm_follower_left --heights 0,80,200,80,10

注意：``LiftAxis`` 的下行地板保护会让高度**低于 ``--descent-floor``**（默认 5 mm）的
目标无法下达。本脚本会直接把这些目标标成「被下行保护拦截」并跳过，
而不是空跑一轮再报一个误导性的「超时，未到位」。
homing 之后高度本来就是 0 mm，所以 ``--heights 0,...`` 里的第一项会被跳过，这是正常的。
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import time
from pathlib import Path

try:
    from _common import overcurrent_tripped, read_current_ma
except ModuleNotFoundError as exc:  # pragma: no cover - defensive: clearer error on a partial copy
    raise SystemExit(
        "缺少 _common.py：lift.py 依赖同目录的公共模块，"
        "请把 examples/debug/ 整个目录一起拷贝过去"
        "（rsync -av examples/debug/ pi5@10.168.1.110:~/lxy_ws/lerobot_alohamini/examples/debug/）"
    ) from exc

from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus, OperatingMode
from lerobot.robots.alohamini.lift_axis import LiftAxis, LiftAxisConfig

DEFAULT_PORT = "/dev/am_arm_follower_left"
LIFT_NAME = "lift_axis"
CURRENT_CUTOFF_MA = 1000.0
PRINT_INTERVAL_S = 0.25
DEFAULT_DESCENT_FLOOR_MM = 5.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AlohaMini lift-axis (servo ID 11) test")
    parser.add_argument("--port", type=str, default=DEFAULT_PORT, help="串口（左总线）")
    parser.add_argument("--motor-id", type=int, default=11, help="升降电机 ID")
    parser.add_argument("--model", type=str, default="sts3215", help="电机型号")
    parser.add_argument(
        "--lead-mm-per-rev", type=float, default=84.0, help="丝杠导程（mm/转），alohamini1 为 84"
    )
    parser.add_argument(
        "--heights", type=str, default="0,80,200,80,10", help="逗号分隔的目标高度（mm），最大 600"
    )
    parser.add_argument("--dwell", type=float, default=5.0, help="每个目标高度的最长停留时间（秒）")
    parser.add_argument("--rate", type=float, default=20.0, help="控制频率（Hz）")
    parser.add_argument(
        "--current-cutoff", type=float, default=CURRENT_CUTOFF_MA, help="过流保护阈值（mA），0 表示关闭"
    )
    parser.add_argument(
        "--descent-floor",
        type=float,
        default=DEFAULT_DESCENT_FLOOR_MM,
        help="下行地板保护高度（mm），低于它的目标会被跳过",
    )
    parser.add_argument("--skip-home", action="store_true", help="跳过 homing（仅在已经归零时使用）")
    parser.add_argument(
        "--show-registers",
        action="store_true",
        help=(
            "额外打印 Present_Velocity(实际速度) 与 Present_Load(负载)。"
            "默认关闭 —— 每多读一个寄存器都会拉长控制循环周期，"
            "改变打印间隔，进而改变「每采样多少 tick」的换算基准。"
        ),
    )
    return parser.parse_args()


def stop_lift(lift: LiftAxis, bus: FeetechMotorsBus) -> None:
    """Stop the axis, tolerating LiftAxis versions that predate ``stop()``.

    ``LiftAxis.stop()`` was added to the robot code after the first version of this
    script; on a machine with an older checkout the attribute is missing entirely,
    so fall back to writing the velocity register directly.
    """
    stop = getattr(lift, "stop", None)
    if callable(stop):
        stop()
        return
    bus.write("Goal_Velocity", LIFT_NAME, 0)


def script_fingerprint() -> str:
    """Return a short fingerprint of this script file.

    These debug scripts are edited on the PC and copied to the Pi by hand, so
    the Pi can easily end up running an older copy — and the symptom is a
    confusing "unrecognized arguments" instead of a clear "your copy is
    stale".  Printing the fingerprint at startup lets both sides be compared
    with a single ``sha256sum`` instead of reading the ``--help`` output.

    Returns:
        The first 8 hex characters of the SHA-256 digest of this file, or
        ``"unknown"`` when the file cannot be read.
    """
    try:
        return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:8]
    except OSError:
        return "unknown"


def read_raw_register(bus: FeetechMotorsBus, name: str) -> str:
    """Read one raw register and format it for printing.

    ``Present_Velocity`` is in ticks/s and ``Present_Load`` is a signed load
    value; both are read with ``normalize=False`` so the caller sees the raw
    register content (the sign is decoded by the bus for the registers that use
    sign-magnitude encoding).

    Args:
        bus: The connected bus.
        name: Control-table key, e.g. ``"Present_Velocity"``.

    Returns:
        The formatted value, or ``"n/a"`` when the read fails.
    """
    try:
        return str(int(bus.read(name, LIFT_NAME, normalize=False)))
    except Exception:
        return "n/a"


def main() -> None:
    args = parse_args()
    targets = [float(t) for t in args.heights.split(",") if t.strip()]

    motors = {LIFT_NAME: Motor(args.motor_id, args.model, MotorNormMode.DEGREES)}
    bus = FeetechMotorsBus(port=args.port, motors=motors)
    lift = LiftAxis(
        LiftAxisConfig(
            motor_id=args.motor_id,
            motor_model=args.model,
            lead_mm_per_rev=args.lead_mm_per_rev,
            descent_floor_mm=args.descent_floor,
        ),
        bus_left=bus,
        bus_right=None,
    )

    bus.connect(handshake=False)
    print(
        f"已连接 {args.port}；升降电机 ID={args.motor_id} ({args.model})，导程 {args.lead_mm_per_rev} mm/转"
    )
    print(
        f"lift.py 指纹 {script_fingerprint()}"
        "（PC 上用 `sha256sum examples/debug/lift.py | cut -c1-8` 比对，两端不一致说明 Pi 的拷贝是旧的）"
    )
    if not hasattr(lift, "stop"):
        print(
            "提示：当前 lerobot 里的 LiftAxis 没有 stop()，已走兼容路径；"
            "建议同步仓库代码（git pull），否则 homing 行程等诊断量也拿不到"
        )

    try:
        bus.write("Lock", LIFT_NAME, 0, normalize=False)
        bus.write("Operating_Mode", LIFT_NAME, OperatingMode.VELOCITY.value)
        bus.enable_torque(LIFT_NAME)
        lift.attach()
        lift.configure()

        if args.skip_home:
            print("跳过 homing（当前高度未归零，数值仅供观察）")
        else:
            print("\n=== homing：下行到底部硬限位 ===")
            started = time.perf_counter()
            lift.home()
            elapsed = time.perf_counter() - started
            travel_mm = getattr(lift, "home_travel_mm", None)
            springback_mm = getattr(lift, "home_springback_mm", None)
            print(f"homing 用时 {elapsed:.1f} s")
            if travel_mm is None:
                print("  （当前 lift_axis 版本没有 home_travel_mm：树莓派上的仓库代码需要同步）")
            else:
                print(f"  下行到硬限位行程 = {travel_mm:.1f} mm")
                if springback_mm is not None:
                    print(f"  释放力矩后回弹 = {springback_mm:.1f} mm（0 mm 参考点比机械底限高这么多）")
                if travel_mm < 1.0:
                    print("  >> 行程 < 1 mm：启动时升降台已经在底部，属正常现象，不是故障")
            print(f"homing 后高度 = {lift.get_height_mm():.1f} mm（应为 0）")
            # home() 结尾会写 Torque_Enable=0 释放电机，这里重新使能以便继续运动。
            bus.enable_torque(LIFT_NAME)

        period = 1.0 / args.rate
        for target in targets:
            if target < args.descent_floor:
                # 下行地板保护不允许走到这个高度；直接跳过，不要空跑一轮再误报"超时"。
                print(
                    f"\n=== 目标 {target:.1f} mm ===\n"
                    f"  -> 被下行保护拦截（目标 {target:.1f} mm < 下行地板 {args.descent_floor:.1f} mm），已跳过"
                )
                continue

            print(f"\n=== 目标 {target:.1f} mm ===")
            started = time.perf_counter()
            reached = False
            last_print = 0.0
            while time.perf_counter() - started < args.dwell:
                lift.apply_action({f"{LIFT_NAME}.height_mm": target})
                height_mm = lift.get_height_mm()
                current_ma = read_current_ma(bus, LIFT_NAME)
                now = time.perf_counter() - started
                if now - last_print >= PRINT_INTERVAL_S or abs(height_mm - target) <= 1.0:
                    last_print = now
                    ticks = bus.read("Present_Position", LIFT_NAME, normalize=False)
                    extra = ""
                    if args.show_registers:
                        extra = (
                            f"  实际速度={read_raw_register(bus, 'Present_Velocity')} tick/s"
                            f"  负载={read_raw_register(bus, 'Present_Load')}"
                        )
                    print(
                        f"  目标={target:7.1f}  实测={height_mm:8.1f} mm  "
                        f"ticks={ticks:4d}  电流="
                        f"{'n/a' if current_ma is None else f'{current_ma:7.1f}'} mA"
                        f"{extra}",
                        flush=True,
                    )
                if overcurrent_tripped(current_ma, args.current_cutoff):
                    print(f"!! 过流 {current_ma:.1f} mA >= {args.current_cutoff:.1f} mA，停止")
                    stop_lift(lift, bus)
                    return
                if abs(height_mm - target) <= 1.0:
                    reached = True
                    break
                time.sleep(period)
            stop_lift(lift, bus)
            print(f"  -> {'已到位' if reached else '超时，未到位'}")
    finally:
        with contextlib.suppress(Exception):
            stop_lift(lift, bus)
        bus.disconnect(disable_torque=True)
        print("\n已停止并断开连接。")


if __name__ == "__main__":
    main()
