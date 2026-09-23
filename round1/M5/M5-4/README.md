# M5-4 ｜ 复盘与实验管理工具箱：场场跑、场场看、场场改

> **难度**：★★★★
> **综合考察**：数据分析、实验管理、配置版本控制、工程效率
> **本题分值权重**：40
> **题目来源**：`创意组一轮考核.md` §M5-4
> **形式**：纯软件（主机侧）。现场带工具，**考官会发一套你没见过的练习日数据**

---

## 0. 这道题在考什么

练习周每天 10+ 把，比赛当天 3~5 把。每把跑完要**30 秒看懂**：

> 成败？关键指标多少？**故障根因是什么**？与上一把差在哪？

想试新参数，要能**一条命令切换、自动记录、自动对比**，
赛后半小时内产出复盘报告与**可交付的基线包**。

考四件事：

1. **快速复盘**：30 秒内出结论，且**故障根因要能一句话说清**
2. **实验管理**：新增/运行/对比/晋升，全流程自动化且**可追溯**
3. **对比可视化**：输出的表格与图**直接可用**（能发群、能写报告）
4. **工程交付**：生成基线包，**在另一台机器上能自验通过**

> **最容易翻车的地方**：把"复盘"做成"把 log 全打印一遍"。
> 题目要的是 **30 秒出结论**——所以必须**只解析关键话题**、
> 并且能**自动归因**（不是把所有数据丢给人类看）。

---

## 1. 硬性要求

| # | 要求 | 说明 |
| :-- | :-- | :-- |
| 1 | **单次复盘脚本** | 输入 mcap + logs + `switch_log.csv`，输出**终端摘要 + Markdown 报告** |
| 2 | **30 秒出结果** | 从启动到输出摘要 **< 30s**（现场掐表）；只解析关键话题 |
| 3 | **故障根因一句话** | 格式见 §2.1；**要有因果链**（现象 → 处理 → 代价） |
| 4 | **与上一把对比** | 指标增减、新增/消失的故障、参数/模型变更 |
| 5 | **实验管理器** | `new` / `run` / `compare` / `promote` 四个子命令 |
| 6 | **对比输出可用** | Markdown 表格 + 交互图（Plotly 或等价物） |
| 7 | **基线包生成** | 产出 `.tar.gz`，含锁定的参数、模型、`verify_baseline.sh` |
| 8 | **异机可验** | 解压 → 跑 `verify_baseline.sh` → PASS |

> **第 2 条的现实约束**：一个 180s 的比赛 mcap 可能几百 MB。
> 如果你的脚本**全量解析**，30 秒绝对出不来——必须先**挑话题**再解析。

---

## 2. 任务分解

### 2.1 单次运行复盘

**输入**：

| 输入 | 说明 |
| :-- | :-- |
| `blackbox.mcap` | 黑匣子（含关键话题） |
| `logs/` | 节点日志 |
| `task_report.json` | **M5-1 状态机产出的执行报告**（每个状态的耗时/重试/降级） |
| `switch_log.csv` | **M5-3 记录的参数/模型切换** |

> 后两份是**上游模块的产物**——这正是 M5 的链路含义：
> 状态机（M5-1）负责"记下每步发生了什么"，
> 终端（M5-3）负责"记下谁改了什么"，
> 而本题负责"把它们与黑匣子对齐，30 秒读出结论"。
> **你要说清怎么把三者按时间对齐**（mcap 是仿真/系统时钟，JSON 是墙钟）。

**输出**：终端彩色摘要 + `review_<timestamp>.md`

**必须包含**：

| 内容 | 要求 |
| :-- | :-- |
| 任务结果 | SUCCESS / FAILED / Timeout + **总耗时** |
| 各子任务 | 每步耗时、重试次数、是否降级 |
| 关键指标表 | 导航成功率、路径最优性、感知频率、置信度均值、系统资源峰值 |
| **故障根因一句话** | 见下方格式 |
| 与上一把对比 | 指标增减、新增/消失故障、参数变更 |

**故障根因的格式**（题面给的例子，要模仿这种"因果链"）：

```
camera_degraded@12:34:56 (freq<10Hz) → nav fallback to lidar_only (+12s)
thermal_throttle@12:35:10 (92°C)    → model swap to yolov8n_int8 (-8fps)
```

即：**现象(证据) → 采取的动作 → 代价**。

**必须回答**：

- 你怎么**只解析关键话题**？（列白名单？按频率过滤？按 topic 类型？）
- 时间戳怎么对齐？（mcap 里的时间 vs 日志里的墙钟时间——**两者不同源**）
- "与上一把对比"里，**参数变更**从哪读？（`switch_log.csv`）如果这次没切过呢？
- 如果 mcap **损坏/缺话题**，你的脚本会怎样？（要给人话，不是 traceback）

### 2.2 实验管理器 `exp.py`

**四个子命令**（行为要忠实于题面）：

| 命令 | 行为 |
| :-- | :-- |
| `new` | 从基线**只记差异**生成新配置；记录元数据（基线/修改项/目的/预期指标） |
| `run` | 热加载参数 → 跑 N 把 → 每把跑复盘 → 汇总统计（均值/方差/成功率） |
| `compare` | 多个实验对比指定指标 → Markdown 表 + 交互图 |
| `promote` | 把最优实验推为新基线（覆盖场景文件、更新模型哈希、git commit 带摘要） |

**示例用法**：

