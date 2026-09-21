# M1-3 ｜ 时间与坐标：让两个传感器"说到一起去"

> **难度**：★★★
> **综合考察**：多传感器数据处理、TF2 坐标变换、时间同步、相机投影模型
> **本题分值权重**：30
> **现场判分接口**：见「接口契约」

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
python3 make_bag.py --frames 40 --seed 7 # 换个场景
```

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

用 `message_filters.TimeSynchronizer`（或 `ApproximateTimeSynchronizer`）
同步 `/scan` 与 `/camera/image_raw`。

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

## 评分要点

| 维度 | 分值 | 看什么 |
| :-- | :--: | :-- |
| 任务完成 | 40 | TF 树正确、时间同步、投影几何正确、按距离着色、≥3 张图 |
| 过程证据 | 20 | 提交是否分步；是否记录过"投影全跑偏"的排查过程 |
| 工程规范 | 10 | 外参**不硬编码**、参数化、README 可复现 |
| 权衡与判断 | 10 | 为什么用 Approximate 而不是 Exact？丢帧怎么办？ |
| 答辩 | 20 | 见下 |

---

## 常见追问（提前想清楚）

- **`camera_link` 和相机光学坐标系有什么区别？** 为什么投影要用光学坐标系？
  （提示：`camera_link` 是 x 前 / y 左 / z 上；光学坐标系是 z 前 / x 右 / y 下）
- 如果你直接用 `camera_link` 下的 z 当深度，会发生什么？
  （现象：**投影命中 0 个点**，因为所有点的 z 都在相机平面附近甚至为负）
- 为什么用 `ApproximateTimeSynchronizer`？两个传感器频率不同会怎样？
- `use_sim_time=false` 时回放 bag 会发生什么？为什么？
- 你是怎么确认投影**方向**没搞反的？（怎么区分"左右反了"和"上下反了"）
- 如果相机有**畸变**（真实相机都有），你的投影还准吗？要怎么改？

---

## 提示（不是答案）

- `ros2 bag play sample_bag --clock` 才会发布 `/clock`；节点必须设 `use_sim_time:=true`
- 静态 TF 用 `StaticTransformBroadcaster` 发布一次即可（但要注意用 `/tf_static`）
- 查变换用 `tf_buffer.lookup_transform(target, source, stamp)`，
  **注意参数顺序是 (target, source)**，写反了会得到逆变换
- 投影公式（光学坐标系下）：

  $$u = f_x \frac{X_{opt}}{Z_{opt}} + c_x, \qquad v = f_y \frac{Y_{opt}}{Z_{opt}} + c_y$$

- 验收时如果发现**投影点上下颠倒或左右镜像**，回去检查
  `camera_link`（机体轴）→ 光学坐标系那一步的符号
