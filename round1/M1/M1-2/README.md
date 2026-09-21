# M1-2 ｜ Launch 编排：从"一个个敲命令"到"一键启动"

> **难度**：★★
> **综合考察**：Launch 管理节点、参数文件、命名空间、事件与依赖
> **本题分值权重**：20
> **现场判分接口**：见「接口契约」

---

## 场景

M1-1 里你开了三个终端，敲了三条 `ros2 run`。现在要比赛了——**没人有时间敲命令**。

这一题教你把"一堆命令"变成"一条命令"，并且让**两组机器人同时跑、互不干扰**。

---

## 任务

基于 M1-1 的三个节点（或重新写一套新的三个节点），完成以下 Launch 工程化改造。

### 1. Python Launch 文件

写一个 `bringup.launch.py`，一键启动全部 **3 个节点**。

- 必须用 **Python 格式**编写（**不允许 XML / YAML** launch）
- 必须支持命令行传参：

  ```bash
  ros2 launch my_pkg bringup.launch.py namespace:=my_robot
  ```

- 所有节点必须运行在**同一个命名空间**下（由 `namespace` 参数控制）
- 每个节点的**名称必须显式指定**（不依赖默认名）

### 2. 参数管理

- 节点B 的滤波系数、节点C 的报警阈值，**必须从 YAML 参数文件加载**
- 参数文件路径本身也必须是 Launch 的**可配置参数**：

  ```bash
  ros2 launch my_pkg bringup.launch.py params_file:=/path/to/params.yaml
  ```

- 在 Launch 中演示**参数覆盖**：同一个参数在**不同命名空间下取不同值**
  （例如 `robot1` 阈值 0.3，`robot2` 阈值 0.5）

### 3. 多组实例

用**同一个** Launch 文件，启动**两组完全独立**的节点实例（不同命名空间）：

| 组 | 命名空间 | 报警阈值 |
| :-- | :-- | :--: |
| 第一组 | `robot1` | 0.3 m |
| 第二组 | `robot2` | 0.5 m |

两组必须**同时运行、互不干扰**（话题名自动隔离）。

### 4. 事件与依赖

在 Launch 中实现**节点启动顺序控制**：**节点C 必须在节点B 完全启动之后才启动**，
避免服务调用失败。

### 5. 错误处理

如果 YAML 参数文件**不存在**，Launch 要给出**清晰的错误提示**，
**而不是 Python 栈回溯**。

---

## 交付物

| 路径 | 内容 |
| :-- | :-- |
| `M1/M1-2/` | 你的包 + `bringup.launch.py` |
| `M1/M1-2/params_robot1.yaml` | robot1 参数（阈值 0.3） |
| `M1/M1-2/params_robot2.yaml` | robot2 参数（阈值 0.5） |
| `M1/M1-2/README.md` | 一键启动命令 + 如何验证两组隔离 |
| `M1/M1-2/` | Git 历史 |

---

## 接口契约（现场按此验收）

**参数名**（Launch 参数）：

| 参数 | 默认值 | 说明 |
| :-- | :-- | :-- |
| `namespace` | `robot1` | 所有节点的命名空间 |
| `params_file` | （空） | YAML 参数文件路径 |
| `use_sim_time` | `false` | 是否使用仿真时间 |

**节点名**（必须显式指定，便于按名查参数）：

`node_a_sensor` / `node_b_filter` / `node_c_alarm`

**YAML 参数文件字段**：

```yaml
/**/node_b_filter:
  ros__parameters:
    alpha: 0.3
/**/node_c_alarm:
  ros__parameters:
    alarm_threshold: 0.3
    service_timeout: 1.0
```

> ⚠️ **注意 key 的写法**：节点带命名空间后，节点全名是 `/robot1/node_b_filter`。
> 用 `node_b_filter` 这样的**相对 key 在命名空间下匹配不到**。
> 本目录已给出可用的 `params_robot1.yaml` / `params_robot2.yaml` 作为参考。

**验收时考官会做**：

1. 同时启动两组，`ros2 node list` 应能看到 `/robot1/...` 与 `/robot2/...` 共 6 个节点
2. `ros2 param get /robot1/node_c_alarm alarm_threshold` → `0.3`
   `ros2 param get /robot2/node_c_alarm alarm_threshold` → `0.5`
   （**同一份 Launch、同一套代码，不同命名空间取到不同值**）
3. `ros2 topic list` 应能看到 `/robot1/sensor_data` 与 `/robot2/sensor_data` 彼此隔离
4. 故意传一个不存在的 `params_file:=/nope.yaml`，**必须看到清晰错误提示、无 Python 栈回溯**

> **命名空间生效的前提**：节点里创建话题/服务时要用**相对名**
> （如 `sensor_data`），而不是**绝对名**（如 `/sensor_data`）——
> 绝对名会绕过命名空间。这是本题最容易踩的坑之一。

---

## 完成判断（现场）

一键启动脚本，终端中正确输出相应日志，并能清楚区分两组命名空间。

---

## 评分要点

| 维度 | 分值 | 看什么 |
| :-- | :--: | :-- |
| 任务完成 | 40 | 一键启动、命名空间隔离、参数文件生效、启动顺序、错误提示 |
| 过程证据 | 20 | 提交是否分步（先能启动 → 再加参数 → 再加多实例 → 再加错误处理） |
| 工程规范 | 10 | launch 结构清晰、无硬编码路径、README 可复现 |
| 权衡与判断 | 10 | 为什么用 `OpaqueFunction`？启动顺序为什么重要？ |
| 答辩 | 20 | 见下 |

---

## 常见追问（提前想清楚）

- 你的节点为什么**没进命名空间**？（提示：检查话题名是绝对还是相对）
- 参数文件的 key 为什么要写成 `/**/node_b_filter`？写成 `node_b_filter` 会怎样？
- **启动顺序**你是怎么保证的？如果不用事件，直接同时启动会出什么问题？
- 两组实例**真的**完全隔离吗？有没有共享的东西（比如全局参数、`/rosout`）？
- 参数文件不存在时，你的错误提示是怎么做出来的？为什么不是栈回溯？
- 如果要求**运行时**给两组实例设不同的 `alpha`，你的方案要改哪里？

---

## 提示（不是答案）

- `GroupAction` + `PushRosNamespace` 可以整组加命名空间
- 想让"节点C 在 B 之后启动"，用 `RegisterEventHandler(OnProcessStart(...))`
- 校验参数文件建议用 `OpaqueFunction`：它在 launch 时执行，可以抛**可读的**异常
- 用 `ros2 param dump /robot1/node_c_alarm` 可以确认参数到底加载上没有
