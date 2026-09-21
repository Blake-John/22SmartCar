#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M1-4 任务二的"故障演练样本"（可选练习，不计分）

它做两件事：
  1. 正常发布一个话题（假装是车载感知节点），证明它确实在工作
  2. 以一定概率触发**真实的段错误（SIGSEGV）**，模拟"几分钟崩一次"

用途：让学生对**一个确定的故障**走一遍完整的记录流程：
  现象 -> 定位 -> 根因 -> 修复 -> 验证，作为 任务二的能力校准样本。
  它与 任务一的两个文件互不依赖。

练什么：
  - 崩溃后**自动重启**（launch 的 respawn / systemd Restart=always）
  - 崩溃后**状态能恢复**（不是重启完就瘫着）
  - 抓到崩溃证据（core dump、dmesg、日志）

用法：
    python3 crash_worker.py                       # 默认平均 90 秒崩一次
    python3 crash_worker.py --mean-interval 20    # 加快，便于调试
    python3 crash_worker.py --fault-rate 1.0      # 每次都崩
"""

import argparse
import ctypes
import random
import sys
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


def segfault():
    """
    故意触发真实的段错误。
    用 ctypes 直接解引用空指针 —— 和 C/C++ 里的野指针崩溃是同一种现象。
    """
    ctypes.string_at(0)


class CrashWorker(Node):
    def __init__(self, mean_interval, fault_rate):
        super().__init__("crash_worker")
        self.pub = self.create_publisher(String, "/hw/heartbeat", 10)
        self.mean_interval = mean_interval
        self.fault_rate = fault_rate
        self.n = 0

        # 每次心跳时，以 fault_rate 的概率决定"这一轮要不要崩"
        self.timer = self.create_timer(1.0, self.tick)

        self.get_logger().info(
            "crash_worker 启动：平均 %.0f 秒崩溃一次（每次心跳崩溃概率 %.2f）"
            % (mean_interval, fault_rate))

    def tick(self):
        self.n += 1
        msg = String()
        msg.data = "heartbeat %d" % self.n
        self.pub.publish(msg)

        if random.random() < self.fault_rate:
            self.get_logger().error(
                "[CRASH] 触发崩溃（第 %d 次心跳）—— 这是个段错误！" % self.n)
            sys.stdout.flush()
            segfault()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mean-interval", type=float, default=90.0,
                    help="平均多少秒崩一次")
    ap.add_argument("--fault-rate", type=float, default=None,
                    help="每次心跳（1秒）触发崩溃的概率；默认按 mean-interval 推算")
    args = ap.parse_args()

    # 每秒一次心跳，故每次心跳的崩溃概率 ≈ 1/mean_interval
    rate = args.fault_rate
    if rate is None:
        rate = max(0.0, min(1.0, 1.0 / max(args.mean_interval, 1.0)))

    rclpy.init()
    node = CrashWorker(args.mean_interval, rate)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            node.destroy_node()
            rclpy.shutdown()
        except Exception:                                  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
