# M5-1 ｜ 任务状态机：把比赛任务串起来、跑通、可调试

> **难度**：★
> **综合考察**：状态机建模、节点封装、上下文流转、契约测试、YAML 编排
> **本题分值权重**：10
> **题目来源**：`创意组一轮考核.md` §M5-1
> **形式**：纯软件。现场带代码与单测，**考官会发一份未见过的任务 YAML** 让你跑

---

## 0. 这道题在考什么

比赛任务是**一串有依赖关系的步骤**，每步都可能失败、超时、需要重试。
把它们串起来的方式，决定了系统"出问题时能不能降级、能不能查"。

本题明确**不用** `BehaviorTree.CPP` / `Groot2`——要你**自己写调度内核**。考四件事：

1. **框架设计**：状态与转移是否清晰、是否支持并发与降级
2. **节点契约**：5 个标准节点的接口是否统一、Mock 是否可替换
3. **编排能力**：一份 YAML 描述任务，**改 YAML 不改代码**
4. **可验证性**：单测是否真能跑（不是摆设）

> 现场考点：给你一份**你没见过的 YAML**（含并发分支、重试、降级），
> 你要用**现有代码**直接跑通——如果你的框架把任务顺序写死在代码里，这题就崩了。

---

## 1. 硬性要求

| # | 要求 | 说明 |
| :-- | :-- | :-- |
| 1 | **纯 Python 实现** | **不得依赖** `BehaviorTree.CPP` / `Groot2` / `py_trees` 等现成 BTree 库 |
| 2 | **核心 < 200 行** | 调度内核（状态机 + 转移逻辑）控制在 200 行内（不含节点实现） |
| 3 | **六种状态** | `IDLE` `RUNNING` `SUCCESS` `FAILED` `SKIPPED` `RETRYING` |
| 4 | **支持重试与降级** | 失败 → 按配置重试（次数/间隔）→ 仍失败 → 走 `fallback` 或标 `SKIPPED` |
| 5 | **支持超时** | 每步可配 `timeout`，超时按失败处理（可走降级） |
| 6 | **支持并发分支** | `Parallel`：所有子节点成功才算成功；任一失败按策略处理 |
| 7 | **上下文对象** | `TaskContext`：任务 ID、截止时间、共享数据字典、重试预算、降级标记、元数据 |
| 8 | **YAML 编排** | 任务由 YAML 定义，**代码不含具体任务顺序** |
| 9 | **5 个标准节点** | 接口固定、Mock 实现（见 §2.2） |
| 10 | **单测覆盖** | 每个节点 ≥3 用例（正常/超时/失败→重试或降级），**Mock 掉 ROS2** |

> **第 2 条怎么算**：调度内核指"读 YAML → 建节点 → 按状态转移执行"这部分。
> 数一下你自己的文件行数，答辩时会看。

---

## 2. 任务分解

### 2.1 状态机框架

**状态定义**：

| 状态 | 含义 |
| :-- | :-- |
| `IDLE` | 未开始 |
| `RUNNING` | 正在执行 |
| `SUCCESS` | 成功完成 |
| `FAILED` | 失败且未降级 |
| `SKIPPED` | 跳过了（降级后的结果） |
| `RETRYING` | 失败后正在重试 |

**转移规则**（必须实现）：

```
IDLE  ──start──>  RUNNING
RUNNING ──ok───> SUCCESS ──> 下一步
RUNNING ──fail─> RETRYING ──(预算未用完)──> RUNNING
                     └──(预算用完)──> fallback / SKIPPED / FAILED
RUNNING ──timeout──> 同 fail 分支
```

**必须回答**：

- **重试预算**是全局的还是每步的？（两种都行，但要说清）
- `fallback` 指向的节点如果**也失败**了，会怎样？（要有终止条件，别无限跳）
- 状态转移**是否允许回跳**（如 `navigate_to_grasp` 失败后回 `navigate_to_scan`）？
  回跳要不要计数？（不计数会**死循环**）

### 2.2 五个标准节点（接口固定）

**基类契约**（必须保持一致，M5-2/3/4 会复用）：

```python
class TaskNode:
    def __init__(self, name, params, ctx): ...
    def setup(self): ...          # 可选：资源准备
    def execute(self) -> str: ...  # 返回 'SUCCESS' | 'FAILED' | 'SKIPPED'
    def cancel(self): ...         # 被超时/急停打断时调用
    def teardown(self): ...       # 可选：释放资源
```

