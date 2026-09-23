# M1-3 ｜ 时间与坐标：让两个传感器"说到一起去"

> **难度**：★★★
> **综合考察**：多传感器数据处理、TF2 坐标变换、时间同步、相机投影模型
> **本题分值权重**：30
> **现场接口契约**：见「接口契约」

---

## 场景

车上有一个**摄像头**和一个**激光雷达**，它们：

- 安装位置不同
- 采样频率不同
- 时间戳也不同

你要做的是——把激光雷达的点**投影到摄像头图像上**，让它们"看到同一个世界"。

这是多传感器融合的基石。

---

## 你拿到的数据

本目录提供 **`make_bag.py`**，生成一个离线可用的合成 rosbag：

```bash
python3 make_bag.py                      # 生成 ./sample_bag 与 ./extrinsics.yaml
python3 make_bag.py --frames 40 --seed 7 # 短一点的场景，文件更小
```

> `--frames` 是**雷达帧数**，默认 200（≈20 秒）。bag 体积约 **2.5 MB/帧**
> （主要是 640×480 的 RGB 图），200 帧约 500 MB，1000 帧约 2.5 GB。
> 现场实验用 100~300 帧足够，别生成几千帧把自己的盘写满。

bag 内含：

| 话题 | 类型 | 说明 |
| :-- | :-- | :-- |
| `/scan` | `sensor_msgs/LaserScan` | 2D 激光（180 线，-90°~90°） |
| `/camera/image_raw` | `sensor_msgs/Image` | `rgb8`，640×480 |
| `/camera/camera_info` | `sensor_msgs/CameraInfo` | 相机内参 |

> 如果你有真实 bag 也可以，只要话题名一致（内参改成你自己的）。

### ★ 关键：`extrinsics.yaml`

生成数据时会同时写出一份 `extrinsics.yaml`，记录**传感器安装位置与相机内参**：

```yaml
laser_link:
  parent: base_link
  xyz: [0.15, 0.0, 0.20]
camera_link:
  parent: base_link
  xyz: [0.10, 0.0, 0.30]
  rpy: [0.0, 0.0, 0.0]
camera_intrinsics:
  fx: 500.0
  fy: 500.0
  cx: 320.0
  cy: 240.0
```

**这是唯一的真值来源。**
你发布静态 TF、做投影时都必须**读它**，**不能在代码里写死数值**——

> **现场会换一组安装位置与内参重新生成数据**（例如 `--laser-z 0.45 --camera-z 0.75 --fx 420`）。
> 写死的实现会当场错得离谱。

---

## 任务

### 1. TF2 坐标树

建立并发布以下**静态 TF**：

```
map → odom → base_link → laser_link
                 ↓
            camera_link
```

树形关系为：`map → odom → base_link`，`base_link → laser_link`，`base_link → camera_link`。

变换数值**从 `extrinsics.yaml` 读取**。

### 2. 时间同步

同步 `/scan` 与 `/camera/image_raw`。

**你要先看清楚这两路数据的性质**：

| 话题 | 频率 | 时间戳特征 |
| :-- | :-- | :-- |
| `/scan` | **10 Hz** | 有抖动 |
| `/camera/image_raw` | **27 Hz** | 有抖动，且与雷达**不同源、不同相位** |

> ⚠️ **两路时间戳不会精确相等**。用 `TimeSynchronizer`（精确同步）
> 会**一帧都配不上**；你必须用 `ApproximateTimeSynchronizer`，
> 并且**把 `slop` 调到合适的大小**。

**这里有个真实的取舍**（文档里要写清）：

| `slop` | 配上的帧数 | 配对的时间差 |
| :-- | :-- | :-- |
| 太小（如 20ms） | 少，**大量雷达帧被丢掉** | 小（对齐精度高） |
| 中等（40~60ms） | 明显增多 | 中等 |
| 太大（>100ms） | 略增后饱和 | **变大**，可能配到"时间上不够近"的那帧 |

也就是说：**`slop` 越大，配对越多，但时间对齐越差**。
你要在"拿到足够多的帧"与"时间对齐足够准"之间选一个平衡点。

