from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional, Protocol
import time

class BusLike(Protocol):
    motors: Dict[str, object]
    def read(self, item: str, name: str) -> float: ...
    def write(self, item: str, name: str, value: float) -> None: ...
    def sync_write(self, item: str, values: Dict[str, float]) -> None: ...

from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import OperatingMode


@dataclass
class LiftAxisConfig:
    enabled: bool = True
    name: str = "lift_axis"
    bus: str = "left"                 # "left" or "right" (select which existing bus to use)
    motor_id: int = 11
    motor_model: str = "sts3215"

    # Mechanical conversion (1 rev = 360° = 4096 ticks); adjust for your leadscrew/gear ratio
    lead_mm_per_rev: float = 84      # Lead screw pitch (mm per revolution)
    output_gear_ratio: float = 1.0    # Servo angle → lead screw angle transmission ratio
    soft_min_mm: float = 0.0
    soft_max_mm: float = 600        # Lift travel range
    descent_floor_mm: float = 5.0   # Hard lower guard: refuse downward motion below this height

    # Homing (drive downward to hard stop → rebound slightly)
    home_down_speed: int = 1300      # Downward target velocity in velocity mode
    home_stall_current_ma: int = 300  # Stall current threshold; used when no current feedback
    home_backoff_deg: float = 5.0

    # Velocity closed-loop gains
    kp_vel: float = 300              # (target speed units / mm)
    v_max: int = 1300                # Velocity limit (depends on motor)
    on_target_mm: int = 1.0          # Position tolerance (mm)
    
    dir_sign: int = -1               # +1 no inversion; -1 invert direction
    step_mm: float = 2              # Step per key press (mm)



