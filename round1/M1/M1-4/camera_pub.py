#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""相机节点 —— 终端1 运行

发布:
    /camera/image_raw    640x480 bgr8, 目标 30Hz

运行:
    python3 camera_pub.py

说明:
    本节点每 3 秒在终端打印一次**自己真实的发布频率**，
    请以这个数字为准判断"输入够不够快"。
"""

import time

import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image

IMAGE_IN = "/camera/image_raw"

IMAGE_WIDTH = 640
IMAGE_HEIGHT = 480
CAMERA_HZ = 30.0
QUEUE_DEPTH = 30


def make_qos():
    return QoSProfile(
        depth=QUEUE_DEPTH,
        reliability=ReliabilityPolicy.RELIABLE,
        history=HistoryPolicy.KEEP_LAST,
    )


class CameraSim(Node):
    def __init__(self):
        super().__init__("camera_sim")
        self.pub = self.create_publisher(Image, IMAGE_IN, make_qos())
        self.bridge = CvBridge()
        self.seq = 0
        self.count = 0
        self.t_start = time.monotonic()
        self.timer = self.create_timer(1.0 / CAMERA_HZ, self.on_timer)
        self.report_timer = self.create_timer(3.0, self.report)

    def capture(self):
        frame = np.zeros((IMAGE_HEIGHT, IMAGE_WIDTH, 3), dtype=np.uint8)
        base = self.seq
        for y in range(IMAGE_HEIGHT):
            row = frame[y]
            off = (y * 13 + base) & 0xFF
            for x in range(IMAGE_WIDTH):
                value = (x + off) & 0xFF
                row[x, 0] = value
                row[x, 1] = value
                row[x, 2] = 60
        return frame

    def on_timer(self):
        self.seq += 1
        frame = self.capture()

        msg = self.bridge.cv2_to_imgmsg(frame, encoding="bgr8")
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "camera_link"
        self.pub.publish(msg)
        self.count += 1

    def report(self):
        elapsed = time.monotonic() - self.t_start
        if elapsed <= 0:
            return
        self.get_logger().info(
            "[CAMERA] 已发布 %d 帧, 平均 %.2f Hz (目标 %.1f Hz)"
            % (self.count, self.count / elapsed, CAMERA_HZ)
        )


def main():
    rclpy.init()
    node = CameraSim()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