```bash
python exp.py new --name "nav_speed_0.9" --base scene_race.yaml \
    --set nav_speed=0.9 --desc "提高直线速度测试"

python exp.py run --name "nav_speed_0.9" --scene nav_speed_0.9 --runs 3

python exp.py compare --names "nav_speed_0.8,nav_speed_0.9,nav_speed_1.0" \
    --metric nav_time,success_rate,cpu_peak

python exp.py promote --name "nav_speed_0.9" --to scene_race.yaml
```

**必须回答**：

- `new` 生成的配置**只记差异**——那运行时怎么合并回完整配置？（深合并？覆盖？）
- `run` 跑 3 把时，**怎么保证环境一致**？（要不要记录当时的 git commit / 模型哈希）
- `compare` 的"成功率"**分母是什么**？（3 把里成功几把？还是别的定义）
- `promote` 会 **git commit**——如果工作区有未提交改动怎么办？（直接 commit 会混入无关改动）

### 2.3 基线包生成器

**输入**：最优实验名 或 `scene_*.yaml`
**输出**：`baseline_package_<date>.tar.gz`，内容：

| 文件 | 说明 |
| :-- | :-- |
| `baseline.yaml` | **锁定所有关键参数**（不是"只记差异"） |
| `models/` | 最优模型文件 |
| `verify_baseline.sh` | 带**阈值**的自验脚本 |
| `README.md` | 怎么用、验证什么 |

**异机验证**：解压 → `./verify_baseline.sh` → **PASS**

**必须回答**：

- `verify_baseline.sh` 具体验什么？（模型哈希？参数一致性？还是跑一遍冒烟测试）
- 阈值怎么定？（**必须可判定**，不能是"看起来还行"）
- 如果目标机器**缺依赖**，脚本给什么提示？
- 基线包多大？（含模型文件，要说明大小是否可接受）

---

## 3. 现场流程（约 20 分钟）

| 环节 | 内容 | 时间 |
| :-- | :-- | :--: |
| **发数据跑复盘** | **考官给一套未见的练习日数据**（5 个 mcap + 3 套参数 + 2 个模型），掐表跑 `quick_review.py` | 6 min |
| 看报告 | 根因是否准确、与上一把对比是否正确、Markdown 是否可读 | 4 min |
| **实验全流程** | `new → run → compare → promote` 现场跑一遍 | 6 min |
| **异机验证** | 生成基线包，**在考官机器上**解压跑 `verify_baseline.sh` | 3 min |
| 追问 | 关键话题筛选、时间对齐、promote 的安全性 | 1 min |

### 考官会重点看

| 项 | 怎么验 |
| :-- | :-- |
| **30 秒** | 掐表（含数据加载时间，不许预先缓存） |
| **根因准确** | 考官知道数据里的真实故障，对比你的结论 |
| **对比正确** | 抽查一个指标，手工算一遍核对 |
| **异机 PASS** | 在**干净环境**（只装必要依赖）跑验证脚本 |
| **promote 安全** | 检查它是否把无关改动一起提交了 |

---

## 4. 交付物与格式

```
M5-4/
├── scripts/
│   ├── quick_review.py        # ★ 单次复盘（< 30s）
│   ├── exp.py                 # ★ 实验管理（new/run/compare/promote）
│   ├── gen_baseline.py        # ★ 基线包生成
│   └── parse_mcap.py          # 关键话题提取（被上面复用）
├── config/
│   ├── scene_race.yaml        # 当前基线
│   └── experiments/           # exp.py new 生成的差异配置 + 元数据
├── data/                      # 示例数据（小样本，可复现）
├── outputs/
│   ├── review_*.md            # 复盘报告
│   ├── compare_*.md           # 对比表
│   └── *.png                  # 交互图导出（或 HTML）
├── docs/
│   ├── review_fields.md       # 摘要各字段定义
│   └── workflow.md            # 从跑完到 promote 的完整工作流
└── README.md
```

### 运行约定

```bash
# 单次复盘（现场掐表这条）
time python scripts/quick_review.py --mcap data/run_01.mcap \
    --logs data/logs/ --switch-log data/switch_log.csv

# 实验流程
python scripts/exp.py new --name "..." --base scene_race.yaml --set k=v
python scripts/exp.py run --name "..." --scene ... --runs 3
python scripts/exp.py compare --names "a,b,c" --metric nav_time,success_rate
python scripts/exp.py promote --name "..." --to scene_race.yaml

# 基线包
python scripts/gen_baseline.py --exp "nav_speed_0.9" --out baseline_package_20260922.tar.gz
```

### 依赖说明

题面提到 `pandas` / `plotly` / `ruamel.yaml` / `gitpython`，但**不强制**：

- 用标准库 + `numpy` 也能做（表格用 markdown 手拼、图用 matplotlib 或直接输出 HTML）
- **若用第三方库，必须写进 `requirements.txt`，且能在干净环境装上**
- 异机验证时会**只按你的 requirements 安装**——漏了依赖就 PASS 不了

---

## 5. 明确禁止

- 禁止全量解析 mcap（超 30 秒必挂；要**挑关键话题**）
- 禁止根因只有现象没有因果链（要写"现象 → 动作 → 代价"）
- 禁止 `compare` 输出只有数字没有图（题面要求"直接可用"）
- 禁止 `promote` 把**无关改动**一起 commit（现场会检查）
- 禁止 `verify_baseline.sh` 没有明确阈值（"看起来正常"不算通过）
- 禁止依赖写死在代码里（异机验证会挂）
- 禁止把"与上一把对比"做成"手动指定上一把文件"（要能自动找最近一次）