| 节点 | 行为 | 输出到上下文 |
| :-- | :-- | :-- |
| `WaitForTrigger` | 等 `/referee/start_cmd` **或**键盘空格；超时 30s | — |
| `NavigateTo` | 调 `/navigate_to_pose` Action；支持静态位姿或从上下文取 | `last_nav_result` |
| `DetectTarget` | 订阅 `/perception/targets`，等类别/置信度达标 | `target_pose` `target_id` |
| `ExecuteGrasp` | 调 `/manipulation/grasp` Action；输入 `grasp_pose` `grasp_type` | `grasp_result` `object_pose` |
| `SpeakTTS` | 调 `/tts/speak` Service | — |

**要求**：

- 每个节点**必须能 Mock**（不启 ROS2 也能单测）
- **取消语义完整**：`cancel()` 被调用后，`execute()` 要能尽快退出（不是只能等超时）
- 节点**不许自己读 YAML**（参数由调度器传入，保持可测）

**必须回答**：

- 节点如何**报告中间进度**？（长任务如导航需要，否则界面只能显示"运行中"）
- `cancel()` 是**协作式**还是强杀？（Python 里强杀不现实，说清你的做法）

### 2.3 YAML 编排 DSL

**必须支持**的字段（考官现场 YAML 会用）：

| 字段 | 说明 |
| :-- | :-- |
| `name` | 节点名（唯一） |
| `type` | 对应哪个 `TaskNode` 子类 |
| `timeout` | 秒；超时按失败处理 |
| `retry` | 重试次数 |
| `retry_interval` | 重试间隔（秒） |
| `fallback` | 失败后跳转到哪个节点名 |
| `on_fail` | `skip` / `abort`（决定标记 SKIPPED 还是 FAILED） |
| `parallel` | 并发分支（子任务列表 + 失败策略） |
| `pose` / `pose_from_context` | 导航目标来源 |
| `target_class` / `min_confidence` | 检测条件 |
| `text` | TTS 文本 |

**示例结构**（供参考，**你的字段名可以不同，但要写进文档**）：

```yaml
tasks:
  - name: wait_start
    type: WaitForTrigger
    timeout: 30

  - name: navigate_to_scan
    type: NavigateTo
    pose: {x: 2.0, y: 0.5, yaw: 0.0}
    retry: 2
    retry_interval: 1.0
    fallback: wait_start

  - name: detect_qr
    type: DetectTarget
    target_class: "qrcode"
    min_confidence: 0.7
    timeout: 15
    fallback: navigate_to_scan

  - name: grasp
    type: ExecuteGrasp
    grasp_type: "top_down"
    retry: 2
    on_fail: skip

  # 并发分支示例（考官会用到）
  - name: parallel_checks
    parallel:
      fail_policy: any_fail      # any_fail | all_must_succeed
      branches:
        - name: check_battery
          type: SpeakTTS
          text: "检查电量"
        - name: check_lidar
          type: SpeakTTS
          text: "检查雷达"
```

**要求**：

- **不支持 `!include` 也没关系**（YAML 标准标签需要自定义构造器），
  但要说清你怎么组织多个位姿文件（合并？还是写在同一文件？）
- YAML **解析失败要给人话**（指出哪一行、缺什么字段），不是抛 Python traceback
- 未知 `type` 要报错并指出可用类型列表

### 2.4 运行时表现

| 项 | 要求 |
| :-- | :-- |
| **彩色日志** | 状态转移 / 上下文变更 / 重试 / 降级 / 超时 各用不同颜色（终端看得清） |
| **`task_report.json`** | 每个状态：耗时、结果、重试次数、是否降级；以及**最终上下文** |
| **退出码** | 全部成功 → 0；有失败 → 非 0（便于 CI/脚本判断） |

**`task_report.json` 字段示例**：

```json
{
  "task_id": "run_20260922_153000",
  "result": "SUCCESS",
  "total_elapsed_s": 42.7,
  "steps": [
    {"name": "wait_start", "status": "SUCCESS", "elapsed_s": 3.2,
     "retries": 0, "degraded": false},
    {"name": "navigate_to_scan", "status": "SUCCESS", "elapsed_s": 18.4,
     "retries": 1, "degraded": false}
  ],
  "final_context": {"target_id": "qr_01", "target_pose": [2.1, 0.4]}
}
```

**`result` 的取值必须明确定义**（下游的 M5-4 要读它做复盘）：

| 值 | 含义 |
| :-- | :-- |
| `SUCCESS` | 全部步骤成功 |
| `FAILED` | 有步骤失败且未能降级 |
| `TIMEOUT` | **任务级截止时间**（`TaskContext` 里的 deadline）到了，被强制结束 |
| `ABORTED` | 被外部中断（如急停、裁判 `STOP`） |

