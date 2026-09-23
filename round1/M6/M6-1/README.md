# M6-1 ｜ 从模型到板端：ONNX 导出 + 基础部署

> **难度**：★
> **综合考察**：模型导出、跨平台推理、性能对比、板端环境搭建
> **本题分值权重**：10
> **题目来源**：`创意组一轮考核.md` §M6-1
> **形式**：自备开发板（Jetson / RDK / RK3588 / 其他）；现场带模型与脚本实测

---

## 0. 这道题在考什么

你在电脑上训了个模型，`mAP 0.85`，跑得挺好。
现在要把它**搬到板子上**——板子算力有限、内存紧张、还跑着别的节点。

考四件事：

1. **导出的"对"**：ONNX 导出后**输出必须与 PyTorch 一致**（不是"看起来能跑"）
2. **板上的"跑"**：板端**不装训练框架**也能推理（只留推理运行时）
3. **测的"准"**：性能数据要**跑满 60 秒**才记（排除冷启动与缓存效应）
4. **选的"明"**：CPU/GPU/NPU 三种模式实测，并**说明推荐哪个、为什么**

> **最容易翻车的地方**：导出后精度掉了却不自知。
> 例如预处理不一致（归一化参数、通道顺序、resize 方式）——
> 模型"能跑"，但框全偏。所以**一致性验证是硬性要求**。

---

## 1. 硬性要求

| # | 要求 | 说明 |
| :-- | :-- | :-- |
| 1 | **导出 ONNX** | `torch.onnx.export`，`opset=17`，`dynamic_axes`（batch 或分辨率可变） |
| 2 | **一致性验证** | `onnx.checker.check_model` + `onnxruntime` 跑测试数据；与 PyTorch 比 **CosSim > 0.99** |
| 3 | **模型信息文件** | `model_info.yaml`：输入尺寸/输出格式/算子列表 |
| 4 | **统一推理脚本** | `infer.py`：加载 ONNX + 预处理 + 后处理（NMS）一体化，输出检测框 JSON |
| 5 | **零训练框架依赖** | 板端**不装 PyTorch/TensorFlow**；只用推理运行时 |
| 6 | **三模式基准** | CPU / GPU / NPU（有则测），各记录六项指标 |
| 7 | **跑满 60 秒** | 最终指标必须基于**连续 60 秒**推理 |
| 8 | **实时演示** | 摄像头 → 板端 → 画面叠显检测框/类别/置信度/FPS，**60 秒不崩** |

> **第 5 条怎么验**：现场会在**只有推理运行时**的环境里跑 `infer.py`。
> 如果你的脚本 `import torch`，直接跑不起来。

---

## 2. 任务分解

### 2.1 模型导出与验证

**导出**：

| 项 | 要求 |
| :-- | :-- |
| 命令 | 提供 `export_onnx.py`（可复现） |
| `opset` | **17**（题面指定） |
| `dynamic_axes` | 至少 batch 维可变；分辨率可变**可选**但要说明代价 |
| 输出 | `models/best_fp32.onnx` + `models/model_info.yaml` |

**一致性验证**（必须给出数字）：

| 指标 | 阈值 | 怎么算 |
| :-- | :-- | :-- |
| CosSim | **> 0.99** | 同一批输入下，ONNX 输出与 PyTorch 输出的余弦相似度 |
| 最大绝对差 | 给出数值 | `max\|onnx\_out - torch\_out\|`（绝对值） |
| 检测框一致性 | 给出数值 | 后处理后框的最大偏差（像素） |

**必须回答**：

- `opset=17` 有什么讲究？换成 11 会怎样？
- `dynamic_axes` 设为可变分辨率后，**性能**会受什么影响？（提示：某些后端会失去优化机会）
- 一致性不达标时，**最可能**是哪一步错了？（列 2~3 个排查方向）

### 2.2 板端环境与推理脚本

**环境**（按你的板子选）：

| 平台 | 推理运行时 |
| :-- | :-- |
| Jetson | ONNX Runtime（GPU EP）/ TensorRT |
| RDK X3/X5 | RKNN-Toolkit2 + `rknnrt` |
| RK3588 | RKNN / NCNN |
| 通用 | ONNX Runtime（CPU EP） |

**`infer.py` 要求**：

| 项 | 要求 |
| :-- | :-- |
| 依赖 | **不 import torch / tensorflow** |
| 输入 | 图片、图片目录、或视频/摄像头 |
| 预处理 | **与训练时严格一致**（resize 方式、归一化均值方差、通道顺序 BGR/RGB） |
| 后处理 | 解码 + NMS（阈值可配） |
| 输出 | 检测框 JSON（类别/置信度/bbox） |
| 设备选择 | `--device cpu` / `gpu` / `npu`（三选一） |

**必须回答**：

- 预处理里**最容易不一致**的是哪一步？（提示：很多坑在 `cv2.resize` 的插值与 letterbox）
- NMS 放在 CPU 还是板端加速器上？为什么？
- 如果模型输出是 `[1, 84, 8400]` 这种布局，**解码**要注意什么？

