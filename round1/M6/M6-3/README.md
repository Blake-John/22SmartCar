# M6-3 ｜ ORT 会话调优与 CUDA Graph：把延迟压稳

> **难度**：★★★
> **综合考察**：推理引擎配置、执行器选择、CUDA Graph 捕获、延迟确定性
> **本题分值权重**：30
> **题目来源**：`创意组一轮考核.md` §M6-3
> **形式**：自备开发板；现场带配置与数据实测

---

## 0. 这道题在考什么

M6-2 的 INT8 模型跑 **22 FPS**，但比赛要求 **≥30 FPS**，
而且——**每帧延迟必须稳定在 35ms 以内**。

> 为什么强调"稳"：感知延迟忽大忽小，**导航会跟丢**。
> 平均 30 FPS 但偶尔飙到 80ms，比稳定 25 FPS 更糟。

考四件事：

1. **执行器（EP）选择**：CPU / CUDA / TensorRT 实测对比，**说清为什么选它**
2. **会话参数**：逐参数实验（一次只改一个），量化每个参数的影响
3. **CUDA Graph**：消除 kernel launch 开销，**把 P99 压下来**
4. **延迟分布**：1000 帧的直方图 + CDF，看的是**尾部**不是平均值

> **最容易翻车的地方**：只看平均延迟。
> 题面要求 **P95 < 35ms、P99 < 50ms、最大 < 80ms**——
> 这些是**尾部指标**，平均值好看不代表达标。

---

## 1. 硬性要求

| # | 要求 | 说明 |
| :-- | :-- | :-- |
| 1 | **三种 EP 对比** | CPU / CUDA / TensorRT（板子支持哪些就测哪些） |
| 2 | **六项指标** | FPS、P50、P95、P99、GPU 利用率、显存 |
| 3 | **逐参数实验** | 每次只改一个 `SessionOptions` 参数，跑 100 帧记延迟 |
| 4 | **CUDA Graph 捕获** | 捕获推理流程，对比捕获前后延迟 |
| 5 | **1000 帧稳定性测试** | 输出直方图 + CDF + 统计表 |
| 6 | **达标线** | **FPS ≥ 30**、**P95 < 35ms**、**P99 < 50ms**、**最大 < 80ms** |
| 7 | **输出三份数据** | `ep_comparison.yaml`、`session_tuning.csv`、`latency_stability.pdf` |

> **第 4 条的约束**：CUDA Graph 需要**固定输入尺寸**。
> 如果你的模型是动态 shape，要先说明怎么处理（固定分辨率？还是放弃 Graph？）。

---

## 2. 任务分解

### 2.1 执行器对比与选择

**要测的 EP**（按板子能力选）：

| EP | 说明 |
| :-- | :-- |
| `CPUExecutionProvider` | 基线 |
| `CUDAExecutionProvider` | GPU 常规路径 |
| `TensorRTExecutionProvider` | GPU 深度优化路径 |

**每个 EP 记录**：

| 指标 | 说明 |
| :-- | :-- |
| FPS | 60 秒平均（沿用 M6-1 要求） |
| P50 / P95 / P99 | 逐帧延迟分位 |
| GPU 利用率 | 平台工具 |
| 显存 | 同上 |

**输出** `ep_comparison.yaml` + **推荐配置**。

**必须回答**：

- **TensorRT EP 有时反而比 CUDA EP 慢**——用你自己的实测数据解释为什么
- 针对上面的原因，你怎么缓解？（说明每一步的依据与前后数字）
- 首次加载 TensorRT engine 很慢，**指标该怎么算才公平**？（要不要排除首次？）

### 2.2 会话配置逐参数调优

**要逐个实验的参数**：

| 参数 | 取值 | 说明 |
| :-- | :-- | :-- |
| `graph_optimization_level` | DISABLE / BASIC / EXTENDED / ALL | 图优化级别 |
| `intra_op_num_threads` | 1 / 2 / 4 / 0(自动) | 算子内并行 |
| `inter_op_num_threads` | 1 / 2 / 4 / 0 | 算子间并行 |
| `enable_mem_pattern` | True / False | 内存复用模式 |
| `enable_cpu_mem_arena` | True / False | CPU 内存池 |
| `execution_mode` | SEQUENTIAL / PARALLEL | 执行模式 |
| `cuda_graph_capture_id` | 开启 / 关闭 | CUDA Graph |

**要求**：

- **每次只改一个参数**（否则无法归因）
- 每个配置跑 **100 帧**，记 P50/P95/P99
- 输出 `session_tuning.csv`（每行一个配置组合）

**必须回答**：

- `intra_op_num_threads` 设太大反而慢，为什么？（线程切换开销 / 核数限制）
- `graph_optimization_level=EXTENDED` 相比 `BASIC` 多做了什么？
- `execution_mode=PARALLEL` 在什么场景下更快？什么场景下更慢？
- 哪个参数对你的**尾部延迟（P99）**影响最大？

### 2.3 CUDA Graph 捕获

**做法**：

1. 预热若干帧（让 kernel 完成自动调优）
2. **捕获**推理流程（预处理 → 推理 → 后处理）的 kernel 启动序列
3. 之后**直接执行 graph**，跳过逐 kernel 的 launch 开销

**要求**：

