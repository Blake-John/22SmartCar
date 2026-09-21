#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""图像处理与控制节点 —— 终端2 运行

订阅:
    /camera/image_raw    640x480, 目标 30Hz（接受 bgr8 / mono8）
发布:
    /perception/result   640x480 mono8
    /control/cmd         Twist, 20Hz

运行:
    python3 image_proc.py

观测:
    ros2 topic hz    /perception/result
    ros2 topic hz    /control/cmd
    ros2 topic delay /perception/result
"""

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from geometry_msgs.msg import Twist
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image

IMAGE_IN = "/camera/image_raw"
IMAGE_OUT = "/perception/result"
CMD_OUT = "/control/cmd"

IMAGE_WIDTH = 640
IMAGE_HEIGHT = 480
WORK_WIDTH = 1280
WORK_HEIGHT = 720
CONTROL_HZ = 20.0


def make_sub_qos():
    """图像链路的 QoS 配置。

    depth 表示"最多缓存多少条尚未处理的消息"。
    """
    return QoSProfile(
        depth=30,
        reliability=ReliabilityPolicy.RELIABLE,
        history=HistoryPolicy.KEEP_LAST,
    )


class ImageProc(Node):
    def __init__(self):
        super().__init__("image_proc")
        self.sub = self.create_subscription(
            Image, IMAGE_IN, self.on_image, make_sub_qos()
        )
        self.pub = self.create_publisher(Image, IMAGE_OUT, make_sub_qos())
        self.bridge = CvBridge()

    def on_image(self, msg):
        gray = self.bridge.imgmsg_to_cv2(msg, desired_encoding="mono8")
        gray = np.array(gray, copy=True)

        large = cv2.resize(
            gray, (WORK_WIDTH, WORK_HEIGHT), interpolation=cv2.INTER_LINEAR
        )

        height, width = large.shape
        brightened = np.zeros(large.shape, dtype=np.uint8)
        for y in range(height):
            for x in range(width):
                value = int(large[y, x]) + 20
                if value > 255:
                    value = 255
                brightened[y, x] = value

        contrasted = np.zeros(brightened.shape, dtype=np.uint8)
        for y in range(height):
            for x in range(width):
                value = (int(brightened[y, x]) - 128) * 3 // 2 + 128
                if value < 0:
                    value = 0
                if value > 255:
                    value = 255
                contrasted[y, x] = value

        small = cv2.resize(
            contrasted, (IMAGE_WIDTH, IMAGE_HEIGHT), interpolation=cv2.INTER_LINEAR
        )
        payload = np.array(small, dtype=np.uint8, copy=True)

        out = self.bridge.cv2_to_imgmsg(payload, encoding="mono8")
        out.header.stamp = msg.header.stamp
        out.header.frame_id = msg.header.frame_id
        self.pub.publish(out)


class ControlLoop(Node):
    def __init__(self):
        super().__init__("control_loop")
        self.pub = self.create_publisher(Twist, CMD_OUT, make_sub_qos())
        self.timer = self.create_timer(1.0 / CONTROL_HZ, self.on_timer)

    def on_timer(self):
        cmd = Twist()
        cmd.linear.x = 0.10
        cmd.angular.z = 0.05
        self.pub.publish(cmd)


def main():
    rclpy.init()
    nodes = [ImageProc(), ControlLoop()]
    executor = SingleThreadedExecutor()
    for node in nodes:
        executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        executor.shutdown()
        for node in nodes:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