### 2.3 性能基准

**六项指标**（每种设备模式）：

| 指标 | 怎么测 |
| :-- | :-- |
| FPS | 连续 60 秒的总帧数 ÷ 60 |
| 推理延迟 P50 / P95 | 逐帧计时，取分位数 |
| 显存/内存占用 | 平台工具（`tegrastats` / `rknn_profiler` / `psutil`） |
| CPU 占用 | 同上 |
| 模型文件大小 | `ls -l` |
| 功耗（可选） | `tegrastats` 等 |

**输出** `benchmark_<board>.yaml`：

```yaml
board: "Jetson Orin Nano 8GB"
model: "best_fp32.onnx"
input_shape: [1, 3, 640, 640]
modes:
  cpu:
    fps: 0.0
    latency_p50_ms: 0.0
    latency_p95_ms: 0.0
    mem_mb: 0.0
    cpu_pct: 0.0
    model_size_mb: 0.0
  gpu: {...}
  npu: {...}
recommended: "gpu"
reason: "为什么推荐它"
```

**必须回答**：

- 为什么必须**跑满 60 秒**？（冷启动、频率爬坡、缓存命中）
- 第一次推理与后续推理的延迟差多少？（给出数字，这解释了为什么不能只跑几帧）
- 如果某个模式**跑不起来**（比如板子没 NPU），你怎么记录？

### 2.4 实时演示

| 项 | 要求 |
| :-- | :-- |
| 输入 | 摄像头（接入板端） |
| 画面 | 叠加：检测框 + 类别 + 置信度 + FPS |
| 稳定性 | **连续 60 秒**不崩溃、不掉帧（说清"不掉帧"的判定） |
| 记录 | 录屏或截图为证 |

---

## 3. 现场流程（约 12 分钟）

| 环节 | 内容 | 时间 |
| :-- | :-- | :--: |
| 环境检查 | 板子上是否**真的没有** torch/tf | 2 min |
| 一致性复核 | 现场跑一遍 ONNX vs PyTorch 对比 | 3 min |
| 三模式演示 | `--device cpu/gpu/npu` 逐个跑起来 | 3 min |
| 实时演示 | 摄像头 60 秒 | 2 min |
| 追问 | 导出细节、预处理一致性、指标含义 | 2 min |

> 现场提供：一台**同款开发板**（仅装推理运行时 + 驱动）。

---

## 4. 交付物与格式

```
M6-1/
├── export_onnx.py            # 可复现的导出脚本
├── models/
│   ├── best_fp32.onnx
│   ├── best_fp32.pt          # 原模型（对比用）
│   └── model_info.yaml       # 输入尺寸/输出格式/算子列表
├── infer.py                  # ★ 统一推理脚本（零训练框架依赖）
├── tools/
│   ├── check_consistency.py  # ONNX vs PyTorch 一致性验证
│   └── benchmark.py          # 60 秒基准测试（输出 yaml）
├── results/
│   ├── benchmark_<board>.yaml
│   ├── consistency.json      # CosSim / 最大绝对差
│   └── demo.png              # 实时演示截图
├── docs/
│   ├── deploy.md             # 板端环境搭建步骤（从裸板开始）
│   └── preprocessing.md      # ★ 预处理一致性说明（训练 vs 部署逐项对照）
└── README.md
```

### 运行约定

```bash
# 导出
python export_onnx.py --weights models/best_fp32.pt --out models/best_fp32.onnx --opset 17

# 一致性验证
python tools/check_consistency.py --onnx models/best_fp32.onnx --pt models/best_fp32.pt --data test_imgs/

# 基准（必须在板子上跑）
python tools/benchmark.py --model models/best_fp32.onnx --device cpu --seconds 60

# 推理
python infer.py --model models/best_fp32.onnx --device gpu --source camera
python infer.py --model models/best_fp32.onnx --source img.jpg --out dets.json
```

### `docs/preprocessing.md` 必须逐项对照

| 步骤 | 训练时 | 部署时 | 是否一致 |
| :-- | :-- | :-- | :--: |
| 通道顺序 | RGB | ? | |
| resize 方式 | letterbox? | ? | |
| 归一化 | /255? mean/std? | ? | |
| 输入尺寸 | 640×640 | ? | |
| 输出布局 | | | |

> 这张表是现场会重点看的——**部署精度掉点的第一原因就是这里不一致**。

---

## 5. 明确禁止

- 禁止只给"能跑"不验一致性（必须给 CosSim 与最大绝对差）
- 禁止板端依赖 PyTorch/TensorFlow（现场在干净环境跑）
- 禁止只测几帧就报 FPS（必须**连续 60 秒**）
- 禁止把首次推理的冷启动延迟混进平均（要说明怎么排除的）
- 禁止预处理与训练不一致却不自知（要交逐项对照表）
- 禁止只报一种设备的指标（题面要求三模式对比）
- 禁止用"看画面正常"代替一致性数值验证