| 项 | 要求 |
| :-- | :-- |
| 输入尺寸 | **必须固定**（Graph 的前提） |
| 对比 | 捕获前 vs 捕获后的 P50/P95/P99 |
| 目标 | **P99 从 ~50ms 降到 35ms 以内**；延迟波动 < 5% |

**必须回答**：

- kernel launch 开销约 **5~10μs/次**。一次推理若有 100 个 kernel，总开销多少？
  这与你的实测提升对得上吗？
- **捕获失败**的常见原因有哪些？（内存分配、同步操作、CPU 侧分支）
- 后处理（NMS）里如果有**动态 shape**，还能捕获吗？

### 2.4 延迟稳定性测试

**1000 帧连续推理**，输出：

| 产物 | 内容 |
| :-- | :-- |
| **直方图** | 延迟分布 |
| **CDF** | 累积分布（看尾部） |
| **统计表** | min / P50 / P95 / P99 / max / std |

**达标线**：

| 指标 | 阈值 |
| :-- | :--: |
| P95 | **< 35 ms** |
| P99 | **< 50 ms** |
| 最大单帧 | **< 80 ms** |

**必须回答**：

- 为什么**最大值**也要管？（偶发的 200ms 卡顿会让车"愣一下"）
- 你的**长尾**来自哪里？（GC？内存分配？CUDA 同步？OS 调度？）
- 调优前后分布形状的变化说明了什么？

---

## 3. 现场流程（约 15 分钟）

| 环节 | 内容 | 时间 |
| :-- | :-- | :--: |
| 基线复现 | 用**默认配置**跑一遍，确认约 22 FPS / P95 ~50ms | 3 min |
| EP 对比 | 看 `ep_comparison.yaml`，现场切 EP 演示 | 3 min |
| 参数贡献 | 追问"哪个参数贡献最大"，要求看 `session_tuning.csv` | 3 min |
| **1000 帧演示** | 现场跑，看延迟是否稳定 | 4 min |
| 追问 | CUDA Graph 原理、尾部延迟来源 | 2 min |

> 现场提供：一台开发板 + 量化后的 INT8 ONNX 模型。

### 会重点核对

| 项 | 怎么验 |
| :-- | :-- |
| 逐参数实验 | 抽查一行，问"这个参数改了会怎样" |
| 尾部指标 | 现场跑 1000 帧，核对 P95/P99/最大值 |
| CUDA Graph | 问"关掉 Graph 会退多少"，看是否有对比数据 |
| 公平性 | 首次加载/预热是否被排除，说明是否清楚 |

---

## 4. 交付物与格式

```
M6-3/
├── tune/
│   ├── ep_compare.py         # 三种 EP 对比
│   ├── session_sweep.py      # ★ 逐参数实验（一次一个）
│   ├── cuda_graph.py         # CUDA Graph 捕获与执行
│   └── latency_test.py       # 1000 帧稳定性测试
├── configs/
│   ├── default.yaml          # 默认配置（基线）
│   └── tuned.yaml            # 调优后（推荐）
├── results/
│   ├── ep_comparison.yaml
│   ├── session_tuning.csv    # 每行一个配置组合
│   ├── latency_stability.pdf # 直方图 + CDF + 统计表
│   └── latency_raw.csv       # 1000 帧原始延迟（可复算）
├── docs/
│   ├── tuning_report.md      # 调优报告（哪个参数贡献最大）
│   └── cuda_graph.md         # 捕获原理 + 失败原因分析
└── README.md
```

### `session_tuning.csv` 格式

```csv
config_id,graph_opt,intra_threads,inter_threads,mem_pattern,cpu_arena,exec_mode,cuda_graph,p50_ms,p95_ms,p99_ms,fps
baseline,ALL,0,0,true,true,SEQUENTIAL,false,38.2,50.1,58.3,22.1
c1,DISABLE,0,0,true,true,SEQUENTIAL,false,41.0,54.2,61.0,20.4
c2,ALL,1,1,true,true,SEQUENTIAL,false,36.9,48.7,55.1,23.0
...
```

> 每行**只与上一行差一个参数**（便于归因）。

### 运行约定

```bash
# EP 对比
python tune/ep_compare.py --model models/best_int8_static.onnx --seconds 60 \
    --out results/ep_comparison.yaml

# 逐参数扫描
python tune/session_sweep.py --model models/best_int8_static.onnx \
    --frames 100 --out results/session_tuning.csv

# CUDA Graph 对比
python tune/cuda_graph.py --model models/best_int8_static.onnx \
    --compare-on-off --out results/graph_compare.yaml

# 1000 帧稳定性
python tune/latency_test.py --model models/best_int8_static.onnx --config configs/tuned.yaml \
    --frames 1000 --out results/latency_stability.pdf --raw results/latency_raw.csv
```

---

## 5. 明确禁止

- 禁止只看平均延迟（必须报 P95/P99/**最大值**）
- 禁止一次改多个参数（无法归因，现场会问）
- 禁止只测几十帧就说"稳定"（要求 1000 帧）
- 禁止把首次加载/TensorRT 引擎编译时间混进延迟统计（要说明是否排除）
- 禁止 CUDA Graph 不说明输入尺寸限制（动态 shape 不能捕获）
- 禁止只给结论不给原始数据（`latency_raw.csv` 要能复算分位数）
- 禁止拿"随机波动"解释尾部延迟（要定位到具体原因）
