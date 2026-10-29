#!/usr/bin/env python3
"""摄像头测试脚本（AlohaMini 的 head_front / head_top）。

用仓库自带的 ``OpenCVCamera`` 后端（而不是裸 ``cv2.VideoCapture``），因此测到的
就是采集时真正会走的那条链路。

默认**不开 GUI**（树莓派通常是 headless），只做测量与报告：

- **协商到的 fourcc** —— 必须显式读 ``CAP_PROP_FOURCC``：仓库的 ``_validate_fourcc``
  协商失败时**只 warning 不报错**，不自己读一遍就会以为配上了；
- **实测帧率** —— 连续 ``read()`` 计时。``read()`` 是"等下一帧"语义，天然同步到帧率；
- **实际分辨率 / 曝光 / 增益** —— 曝光增益走 ``cam.videocapture.set(...)``（仓库没有封装）；
- **画面亮度统计** —— 用来区分"正常画面"、"全黑"、"满屏噪点"。

``--save-dir`` 把若干帧存成 PNG（在整个时长内均匀取样）；``--show`` 才弹窗预览。

前置条件：**Host 必须已经停掉**（Host 独占相机，USB 带宽也是共享的）。

用法::

    # 测配置里的两台相机
    python examples/debug/cameras.py

    # 只测 head_top，并把 10 帧存到 /tmp/cam_frames
    python examples/debug/cameras.py --camera head_top --save-dir /tmp/cam_frames --frames 10

    # 测配置里没列出的设备（例如 head_back）
    python examples/debug/cameras.py --device /dev/am_camera_head_back

退出码：0 = 全部相机通过；1 = 有相机失败；2 = 参数错误。
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from lerobot.cameras.configs import Cv2Rotation
from lerobot.cameras.opencv.camera_opencv import OpenCVCamera
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.robots.alohamini.config_alohamini import alohamini_cameras_config

#: CLI 的旋转角度 -> 仓库的 ``Cv2Rotation``。
ROTATIONS: dict[int, Cv2Rotation] = {
    0: Cv2Rotation.NO_ROTATION,
    90: Cv2Rotation.ROTATE_90,
    180: Cv2Rotation.ROTATE_180,
    270: Cv2Rotation.ROTATE_270,
}

DEFAULT_FPS = 30
DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 480
DEFAULT_FOURCC = "MJPG"
DEFAULT_DURATION_S = 3.0
DEFAULT_SAVE_FRAMES = 3
DEFAULT_WARMUP_S = 1

#: 画面均值的判断阈值（0-255），低于此值认为"几乎全黑"。
DARK_MEAN = 5.0
#: 画面标准差的提示阈值（0-255），高于此值认为"噪点很多"。
NOISY_STD = 60.0


def available_cameras() -> tuple[str, ...]:
    """Names of the cameras declared by ``alohamini_cameras_config()``."""
    return tuple(alohamini_cameras_config().keys())


def fourcc_to_str(code: float) -> str:
    """Convert an OpenCV FOURCC code into its 4-character string.

    Args:
        code: Raw ``CAP_PROP_FOURCC`` value.

    Returns:
        The 4-character FOURCC, e.g. ``"MJPG"``.
    """
    value = int(code)
    return "".join(chr((value >> (8 * i)) & 0xFF) for i in range(4))


def build_configs(args: argparse.Namespace) -> dict[str, OpenCVCameraConfig]:
    """Build the camera configs to test, from the robot config plus CLI overrides.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Camera name -> config to test.

    Raises:
        ValueError: If the arguments contradict each other (e.g. ``--device``
            together with more than one camera).
    """
    configs: dict[str, OpenCVCameraConfig] = dict(alohamini_cameras_config())
    if args.camera != "all":
        if args.camera not in configs:
            raise ValueError(f"未知相机 '{args.camera}'，可用: {', '.join(configs)}")
        configs = {args.camera: configs[args.camera]}

    if args.device:
        if len(configs) != 1:
            raise ValueError("--device 只能用于单台相机，请配合 --camera <名字> 使用")
        name = next(iter(configs))
        configs[name] = dataclasses.replace(configs[name], index_or_path=args.device)

    overrides: dict[str, object] = {"warmup_s": args.warmup}
    if args.fps is not None:
        overrides["fps"] = args.fps
    if args.width is not None:
        overrides["width"] = args.width
    if args.height is not None:
        overrides["height"] = args.height
    if args.fourcc is not None:
        overrides["fourcc"] = args.fourcc.upper()
    if args.rotation is not None:
        overrides["rotation"] = ROTATIONS[args.rotation]
    return {name: dataclasses.replace(cfg, **overrides) for name, cfg in configs.items()}


def apply_exposure_gain(cam: OpenCVCamera, exposure: float | None, gain: float | None) -> None:
    """Set exposure and gain on the underlying ``cv2.VideoCapture``, if requested.

    Args:
        cam: The connected camera.
        exposure: Exposure value, or ``None`` to leave it untouched.
        gain: Gain value, or ``None`` to leave it untouched.
    """
    capture = cam.videocapture
    if capture is None:
        return
    if exposure is not None:
        capture.set(cv2.CAP_PROP_EXPOSURE, float(exposure))
    if gain is not None:
        capture.set(cv2.CAP_PROP_GAIN, float(gain))


def read_properties(cam: OpenCVCamera) -> dict[str, object]:
    """Read back the negotiated capture properties.

    Args:
        cam: The connected camera.

    Returns:
        A dict with the fourcc string, the reported resolution, and the
        exposure / gain values.
    """
    capture = cam.videocapture
    if capture is None:
        return {"fourcc": "?", "width": 0, "height": 0, "exposure": 0.0, "gain": 0.0}
    return {
        "fourcc": fourcc_to_str(capture.get(cv2.CAP_PROP_FOURCC)),
        "width": int(round(capture.get(cv2.CAP_PROP_FRAME_WIDTH))),
        "height": int(round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))),
        "exposure": float(capture.get(cv2.CAP_PROP_EXPOSURE)),
        "gain": float(capture.get(cv2.CAP_PROP_GAIN)),
    }


def frame_stats(frame: np.ndarray) -> tuple[float, float, tuple[float, float, float]]:
    """Summarize a frame's brightness.

    Args:
        frame: RGB frame, shape (H, W, 3).

    Returns:
        ``(mean, std, per_channel_means)``.
    """
    means = frame.mean(axis=(0, 1))
    return float(frame.mean()), float(frame.std()), (float(means[0]), float(means[1]), float(means[2]))


def save_frame(frame: np.ndarray, path: Path) -> bool:
    """Write one RGB frame to disk as a PNG.

    ``OpenCVCamera`` returns **RGB**, while ``cv2.imwrite`` expects **BGR**.

    Args:
        frame: RGB frame.
        path: Destination file path.

    Returns:
        ``True`` when the file was written.
    """
    bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    return bool(cv2.imwrite(str(path), bgr))


def run_camera(name: str, config: OpenCVCameraConfig, args: argparse.Namespace) -> bool:
    """Connect to one camera, measure it, and report.

    Args:
        name: Camera name, for display.
        config: The camera config to test.
        args: Parsed CLI arguments.

    Returns:
        ``True`` when the camera worked.
    """
    print(f"\n=== {name} ===")
    print(f"  设备路径 : {config.index_or_path}")

    cam = OpenCVCamera(config)
    try:
        cam.connect(warmup=True)
    except Exception as exc:  # noqa: BLE001 - 调试脚本，把连接失败原因原样打出来
        print(f"  !! 连接失败: {type(exc).__name__}: {exc}")
        return False

    try:
        apply_exposure_gain(cam, args.exposure, args.gain)
        props = read_properties(cam)

        requested_fourcc = (config.fourcc or "").upper()
        fourcc_ok = not requested_fourcc or props["fourcc"] == requested_fourcc
        print(f"  fourcc   : 请求 {requested_fourcc or '(自动)'}，实际 {props['fourcc']}")
        if not fourcc_ok:
            print(
                f"  !! fourcc 协商失败：实际是 {props['fourcc']} 而不是 {requested_fourcc}。"
                " YUYV 未压缩，640x480@30 约 18 MB/s/台，多台会挤爆 USB 带宽。"
            )
        print(f"  分辨率   : 采集 {props['width']}x{props['height']}（请求 {config.width}x{config.height}）")
        print(f"  曝光/增益: exposure={props['exposure']:.1f}  gain={props['gain']:.1f}")

        save_dir = Path(args.save_dir) if args.save_dir else None
        if save_dir:
            save_dir.mkdir(parents=True, exist_ok=True)

        frames = 0
        saved = 0
        last_frame = None
        show = args.show
        start = time.perf_counter()
        save_period = args.duration / args.frames if args.frames > 0 else 0.0
        next_save_at = 0.0

        while time.perf_counter() - start < args.duration:
            frame = cam.read()
            frames += 1
            last_frame = frame

            if (
                save_dir
                and save_period > 0
                and saved < args.frames
                and time.perf_counter() - start >= next_save_at
            ):
                path = save_dir / f"{name}_{saved:03d}.png"
                if save_frame(frame, path):
                    print(f"  已存帧   : {path}")
                else:
                    print(f"  !! 存帧失败: {path}")
                saved += 1
                next_save_at += save_period

            if show:
                try:
                    cv2.imshow(name, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
                    cv2.waitKey(1)
                except cv2.error as exc:
                    print(f"  !! 无法显示窗口（headless?）: {exc}\n     继续无 GUI 模式。")
                    show = False

        elapsed = time.perf_counter() - start
        fps = frames / elapsed if elapsed > 0 else 0.0
        print(f"  实测 FPS : {fps:.1f}（{frames} 帧 / {elapsed:.2f} s，请求 {config.fps}）")

        if last_frame is None:
            print("  !! 一帧都没读到")
            return False

        mean, std, means = frame_stats(last_frame)
        print(
            f"  画面统计 : mean={mean:.1f} std={std:.1f}  RGB=({means[0]:.1f}, {means[1]:.1f}, {means[2]:.1f})"
        )
        if mean < DARK_MEAN:
            print("  !! 画面几乎全黑：检查曝光、镜头盖，或是不是选错了设备节点")
        elif std > NOISY_STD:
            print("  !! 画面噪点很多：多半是树莓派 ISP 的伪节点（/dev/video19-35），不是真相机")

        if show:
            with contextlib.suppress(cv2.error):
                cv2.destroyAllWindows()

        ok = frames > 0
        print(f"  结论     : {'OK' if ok else '失败'}")
        return ok
    except Exception as exc:  # noqa: BLE001 - 调试脚本，异常直接报出来
        print(f"  !! 运行异常: {type(exc).__name__}: {exc}")
        return False
    finally:
        if cam.is_connected:
            cam.disconnect()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AlohaMini camera test")
    parser.add_argument(
        "--camera",
        type=str,
        choices=("all", *available_cameras()),
        default="all",
        help="要测哪台相机，默认 all（配置里的全部）",
    )
    parser.add_argument("--device", type=str, help="覆盖设备路径（需配合 --camera 指定单台）")
    parser.add_argument("--fps", type=int, help="覆盖帧率")
    parser.add_argument("--width", type=int, help="覆盖宽度")
    parser.add_argument("--height", type=int, help="覆盖高度")
    parser.add_argument("--fourcc", type=str, help="覆盖 fourcc，如 MJPG / YUYV")
    parser.add_argument("--rotation", type=int, choices=sorted(ROTATIONS), help="覆盖旋转角度")
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP_S, help="连接后预热秒数")
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION_S, help="测量时长（秒）")
    parser.add_argument(
        "--frames", type=int, default=DEFAULT_SAVE_FRAMES, help="保存的帧数（需要 --save-dir）"
    )
    parser.add_argument("--save-dir", type=str, help="把帧存成 PNG 的目录")
    parser.add_argument("--exposure", type=float, help="曝光值（不设则不动）")
    parser.add_argument("--gain", type=float, help="增益值（不设则不动）")
    parser.add_argument("--show", action="store_true", help="弹出预览窗口（需要图形界面）")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.duration <= 0:
        print("参数错误: --duration 必须为正数")
        return 2

    try:
        configs = build_configs(args)
    except ValueError as exc:
        print(f"参数错误: {exc}")
        return 2

    print(f"要测的相机: {', '.join(configs)}")
    if args.save_dir:
        print(f"存帧目录: {args.save_dir}（{args.frames} 帧）")

    results = {name: run_camera(name, cfg, args) for name, cfg in configs.items()}

    failed = [name for name, ok in results.items() if not ok]
    print("\n=== 汇总 ===")
    for name, ok in results.items():
        print(f"  {name}: {'OK' if ok else '失败'}")
    if failed:
        print(f"\n失败: {', '.join(failed)}")
        return 1
    print("\n全部相机通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
