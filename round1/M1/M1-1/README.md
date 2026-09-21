# M1-1 ｜ 三节点链路 + 动态配参

> **难度**：★
> **综合考察**：ROS 基础，各大通信方式（话题 / 服务 / 参数 / 自定义接口）
> **本题分值权重**：10
> **现场判分接口**：见文末「接口契约」，**必须严格遵守**，否则自动比对无法进行

---

## 场景

你要做一个"虚拟超声波测距"链路：**传感器 → 滤波 → 报警**。

三个节点各自独立，通过话题和服务连起来。这是 ROS2 里最常见、也最基本的一段工程链路。

---

## 任务

### 节点A（发布者 —— 模拟传感器）

以 **10 Hz** 发布自定义消息 `SensorData.msg`，包含：

| 字段 | 类型 | 说明 |
| :-- | :-- | :-- |
| `distance` | `float32` | 模拟超声波的距离（米） |
| `unit` | `string` | 距离单位，固定 `"m"` |
| `stamp` | `builtin_interfaces/Time` | 消息生成时间 |
| `status` | `uint8` | 状态：`0`=正常，`1`=超出量程，`2`=传感器错误 |

> **接口包要自己创建**：本目录**不提供** `sensor_interfaces/`。
> 下面的字段名 / 类型 / 顺序是**契约**，你必须原样实现（字段名、类型、顺序都算分）。
> 包名必须叫 `sensor_interfaces`，否则节点 import 会失败。

### 节点B（处理者 —— 数据滤波与转换）

1. 订阅节点A的话题，用**一阶低通滤波**平滑数据：

   $$y_k = \alpha \cdot x_k + (1-\alpha) \cdot y_{k-1}$$

2. **滤波系数 $\alpha$ 必须是 ROS 参数**，要能用 `ros2 param set` **在运行时动态修改**，并且在终端**看得到效果**
3. 滤除 `status != 0` 的无效数据：**不参与滤波**，但要**打印警告日志**
4. 把滤波结果发布到另一个话题，消息类型用 **ROS2 标准消息** `std_msgs/Float32`

### 节点C（执行者 —— 结果响应）

1. 订阅处理后的结果
2. 当距离 **< 0.3 m** 时，调用自定义服务 `TriggerAlarm.srv` 触发"报警"，并打印日志
3. 服务端可以简单地打印 `[ALARM] 距离过近！` 并返回成功
4. **正确处理服务超时**：若服务端 **1 秒无响应**，打印 `[WARN] 报警服务超时`

> 服务接口同样按上面的契约自己创建：`sensor_interfaces/srv/TriggerAlarm.srv`

---

## 交付物

| 路径 | 内容 |
| :-- | :-- |
| `M1/M1-1/src/sensor_interfaces/` | **自己创建**的接口包（msg + srv + CMakeLists + package.xml） |
| `M1/M1-1/src/<你的包>/` | 你的三个节点 |
| `M1/M1-1/README.md` | 如何编译、如何运行三个节点、如何验证 |
| `M1/M1-1/` | Git 历史 |

---

## 接口契约（现场按此验收）

**话题 / 服务名**（**必须一致**，否则考官无从比对）：

| 名称 | 类型 | 方向 |
| :-- | :-- | :-- |
| `/sensor_data` | `sensor_interfaces/msg/SensorData` | 节点A → 节点B |
| `/processed_distance` | `std_msgs/msg/Float32` | 节点B → 节点C |
| `/trigger_alarm` | `sensor_interfaces/srv/TriggerAlarm` | 节点C 调用 |

**参数**：

| 节点 | 参数名 | 类型 | 默认值 | 说明 |
| :-- | :-- | :-- | :--: | :-- |
| 节点B | `alpha` | double | 0.3 | 低通滤波系数 |
| 节点C | `alarm_threshold` | double | 0.3 | 报警阈值（米） |
| 节点C | `service_timeout` | double | 1.0 | 服务超时（秒） |

**验收时考官会做**：

1. `ros2 node list` / `ros2 topic list` / `ros2 topic hz /processed_distance`
   确认三节点在跑、频率约 10 Hz
2. `ros2 param set /node_b_filter alpha 0.9`，然后 `ros2 param get` 确认已生效，
   并观察输出数据的平滑程度是否变化
3. `ros2 service call /trigger_alarm ...` 手动调一次服务，确认服务端有响应
4. **杀掉服务端**，再看节点C是否打印 `[WARN] 报警服务超时`（而不是死等或崩溃）

> **允许** Py 或 C++ 任选。

---

## 完成判断（现场）

跑通代码，能够看到发布的话题、处理的结果与实时日志。

---

## 评分要点

| 维度 | 分值 | 看什么 |
| :-- | :--: | :-- |
| 任务完成 | 40 | 三节点跑通；$\alpha$ 运行时可改；无效数据被过滤；服务超时被处理 |
| 过程证据 | 20 | 提交是否分步（先A→再B→再C→再补服务超时） |
| 工程规范 | 10 | 包结构、`package.xml`、依赖声明、无硬编码话题名 |
| 权衡与判断 | 10 | 为什么用话题而不是服务？为什么服务要用异步调用？ |
| 答辩 | 20 | 见下 |

---

## 常见追问（提前想清楚）

- **为什么服务客户端不能在回调里 `while + spin_once` 等结果？** 会发生什么？
- 一阶低通滤波的 $\alpha$ 越大，输出越平滑还是越灵敏？为什么？
- 你的超时是怎么实现的？如果服务端"假装在跑但永不返回"，你能检测到吗？
- `status != 0` 时你**不更新滤波状态**——如果传感器连续 10 帧都是错误，恢复后第一帧会怎样？
- 如果节点B挂了，节点C会有什么表现？你会怎么加"看门狗"？

---

## 提示（不是答案）

- 自己建 `sensor_interfaces` 包（`--build-type ament_cmake` + `rosidl_generate_interfaces`），`colcon build` 后用 `ros2 interface show` 确认字段
- 参数必须 **`declare_parameter`** 才能被 `ros2 param set` 改
- 服务超时的正统做法是 **`call_async` + 定时器轮询 `future.done()`**，
  而不是在回调里阻塞等待（那会和 executor 重入打架）
