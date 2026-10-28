#!/usr/bin/env python3
# axis.py - Overcurrent-protected axis demo (PORT parameterized)

import argparse
import time

from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus, OperatingMode
from lerobot.utils.keyboard_input import TerminalKeyListener, pynput_can_capture

try:
    from pynput import keyboard
except Exception:  # headless Linux has no X display for pynput to bind to
    keyboard = None

# ==================== Constants ==================== #
SERVO_ID = 11               # Servo ID
MODEL = "sts3215"           # Servo model
SPEED_DEGPS = 180.0         # Speed (deg/s)
CURRENT_CUTOFF = 1000.0      # Overcurrent threshold (mA)
SAMPLES_TO_TRIGGER = 2      # Consecutive samples before triggering
# ================================================= #

STEPS_PER_DEG = 4096.0 / 360.0  # ≈11.377 ticks/deg
TELEOP_KEYS = {"up": "u", "down": "j"}
pressed = {"up": False, "down": False}
running = True

# Terminal backend: a TTY reports key-down but never key-release, so a press only
# keeps the axis moving until this timeout expires without a new press.
KEY_HOLD_TIMEOUT_S = 0.4
_terminal_deadlines: dict[str, float] = {}


def degps_to_raw(degps: float) -> int:
    mag = int(round(abs(degps) * STEPS_PER_DEG))
    if mag > 0x7FFF:
        mag = 0x7FFF
    return -mag if degps < 0 else mag


def on_press(key):
    global running
    try:
        if key.char == TELEOP_KEYS["up"]:
            pressed["up"] = True
        elif key.char == TELEOP_KEYS["down"]:
            pressed["down"] = True
        elif key.char == "q":
            running = False
    except Exception:
        pass


def on_terminal_key(name: str) -> None:
    """Handle one key-down from the terminal.

    The controlling TTY cannot report key-release, so every press refreshes a
    deadline and the main loop clears the action once it expires.
    """
    global running
    if name == "esc":
        running = False
        return
    ch = name.lower()
    if ch == "q":
        running = False
        return
    for action, bind in TELEOP_KEYS.items():
        if ch == bind:
            pressed[action] = True
            _terminal_deadlines[action] = time.monotonic() + KEY_HOLD_TIMEOUT_S


def expire_terminal_keys() -> None:
    """Clear terminal-driven actions whose deadline expired (no new key-down)."""
    now = time.monotonic()
    for action, deadline in list(_terminal_deadlines.items()):
        if now >= deadline:
            pressed[action] = False
            _terminal_deadlines.pop(action, None)


def on_release(key):
    try:
        if key.char == TELEOP_KEYS["up"]:
            pressed["up"] = False
        elif key.char == TELEOP_KEYS["down"]:
            pressed["down"] = False
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="Lift-axis teleop with overcurrent cutoff")
    parser.add_argument("--port", default="/dev/ttyACM0", help="USB-TTL port, e.g. /dev/ttyACM0")
    args = parser.parse_args()

    name = "lift_axis"
    motors = {name: Motor(id=SERVO_ID, model=MODEL, norm_mode=MotorNormMode.RANGE_0_100)}
    bus = FeetechMotorsBus(port=args.port, motors=motors)

    bus.connect(handshake=False)
    print(f"[INFO] Connected on {args.port}")
    try:
        bus.disable_torque(name)
    except Exception:
        pass
    bus.write("Operating_Mode", name, OperatingMode.VELOCITY.value, normalize=False)
    try:
        bus.enable_torque(name)
    except Exception:
        pass

    if keyboard is not None and pynput_can_capture():
        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()
        print("[INFO] Keyboard: pynput global listener (hold a key to move).")
    else:
        listener = TerminalKeyListener(on_terminal_key)
        listener.start()
        print(
            "[INFO] No display detected - using terminal keyboard input.\n"
            f"[INFO]   Tap a key to move; it stops after {KEY_HOLD_TIMEOUT_S:.1f}s without a new press.\n"
            "[INFO]   Keys: U up / J down / Q or ESC quit."
        )
    print(f"[INFO] Ready. U ↑ / J ↓ / Ctrl-C to quit.")
    print(f"[INFO] Overcurrent cutoff: {CURRENT_CUTOFF} mA, trigger after {SAMPLES_TO_TRIGGER} samples")

    over_cnt = 0
    try:
        while running:
            # 0) Terminal backend: expire held keys when no new press arrived
            expire_terminal_keys()

            # 1) Read current
            current_ma = 0.0
            try:
                raw_current_ma = bus.read("Present_Current", name, normalize=False)
                if isinstance(raw_current_ma, tuple):
                    raw_current_ma = raw_current_ma[0]
                if raw_current_ma is None:
                    raw_current_ma = 0
                else:
                    current_ma = raw_current_ma * 6.5
                    print(f"[DEBUG] Present_Current={current_ma} mA")  # debug
            except Exception:
                raw_current_ma = 0

            # 2) Check for overcurrent
            if current_ma > CURRENT_CUTOFF:
                over_cnt += 1
            else:
                over_cnt = 0

            if over_cnt >= SAMPLES_TO_TRIGGER:
                print(f"\n[SAFETY] Overcurrent detected: {current_ma} mA ≥ {CURRENT_CUTOFF} mA")
                try:
                    bus.write("Goal_Velocity", name, 0, normalize=False)
                except Exception:
                    pass
                try:
                    bus.disable_torque(name)
                except Exception:
                    pass
                try:
                    bus.disconnect(disable_torque=True)
                except Exception:
                    pass
                return

            # 3) Velocity control
            if pressed["up"] and not pressed["down"]:
                raw = degps_to_raw(-SPEED_DEGPS)
            elif pressed["down"] and not pressed["up"]:
                raw = degps_to_raw(SPEED_DEGPS)
            else:
                raw = 0
            bus.write("Goal_Velocity", name, raw, normalize=False)

            time.sleep(0.03)
    except KeyboardInterrupt:
        print("\n[INFO] Stopping motor...")
        try:
            bus.write("Goal_Velocity", name, 0, normalize=False)
        except Exception:
            pass
    finally:
        try:
            bus.disconnect(disable_torque=False)
        except Exception:
            pass


if __name__ == "__main__":
    main()