**建议做一次实验**：把 `slop` 从 20ms 扫到 150ms，
记录**每个取值配上的帧数**与**配对时间差的中位数**，用数据支撑你的选择。

> ⚠️ 注意 `ApproximateTimeSynchronizer` 是**一对一贪心匹配**，
> 不是"每个雷达帧各找最近的相机帧"——相机比雷达快 2.7 倍，
> 多余的相机帧会被丢弃，**这会让实际的时间差比"理论最近距离"大**。
> 别把"最近帧只差 10ms"当成"配对时间差就是 10ms"。
>
> 另外 `queue_size` 要设够大（相机 27Hz、雷达 10Hz，建议 ≥ 50），
> 否则早期的帧会因队列滚出而丢失。

### 3. 点云投影

- 把同步后的激光点（2D 激光，只有 x 和 y，z=0）投影到图像平面
- 每个激光点**按距离着色**：**近处红色，远处蓝色**
- 输出至少 **3 张不同时刻**的投影效果图

### 4. 时钟处理

- 回放 bag 时，必须正确处理 **`use_sim_time`** 参数
- 演示切换 `use_sim_time`（true ↔ false）时，系统行为会发生什么变化（**录屏记录**）

---

## 交付物

| 路径 | 内容 |
| :-- | :-- |
| `M1/M1-3/` | 你的投影节点代码 |
| `M1/M1-3/projection_*.png` | ≥3 张不同时刻的投影效果图 |
| `M1/M1-3/README.md` | 如何运行、TF 树说明、`use_sim_time` 对比结论 |
| `M1/M1-3/` | 录屏（`use_sim_time` true↔false）与 Git 历史 |

---

## 接口契约（现场按此验收）

**话题名**：

| 名称 | 类型 | 方向 |
| :-- | :-- | :-- |
| `/scan` | `sensor_msgs/LaserScan` | 输入（bag） |
| `/camera/image_raw` | `sensor_msgs/Image` | 输入（bag） |
| `/camera/camera_info` | `sensor_msgs/CameraInfo` | 输入（bag） |
| `/projection/debug_image` | `sensor_msgs/Image` | **输出**（带投影的图，`rgb8`） |
| `/tf_static` | `tf2_msgs/TFMessage` | 静态 TF |

**坐标系名**（必须一致）：`map` / `odom` / `base_link` / `laser_link` / `camera_link`

**参数**：

| 参数 | 默认值 | 说明 |
| :-- | :-- | :-- |
| `use_sim_time` | `false` | 回放 bag 时必须为 `true` |
| `extrinsics_file` | `extrinsics.yaml` | 外参/内参真值文件路径 |
| `output_dir` | `.` | 效果图输出目录 |
| `max_images` | `3` | 最多保存几张效果图 |

**验收时考官会做**：

1. **用非默认外参重新生成 bag**（如 `--laser-z 0.45 --camera-z 0.75 --fx 420`），
   让学生现场跑一遍——**写死数值的实现会失败**
2. `ros2 run tf2_tools view_frames` 或 `ros2 run tf2_ros tf2_echo base_link camera_link`
   确认 TF 树正确
3. 检查输出的 3 张图：投影点应落在合理区域（相机高于激光平面 → 点集中在图像**中心偏下**），
   且颜色随距离变化
4. 追问 `use_sim_time` 的对比结论

---

## 完成判断（现场）

现场展示实时演示图像（在**非默认**外参下）。

---

## 提示

- `ros2 bag play sample_bag --clock` 才会发布 `/clock`；节点必须设 `use_sim_time:=true`
- 静态 TF 用 `StaticTransformBroadcaster` 发布一次即可（但要注意用 `/tf_static`）
- 查变换用 `tf_buffer.lookup_transform(target, source, stamp)`，
  **注意参数顺序是 (target, source)**，写反了会得到逆变换
- 投影公式（光学坐标系下）：

  $$u = f_x \frac{X_{opt}}{Z_{opt}} + c_x, \qquad v = f_y \frac{Y_{opt}}{Z_{opt}} + c_y$$

- 验收时如果发现**投影点上下颠倒或左右镜像**，回去检查
  `camera_link`（机体轴）→ 光学坐标系那一步的符号