class LiftAxis:
    """Z-axis controller merged into existing left/right bus (velocity mode + multi-turn counter + mm-level closed loop)"""
    def __init__(
        self,
        cfg: LiftAxisConfig,
        bus_left: Optional[BusLike],
        bus_right: Optional[BusLike],
    ):
        self.cfg = cfg
        self._bus = (bus_left if cfg.bus == "left" else bus_right)
        self.enabled = bool(cfg.enabled and self._bus is not None)
        self._ticks_per_rev = 4096.0
        self._deg_per_tick = 360.0 / self._ticks_per_rev
        self._mm_per_deg = (cfg.lead_mm_per_rev * cfg.output_gear_ratio) / 360.0

        # Multi-turn tick tracking
        self._last_tick: float = 0.0
        self._extended_ticks: float = 0.0  # cumulative total
        # Zero reference (extended angle)
        self._z0_deg: float = 0.0

        # Homing diagnostics, filled in by home().
        self.home_travel_mm: float | None = None
        self.home_springback_mm: float | None = None
        self.home_stall_ma: float | None = None
        self.home_stopped_by: str | None = None

        self._configured = False

    def attach(self) -> None:
        if not self.enabled: return
        if self.cfg.name not in self._bus.motors:
            self._bus.motors[self.cfg.name] = Motor(self.cfg.motor_id, self.cfg.motor_model, MotorNormMode.DEGREES)

    def configure(self) -> None:
        if not self.enabled: return
        if self._configured: return   
        self._bus.write("Operating_Mode", self.cfg.name, OperatingMode.VELOCITY.value)
        self._last_tick = float(self._bus.read("Present_Position", self.cfg.name, normalize=False))
        self._extended_ticks = 0.0
        self._configured = True

    def _update_extended_ticks(self) -> None:
        if not self.enabled: return
        cur = float(self._bus.read("Present_Position", self.cfg.name, normalize=False))  # 0..4095
        delta = cur - self._last_tick
        half = self._ticks_per_rev * 0.5
        if   delta > +half: delta -= self._ticks_per_rev
        elif delta < -half: delta += self._ticks_per_rev
        self._extended_ticks += delta
        self._last_tick = cur

    def _extended_deg(self) -> float:
        return self.cfg.dir_sign * self._extended_ticks * self._deg_per_tick 

    def get_height_mm(self) -> float:
        if not self.enabled: return 0.0
        self._update_extended_ticks()
        raw_mm = (self._extended_deg() - self._z0_deg) * self._mm_per_deg
        #print(f"[lift_axis.get_height_mm] raw_mm={raw_mm:.2f}, extended_deg={self._extended_deg():.2f}, z0_deg={self._z0_deg:.2f}")  # debug
        return raw_mm
    
    # Homing (down to hard stop → rebound, set z=0mm)
    def home(self, use_current: bool = True) -> None:
        """Drive the axis down to the hard stop and use it as the 0 mm reference.

        Diagnostics written by this method:

        - ``home_travel_mm``: how far the axis travelled *down* before it stopped.
          Positive = travelled down. The sign follows ``dir_sign``: with the
          default ``dir_sign=-1`` a downward run gives a positive number.
        - ``home_springback_mm``: how far the axis rose again after the torque was
          released. Positive = sprang back up.
        - ``home_stall_ma``: the current measured when the axis stopped.
        - ``home_stopped_by``: why the loop ended -- ``"current"`` (the stall
          current was reached), ``"no_motion"`` (the axis did not move, e.g. it
          was already sitting on the stop) or ``"timeout"`` (30 s without a stop;
          the zero reference is then unreliable).

        The 0 mm reference is taken *after* the torque release, so it sits
        ``home_springback_mm`` above the mechanical stop.
        """
        if not self.enabled: return
        self.configure()
        name = self.cfg.name
        start_deg = self._extended_deg()
        # Move downward
        v_down = self.cfg.home_down_speed
        self._bus.write("Goal_Velocity", name, v_down)
        stuck = 0
        # "Did it move?" is judged over a 300 ms window: at the homing speed a
        # single 50 ms sample is only ~12 ticks, so a per-sample threshold would
        # false-trigger on jitter and abort the homing early.
        window_start_tick = int(self._bus.read("Present_Position", name, normalize=False))
        window_samples = 0
        stop_reason = "timeout"
        stall_ma = 0.0
        for _ in range(600):  # ~30s @50ms
            time.sleep(0.05)
            self._update_extended_ticks()
            now_tick = self._last_tick
            moved = abs(now_tick - window_start_tick) > 4
            window_samples += 1
            if window_samples >= 6:  # 300 ms
                window_start_tick = now_tick
                window_samples = 0
            cur_ma = 0
            raw_cur_ma = 0
            if use_current:
                try:
                    raw_cur_ma = int(self._bus.read("Present_Current", name, normalize=False))
                    cur_ma = raw_cur_ma * 6.5
                    print(f"[lift_axis.home] Present_Current={cur_ma} mA")  # debug
                    print(f"[lift_axis.home] Present_Position={now_tick} ticks")  # debug

                except Exception: cur_ma = 0
            stalled_by_current = use_current and cur_ma >= self.cfg.home_stall_current_ma
            if stalled_by_current or not moved:
                print(f"[lift_axis.home] Stalled at current={cur_ma} mA, moved={moved}")  # debug
                stuck += 1
                if stalled_by_current:
                    stop_reason = "current"
                    stall_ma = cur_ma
                elif not moved:
                    stop_reason = "no_motion"
            else:
                stuck = 0
            if stuck >= 2: break
        # Snapshot the position at the hard stop *before* releasing the torque: the
        # released axis is pushed back up by the load, so the stop position can only
        # be measured while the motor still holds it. The snapshot feeds the
        # diagnostics below; the 0 mm reference itself is taken after the release.
        self._update_extended_ticks()
        stop_deg = self._extended_deg()
        self.home_travel_mm = (start_deg - stop_deg) * self._mm_per_deg
        self.home_stall_ma = stall_ma
        self.home_stopped_by = stop_reason
        # Goal_Velocity is SRAM and survives a torque disable: without this write the
        # homing command stays latched and re-enabling the torque slams the axis
        # into the hard stop.
        self._bus.write("Goal_Velocity", name, 0)
        self._bus.write("Torque_Enable", name, 0)
        print("Disable torque output (motor will be released)")
        time.sleep(1)

        self._update_extended_ticks()
        self.home_springback_mm = (self._extended_deg() - stop_deg) * self._mm_per_deg
        self._z0_deg = self._extended_deg()
        print("Extended ticks after homing:", self._extended_ticks)
        h_now = self.get_height_mm()
        print(f"[home] set-zero z0_deg={self._z0_deg:.2f}, height_now={h_now:.2f} mm")  # should be ~0 here
        if stop_reason == "timeout":
            print(
                "[home] !! 30 s 内没有检测到底部限位，0 mm 参考点不可信"
                "（检查力矩是否使能、限位位置，或 home_stall_current_ma）"
            )



    # Lightweight coupling with action/obs
    def contribute_observation(self, obs: Dict[str, float]) -> None:
        """Export convenient observation fields: height_mm and velocity"""
        if not self.enabled: return
        obs[f"{self.cfg.name}.height_mm"] = self.get_height_mm()
        try:
            obs[f"{self.cfg.name}.vel"] = int(self._bus.read("Present_Velocity", self.cfg.name, normalize=False))
        except Exception:
            pass

    def apply_action(
        self, action: Dict[str, float], current_height_mm: float | None = None
    ) -> Dict[str, float]:
        """
        Supports two action keys:
        - f"{name}.height_mm": target height (mm)  (recommended)
        - f"{name}.vel"      : target velocity     (advanced)
        """
        #print(f"[lift_axis.apply_action] action={action}")  # debug
        if not self.enabled:
            return {}
        key_h = f"{self.cfg.name}.height_mm"
        key_v = f"{self.cfg.name}.vel"
        if key_h in action:
            target_mm = min(
                max(float(action[key_h]), self.cfg.soft_min_mm),
                self.cfg.soft_max_mm,
            )
            cur_mm = self.get_height_mm() if current_height_mm is None else current_height_mm
            err = target_mm - cur_mm
            if abs(err) <= self.cfg.on_target_mm:
                v_cmd = 0
            else:
                v_cmd = self.cfg.kp_vel * err
                if v_cmd > self.cfg.v_max:
                    v_cmd = self.cfg.v_max
                elif v_cmd < -self.cfg.v_max:
                    v_cmd = -self.cfg.v_max
            # Descent floor guard
            if v_cmd < 0 and cur_mm <= self.cfg.descent_floor_mm:
                print(
                    f"[LiftAxis] Descent guard active: height {cur_mm:.1f} mm is at or below "
                    f"the floor limit ({self.cfg.descent_floor_mm} mm). "
                    "Downward motion blocked to prevent motor stall."
                )
                v_cmd = 0
            # Soft boundary limit
            if (cur_mm >= self.cfg.soft_max_mm and v_cmd > 0) or (
                cur_mm <= self.cfg.soft_min_mm and v_cmd < 0
            ):
                v_cmd = 0
            self._bus.write("Goal_Velocity", self.cfg.name, int(self.cfg.dir_sign * v_cmd))
            return {key_h: target_mm}
        elif key_v in action:
            # Direct velocity clears height target
            v = int(action[key_v])
            v = max(-self.cfg.v_max, min(self.cfg.v_max, v))
            # Limit if already at boundary
            try:
                cur_mm = self.get_height_mm() if current_height_mm is None else current_height_mm
                # Descent floor guard
                if v < 0 and cur_mm <= self.cfg.descent_floor_mm:
                    print(
                        f"[LiftAxis] Descent guard active: height {cur_mm:.1f} mm is at or below "
                        f"the floor limit ({self.cfg.descent_floor_mm} mm). "
                        "Downward motion blocked to prevent motor stall."
                    )
                    v = 0
                elif (cur_mm >= self.cfg.soft_max_mm and v > 0) or (cur_mm <= self.cfg.soft_min_mm and v < 0):
                    v = 0
            except Exception:
                pass
            self._bus.write("Goal_Velocity", self.cfg.name, v * self.cfg.dir_sign)
            return {key_v: float(v)}
        
        # ticks = int(self._bus.read("Present_Position", self.cfg.name, normalize=False))
        # print(f"[lift_axis] Z-axis ticks: {ticks}")
        # print(f"[lift_axis] Z-axis height: {self.get_height_mm():.2f} mm")
        return {}

    def stop(self) -> None:
        """Stop any ongoing lift motion in velocity mode."""
        if not self.enabled:
            return
        self._bus.write("Goal_Velocity", self.cfg.name, 0)
