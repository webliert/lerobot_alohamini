#!/usr/bin/env python3
"""AlohaMini 硬件调试脚本的公共工具。

这个模块只放**跨脚本复用**的东西，不含任何硬件语义：

- :func:`add_common_args` —— 统一的命令行参数；
- :func:`open_bus` —— 统一的总线生命周期（连接 → 关力矩/解锁 → 设模式 → 使能力矩 → 断开）；
- :func:`read_current_ma` —— 安全的电流读取（读失败返回 ``None``，不抛异常）。

全家桶共用同一套约定：

- ``--port`` 默认 ``/dev/am_arm_follower_left``：这是厂商 udev 别名，插拔后不会漂移
  （``/dev/ttyACM0`` 之类的编号会变）；
- 退出时统一 ``disconnect(disable_torque=True)``，除非显式要求保留力矩；
- 过流阈值默认 1000 mA。STS3215 的额定电流是 900 mA、堵转电流 2700 mA
  （见 ``alohamini.py`` 的 ``_MOTOR_CURRENT_RATINGS_MA``），1000 mA 略高于额定值。

前置条件：调试脚本与 Host 争用同一个串口，跑之前必须先停掉 Host。
"""

from __future__ import annotations

import argparse
import contextlib
from collections.abc import Iterator

from lerobot.motors.feetech import FeetechMotorsBus, OperatingMode

DEFAULT_PORT = "/dev/am_arm_follower_left"
DEFAULT_MODEL = "sts3215"
DEFAULT_CURRENT_CUTOFF_MA = 1000.0

#: Feetech 电流原始单位到 mA 的换算系数，与 ``alohamini.py`` 的
#: ``_CURRENT_MA_PER_RAW_UNIT`` 一致。
CURRENT_MA_PER_RAW_UNIT = 6.5


def add_common_args(
    parser: argparse.ArgumentParser,
    *,
    default_port: str = DEFAULT_PORT,
    with_motor_id: bool = False,
    with_model: bool = False,
    with_current_cutoff: bool = True,
) -> argparse.ArgumentParser:
    """Register the CLI flags shared by every debug script.

    Args:
        parser: The parser to add arguments to.
        default_port: Default serial device path.
        with_motor_id: Add ``--motor-id``.
        with_model: Add ``--model``.
        with_current_cutoff: Add ``--current-cutoff``.

    Returns:
        The same parser, for chaining.
    """
    parser.add_argument("--port", type=str, default=default_port, help="串口设备路径")
    if with_motor_id:
        parser.add_argument("--motor-id", type=int, help="电机 ID")
    if with_model:
        parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="电机型号")
    if with_current_cutoff:
        parser.add_argument(
            "--current-cutoff",
            type=float,
            default=DEFAULT_CURRENT_CUTOFF_MA,
            help="过流保护阈值（mA），0 表示关闭",
        )
    return parser


@contextlib.contextmanager
def open_bus(
    bus: FeetechMotorsBus,
    *,
    operating_mode: OperatingMode | None = None,
    enable_torque: bool | list[str] | None = None,
    disable_torque_first: bool = True,
    disable_torque_on_exit: bool = True,
    sync_goal_positions: bool = False,
) -> Iterator[FeetechMotorsBus]:
    """Open a Feetech bus with a fixed, reproducible lifecycle.

    The sequence is the one already used by ``examples/debug/motors.py``:

    1. ``connect(handshake=False)`` —— 不校验总线上其它 ID，因此只注册关心的电机即可；
    2. ``disable_torque`` —— 先关力矩，同时把 ``Lock`` 写成 0（解锁 EEPROM）；
    3. 写 ``Operating_Mode``（可选）；
    4. ``enable_torque``（可选）—— 会把 ``Lock`` 重新锁回 1。

    ``Goal_Position`` / ``Goal_Velocity`` / ``Operating_Mode`` 都在 SRAM 里，
    即使 EEPROM 被锁也能正常写。

    Args:
        bus: The bus to open.
        operating_mode: Mode to program on every registered motor.
        enable_torque: ``True`` enables every registered motor, a list enables only
            those, ``None``/``False`` leaves every motor's torque off.
        disable_torque_first: Whether to switch torque off before configuring.
            Pass ``False`` for read-only runs so the mechanism keeps holding its
            position (switching torque off would let the arm sag).
        disable_torque_on_exit: Whether to disable torque when the bus is closed.
        sync_goal_positions: Write every motor's current ``Present_Position`` into
            its ``Goal_Position`` right before enabling the torque.

            **Required whenever several motors are enabled in POSITION mode.**
            In that mode a Feetech servo drives towards its ``Goal_Position``
            register, and that register is SRAM: it keeps whatever value was
            written last (often the factory default) and is *not* refreshed by
            switching the torque on. Enabling the torque without this sync makes
            every untouched joint jump towards a stale goal.

    Yields:
        The connected bus.
    """
    bus.connect(handshake=False)
    try:
        if disable_torque_first:
            bus.disable_torque(list(bus.motors))
        if operating_mode is not None:
            for name in bus.motors:
                bus.write("Operating_Mode", name, operating_mode.value)
        if enable_torque is True:
            if sync_goal_positions:
                # 位置模式下伺服会朝 Goal_Position 走，而该寄存器是 SRAM，保留着上次的
                # 旧值（常常是出厂值）。使能前先把每个关节的当前位置写进去，
                # 这样使能后所有关节原地保持，只有被点动的那个会动。
                for name in bus.motors:
                    current = bus.read("Present_Position", name, normalize=False)
                    bus.write("Goal_Position", name, int(round(current)), normalize=False)
            bus.enable_torque(list(bus.motors))
        elif enable_torque:
            if sync_goal_positions:
                for name in enable_torque:
                    current = bus.read("Present_Position", name, normalize=False)
                    bus.write("Goal_Position", name, int(round(current)), normalize=False)
            bus.enable_torque(list(enable_torque))
        yield bus
    finally:
        bus.disconnect(disable_torque=disable_torque_on_exit)


def read_current_ma(bus: FeetechMotorsBus, motor: str) -> float | None:
    """Read one motor's current in mA, or ``None`` when the read fails.

    Args:
        bus: The bus to read from.
        motor: Motor name.

    Returns:
        Current in mA, or ``None`` if the register could not be read.
    """
    try:
        raw = bus.read("Present_Current", motor, normalize=False)
    except Exception:
        return None
    if raw is None:
        return None
    return float(raw) * CURRENT_MA_PER_RAW_UNIT


def read_currents_ma(bus: FeetechMotorsBus, motors: list[str]) -> dict[str, float | None]:
    """Read several motors' currents in mA with a single sync read.

    Args:
        bus: The bus to read from.
        motors: Motor names to read.

    Returns:
        Motor name -> current in mA. Values are ``None`` when the read failed.
    """
    try:
        raw = bus.sync_read("Present_Current", motors)
    except Exception:
        return dict.fromkeys(motors)
    return {
        name: (None if value is None else float(value) * CURRENT_MA_PER_RAW_UNIT)
        for name, value in raw.items()
    }


def overcurrent_tripped(current_ma: float | None, cutoff_ma: float) -> bool:
    """Whether the measured current exceeded the cutoff.

    Args:
        current_ma: Measured current, or ``None`` when the read failed.
        cutoff_ma: Cutoff threshold in mA. ``0`` disables the check.

    Returns:
        ``True`` when the current is at or above a non-zero cutoff.
    """
    if current_ma is None or cutoff_ma <= 0:
        return False
    return current_ma >= cutoff_ma
