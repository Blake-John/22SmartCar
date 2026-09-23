#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M1-3 样例数据生成器（学生用）

生成一个**离线可用的合成 rosbag**，内含：
    /scan                sensor_msgs/LaserScan
    /camera/image_raw    sensor_msgs/Image          (rgb8)
    /camera/camera_info  sensor_msgs/CameraInfo     (含内参)

同时写出一份 `extrinsics.yaml`，记录**传感器安装位置与相机内参**。
之所以自己造数据，是因为公开数据集体积大、要联网下载，
而 M1-3 考的是 **时间同步 + 坐标变换 + 投影**，不是"会不会下数据"。

★ 重要：`extrinsics.yaml` 是**唯一的真值来源**。
  你发布静态 TF、做投影时都必须读它，**不能在代码里写死数值**——
  现场会换一组安装位置与内参重新生成，写死就会错。

用法：
    python3 make_bag.py                          # 生成 ./sample_bag + extrinsics.yaml
    python3 make_bag.py --frames 40 --out my_bag
    python3 make_bag.py --seed 123               # 换个场景
    python3 make_bag.py --laser-z 0.35 --camera-z 0.55   # 改安装高度（现场会用）

回放：
    ros2 bag play sample_bag --clock
"""

import argparse
import json
import math
import os
import shutil
import sys

import numpy as np

try:
    import rosbag2_py
    from rclpy.serialization import serialize_message
    from builtin_interfaces.msg import Time
    from sensor_msgs.msg import LaserScan, Image, CameraInfo
    from std_msgs.msg import Header
except ImportError as e:
    print("[ERROR] 需要 ROS2 环境。请先 source /opt/ros/humble/setup.bash",
          file=sys.stderr)
    print("        (%s)" % e, file=sys.stderr)
    sys.exit(2)

# =============================================================================
#  默认场景参数（可用命令行覆盖）
# =============================================================================

FRAME_MAP = "map"
FRAME_ODOM = "odom"
FRAME_BASE = "base_link"
FRAME_LASER = "laser_link"
FRAME_CAMERA = "camera_link"

# 激光雷达相对 base_link
DEF_LASER_XYZ = (0.15, 0.0, 0.20)
# 相机相对 base_link
DEF_CAMERA_XYZ = (0.10, 0.0, 0.30)
DEF_CAMERA_RPY = (0.0, 0.0, 0.0)

# 相机内参
IMG_W, IMG_H = 640, 480
DEF_FX = DEF_FY = 500.0
DEF_CX, DEF_CY = IMG_W / 2.0, IMG_H / 2.0

# 激光参数
N_BEAMS = 180
ANGLE_MIN = -math.pi / 2
ANGLE_MAX = math.pi / 2
RANGE_MIN, RANGE_MAX = 0.10, 8.0

# ── 两个传感器**独立**的时间线（这是本题"时间同步"的关键）──
# 真机上激光雷达与相机是两套独立时钟，频率不同、相位不同、还有抖动。
# 如果两者时间戳完全相同，精确同步(TimeSynchronizer)就够用，
# ApproximateTimeSynchronizer 的考点就消失了。
SCAN_HZ = 10.0            # 激光雷达 10Hz
# 相机频率**刻意不用 30Hz**：30 是 10 的整数倍，两者相位会锁死，
# 导致"雷达帧到最近相机帧"的间隔恒为半个相机周期(≈16.7ms)，
# 学生把 slop 设成 17ms 就一劳永逸 —— slop 就失去了调优空间。
# 取 27Hz（非整数倍）让相位每帧漂移，两路时间差在一个相机周期内连续变化，
# slop 才有真实的调优空间（具体数值请自己扫一遍 slop 实测，不要照抄）。
CAMERA_HZ = 27.0
SCAN_JITTER_NS = 3_000_000      # 雷达时间戳抖动 ±3ms
CAMERA_JITTER_NS = 2_000_000    # 相机时间戳抖动 ±2ms
T0_NS = 0

TOPIC_SCAN = "/scan"
TOPIC_IMAGE = "/camera/image_raw"
TOPIC_INFO = "/camera/camera_info"


def _dump_yaml(obj, path):
    try:
        import yaml
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(obj, f, allow_unicode=True, sort_keys=False)
    except ImportError:
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False, indent=2))


def stamp(ns):
    return Time(sec=int(ns // 10**9), nanosec=int(ns % 10**9))


def _timeline(hz, duration_s, rng, jitter_ns=0, phase_s=0.0):
    """生成一个话题的**独立时间线**（纳秒，递增）。

    模拟真实传感器：标称周期 + 相位偏移 + 随机抖动。
        t_i = (phase + i / hz + jitter_i) * 1e9

    jitter 用正态分布（std = jitter_ns/3，等效 ±jitter_ns 的 3σ 范围），
    并做单调性修正 —— 时间戳必须严格递增，否则 message_filters 会错乱。
    """
    n = max(1, int(round(duration_s * hz)))
    out = []
    prev = -1
    for i in range(n):
        base = (phase_s + i / hz) * 1e9
        if jitter_ns > 0:
            base += rng.normal(0.0, jitter_ns / 3.0)
        t = int(round(base))
        if t <= prev:               # 保证严格递增（抖动可能造成回退）
            t = prev + 1
        out.append(t)
        prev = t
    return out


def make_ranges(rng, k):
    """生成一帧"墙面"距离：正前方墙 + 两侧墙 + 一个移动凸起。"""
    ranges = []
    for i in range(N_BEAMS):
        a = ANGLE_MIN + i * (ANGLE_MAX - ANGLE_MIN) / (N_BEAMS - 1)
        deg = math.degrees(a)
        if abs(deg) <= 25.0:
            r = 6.0 + 0.15 * math.sin(k * 0.4)
        elif abs(deg) <= 55.0:
            r = 3.2
        else:
            r = 1.6
        bump_deg = -40.0 + (k % 10) * 8.0
        if abs(deg - bump_deg) < 4.0:
            r -= 1.0
        r += rng.normal(0, 0.01)
        ranges.append(float(max(RANGE_MIN, min(RANGE_MAX, r))))
    return ranges


def make_image(rng, k):
    """生成一帧图像：天空/地面渐变 + 几个彩色方块（便于肉眼确认投影）。"""
    img = np.zeros((IMG_H, IMG_W, 3), dtype=np.uint8)
    img[: IMG_H // 2, :, :] = (60, 70, 90)
    grad = np.linspace(120, 40, IMG_H - IMG_H // 2).astype(np.uint8)
    for c in range(3):
        img[IMG_H // 2:, :, c] = grad[:, None]
    for (bx, by, bw, bh, col) in [
        (80, 300, 60, 60, (220, 60, 60)),
        (300, 260, 70, 70, (60, 220, 60)),
        (520, 320, 50, 50, (60, 60, 220)),
    ]:
        x0 = min(IMG_W - bw, bx + (k % 5) * 3)
        img[by:by + bh, x0:x0 + bw] = col
    img = np.clip(img.astype(np.int16) + rng.integers(-6, 7, img.shape), 0, 255)
    return img.astype(np.uint8)


def build(outdir, frames, seed, laser_xyz, camera_xyz, camera_rpy,
          fx, fy, cx, cy):
    rng = np.random.default_rng(seed)
    if os.path.exists(outdir):
        shutil.rmtree(outdir)

    writer = rosbag2_py.SequentialWriter()
    writer.open(
        rosbag2_py.StorageOptions(uri=outdir, storage_id="sqlite3"),
        rosbag2_py.ConverterOptions(
            input_serialization_format="cdr",
            output_serialization_format="cdr",
        ),
    )
    writer.create_topic(rosbag2_py.TopicMetadata(
        name=TOPIC_SCAN, type="sensor_msgs/msg/LaserScan",
        serialization_format="cdr"))
    writer.create_topic(rosbag2_py.TopicMetadata(
        name=TOPIC_IMAGE, type="sensor_msgs/msg/Image",
        serialization_format="cdr"))
    writer.create_topic(rosbag2_py.TopicMetadata(
        name=TOPIC_INFO, type="sensor_msgs/msg/CameraInfo",
        serialization_format="cdr"))

    # ── 两个话题各自生成"时间线"（频率不同 + 独立抖动 + 相位错开）──
    # 相位错开：相机不从 t=0 开始，而是偏移半个相机周期，
    # 避免"第一个雷达帧恰好撞上第一个相机帧"这种巧合配对。
    duration_s = float(frames) / SCAN_HZ        # 以雷达帧数定义总时长

    scan_times = _timeline(SCAN_HZ, duration_s, rng,
                           jitter_ns=SCAN_JITTER_NS, phase_s=0.0)
    cam_times = _timeline(CAMERA_HZ, duration_s, rng,
                          jitter_ns=CAMERA_JITTER_NS,
                          phase_s=0.5 / CAMERA_HZ)

    # 按时间顺序写入（rosbag 要求写入顺序递增，否则回放时序会乱）
    events = ([(t, "scan") for t in scan_times] +
              [(t, "camera") for t in cam_times])
    events.sort(key=lambda e: e[0])

    n_scan = n_cam = 0
    for t_ns, kind in events:
        ts = stamp(t_ns)
        if kind == "scan":
            scan = LaserScan()
            scan.header = Header()
            scan.header.frame_id = FRAME_LASER
            scan.header.stamp = ts
            scan.angle_min = ANGLE_MIN
            scan.angle_max = ANGLE_MAX
            scan.angle_increment = (ANGLE_MAX - ANGLE_MIN) / (N_BEAMS - 1)
            scan.time_increment = 0.0
            scan.scan_time = 1.0 / SCAN_HZ
            scan.range_min = RANGE_MIN
            scan.range_max = RANGE_MAX
            scan.ranges = make_ranges(rng, n_scan)
            writer.write(TOPIC_SCAN, serialize_message(scan), t_ns)
            n_scan += 1
        else:
            arr = make_image(rng, n_cam)
            img = Image()
            img.header = Header()
            img.header.frame_id = FRAME_CAMERA
            img.header.stamp = ts
            img.height, img.width = IMG_H, IMG_W
            img.encoding = "rgb8"
            img.is_bigendian = 0
            img.step = IMG_W * 3
            img.data = arr.tobytes()
            writer.write(TOPIC_IMAGE, serialize_message(img), t_ns)

            info = CameraInfo()
            info.header = Header()
            info.header.frame_id = FRAME_CAMERA
            info.header.stamp = ts
            info.height, info.width = IMG_H, IMG_W
            info.distortion_model = "plumb_bob"
            info.d = [0.0, 0.0, 0.0, 0.0, 0.0]
            info.k = [fx, 0.0, cx, 0.0, fy, cy, 0.0, 0.0, 1.0]
            info.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
            info.p = [fx, 0.0, cx, 0.0, 0.0, fy, cy, 0.0, 0.0, 0.0, 1.0, 0.0]
            writer.write(TOPIC_INFO, serialize_message(info), t_ns)
            n_cam += 1

    writer.close()
    stats = {"n_scan": n_scan, "n_cam": n_cam,
             "scan_times": scan_times, "cam_times": cam_times}

    cfg = {
        "frames": {
            "map": FRAME_MAP, "odom": FRAME_ODOM, "base_link": FRAME_BASE,
            "laser_link": FRAME_LASER, "camera_link": FRAME_CAMERA,
        },
        "laser_link": {
            "parent": FRAME_BASE,
            "xyz": [float(v) for v in laser_xyz],
            "rpy": [0.0, 0.0, 0.0],
        },
        "camera_link": {
            "parent": FRAME_BASE,
            "xyz": [float(v) for v in camera_xyz],
            "rpy": [float(v) for v in camera_rpy],
        },
        "camera_intrinsics": {
            "width": IMG_W, "height": IMG_H,
            "fx": float(fx), "fy": float(fy),
            "cx": float(cx), "cy": float(cy),
            "distortion_model": "plumb_bob",
            "d": [0.0, 0.0, 0.0, 0.0, 0.0],
        },
        "scan": {
            "n_beams": N_BEAMS,
            "angle_min_deg": math.degrees(ANGLE_MIN),
            "angle_max_deg": math.degrees(ANGLE_MAX),
            "range_min": RANGE_MIN, "range_max": RANGE_MAX,
            "rate_hz": SCAN_HZ,
            "jitter_ms": SCAN_JITTER_NS / 1e6,
        },
        "camera": {
            "width": IMG_W, "height": IMG_H, "encoding": "rgb8",
            "rate_hz": CAMERA_HZ,
            "jitter_ms": CAMERA_JITTER_NS / 1e6,
        },
    }
    return cfg, stats


def main():
    ap = argparse.ArgumentParser(description="生成 M1-3 合成 rosbag + 外参文件")
    ap.add_argument("--out", default="sample_bag", help="输出目录")
    ap.add_argument("--frames", type=int, default=200,
                    help="激光雷达帧数（默认 200 ≈ 20s，约 500MB）。"
                         "帧数决定 bag 体积：约 2.5MB/帧")
    ap.add_argument("--seed", type=int, default=2025, help="随机种子")
    ap.add_argument("--extrinsics", default="extrinsics.yaml",
                    help="外参文件输出路径")
    ap.add_argument("--laser-z", type=float, default=DEF_LASER_XYZ[2],
                    help="激光雷达安装高度 z（米）")
    ap.add_argument("--laser-x", type=float, default=DEF_LASER_XYZ[0],
                    help="激光雷达安装前向偏移 x（米）")
    ap.add_argument("--camera-z", type=float, default=DEF_CAMERA_XYZ[2],
                    help="相机安装高度 z（米）")
    ap.add_argument("--camera-x", type=float, default=DEF_CAMERA_XYZ[0],
                    help="相机安装前向偏移 x（米）")
    ap.add_argument("--camera-pitch-deg", type=float, default=0.0,
                    help="相机绕 y 轴旋转角（度，右手定则）。0=朝向车头正前方；"
                         "正值使相机略微向下俯视")
    ap.add_argument("--fx", type=float, default=DEF_FX, help="相机内参 fx")
    ap.add_argument("--fy", type=float, default=DEF_FY, help="相机内参 fy")
    ap.add_argument("--cx", type=float, default=DEF_CX, help="相机内参 cx")
    ap.add_argument("--cy", type=float, default=DEF_CY, help="相机内参 cy")
    args = ap.parse_args()

    laser_xyz = (args.laser_x, 0.0, args.laser_z)
    camera_xyz = (args.camera_x, 0.0, args.camera_z)
    camera_rpy = (0.0, math.radians(args.camera_pitch_deg), 0.0)

    cfg, stats = build(args.out, args.frames, args.seed, laser_xyz,
                       camera_xyz, camera_rpy, args.fx, args.fy,
                       args.cx, args.cy)
    _dump_yaml(cfg, args.extrinsics)

    print("已生成 rosbag : %s" % args.out)
    print("已生成外参    : %s" % args.extrinsics)
    dur = args.frames / SCAN_HZ
    print("  时长      : %.1f s" % dur)
    print("  激光帧数  : %d  (%.1f Hz, 抖动 ±%.1f ms)"
          % (stats["n_scan"], SCAN_HZ, SCAN_JITTER_NS / 1e6))
    print("  相机帧数  : %d  (%.1f Hz, 抖动 ±%.1f ms)"
          % (stats["n_cam"], CAMERA_HZ, CAMERA_JITTER_NS / 1e6))
    print()
    print("  ★ 两个话题的时间戳**独立**（频率不同 + 抖动），")
    print("    精确同步(TimeSynchronizer)配不上，必须用 ApproximateTimeSynchronizer。")
    print("  话题      : %s  %s  %s" % (TOPIC_SCAN, TOPIC_IMAGE, TOPIC_INFO))
    print("  激光      : %d 线, %.0f° ~ %.0f°, frame_id=%s"
          % (N_BEAMS, math.degrees(ANGLE_MIN), math.degrees(ANGLE_MAX),
             FRAME_LASER))
    print("  图像      : %dx%d rgb8, frame_id=%s" % (IMG_W, IMG_H, FRAME_CAMERA))
    print("  安装      : laser_link xyz=%s  camera_link xyz=%s rpy=%s"
          % (list(laser_xyz), list(camera_xyz), list(camera_rpy)))
    print("  内参      : fx=%.1f fy=%.1f cx=%.1f cy=%.1f"
          % (args.fx, args.fy, args.cx, args.cy))
    print()
    print("回放（务必带 --clock，并在节点上设 use_sim_time:=true）:")
    print("  ros2 bag play %s --clock" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