> ⚠️ **注意区分两种超时**：
> - **步骤级** `timeout`：某个节点超时 → 按失败处理（可重试/降级）
> - **任务级 deadline**：整体超过截止时间 → 整个任务结束，`result = TIMEOUT`
>
> 两者都要实现。只做步骤级超时的话，一个"无限重试"的任务会永远跑不完。

### 2.5 单测（必须真能跑）

**要求**：

- 进程内跑（`pytest tests/`），**不依赖 ROS2 运行时**（Mock 掉 Action/Service/订阅）
- 每个节点 ≥3 用例：

| 节点 | 用例示例 |
| :-- | :-- |
| `WaitForTrigger` | 收到触发 / 超时 / 取消 |
| `NavigateTo` | 成功 / 失败 / 超时 / 取消 |
| `DetectTarget` | 达到阈值 / 未达阈值超时 / 置信度不足 |
| `ExecuteGrasp` | 成功 / 失败→重试成功 / 重试耗尽 |
| `SpeakTTS` | 服务可用 / 服务不存在 / 调用超时 |

- **框架级用例**（至少 3 个）：重试耗尽后走 fallback、超时触发降级、并发分支任一失败

**要求给出** `pytest -q` 的输出（覆盖率可选但要贴数字）。

---

## 3. 现场流程（约 12 分钟）

| 环节 | 内容 | 时间 |
| :-- | :-- | :--: |
| 看框架 | 数核心行数、看状态转移实现 | 3 min |
| 跑单测 | `pytest tests/` 是否全绿 | 2 min |
| **跑未见过的 YAML** | **考官发一份含并发/重试/降级的 YAML**，一键跑通 | 5 min |
| 追问 | 设计取舍、死循环防护、取消语义 | 2 min |

### 现场 YAML 会考到

考官的 YAML 会包含：

- 至少一条 `fallback` 链（且**故意让 fallback 也失败**，看你会不会无限跳）
- 一个 `parallel` 分支，其中**一个子任务失败**
- 一个 `timeout` 会触发的节点
- 一个 `retry` 会耗尽的节点

**评测点**：能否跑完、报告是否合理、有没有卡死。

---

## 4. 交付物与格式

```
M5-1/
├── task_fsm/                  # 框架包
│   ├── core.py                # ★ 调度内核（< 200 行）
│   ├── context.py             # TaskContext
│   ├── nodes.py               # 5 个标准节点
│   ├── registry.py            # type -> 节点类 的注册表
│   └── logger.py              # 彩色日志
├── run_task.py                # 入口：python run_task.py xxx.yaml
├── tasks/
│   ├── task_demo.yaml         # 自带示例（含并发）
│   └── poses/                 # 位姿片段（若你支持外部文件）
├── tests/
│   ├── test_nodes.py
│   └── test_fsm.py
├── docs/
│   ├── design.md              # 设计说明（状态图 + 取舍）
│   └── dsl.md                 # ★ YAML 字段说明（考官按此写测试 YAML）
└── README.md
```

### 运行约定

```bash
# 一键运行
python run_task.py tasks/task_demo.yaml

# 输出
#   - 终端彩色日志
#   - task_report.json
# 退出码: 0=全成功, 非0=有失败

# 单测
pytest tests/ -q
```

### `docs/dsl.md` 必须写清

考官要**只看这份文档**就能写出测试 YAML。必须包含：

- [ ] 所有支持的字段名与含义
- [ ] `fallback` / `on_fail` 的语义（什么时候 SKIPPED、什么时候 FAILED）
- [ ] `parallel` 的写法与 `fail_policy` 取值
- [ ] 必填字段缺了会怎样
- [ ] 一个**完整的示例**（可直接跑）

---

## 5. 明确禁止

- 禁止依赖 `BehaviorTree.CPP` / `Groot2` / `py_trees`（题面明确要求自己写）
- 禁止把任务顺序写死在代码里（现场 YAML 会变）
- 禁止无终止条件的 fallback（会死循环；必须能检测并退出）
- 禁止节点直接读 YAML / 直接依赖 ROS2 全局状态（否则无法单测）
- 禁止单测是摆设（`pytest` 必须真跑，且不要求 ROS2 环境）
- 禁止超时用"轮询到天荒地老"实现（要有明确的超时判定）
- 禁止 `cancel()` 形同虚设（被取消后要能及时退出）
