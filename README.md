# LLM 语义增强的多阶段推荐系统

> 面向短视频 / 电商场景：**LLM 语义增强的用户序列建模 + 多目标精排 + 推理加速 + 离线反事实评估闭环**。
>
> 一个能同时打「推荐 / 广告 / 搜索」和「大模型落地」两个岗位标签的简历项目。核心思路：把 LLM 当**特征增强器**，而不是当产品外壳——纯 RAG 问答已经烂大街，LLM 特征增益 + 严格消融才是当前最能拉开差距的切入点。

---

## 1. 项目定位

大厂算法实习 HC 最多的方向是推荐，而 LLM 特征增强是当下最热的能力标签。一个项目同时证明两件事：

1. **传统推荐全链路**：召回 → 粗排 → 精排 → 重排，每一段有 baseline、有指标、有消融；
2. **大模型落地**：LLM 语义表示进特征链路，并且能说清它带来的增益与代价。

只做「RAG 问答机器人」证明不了第一件事；只做「DIN 复现」证明不了第二件事。

---

## 2. 六项交付（全部完成才配叫「端到端」）

| # | 交付物 | 验收标准 |
|---|---|---|
| 1 | **可复现的离线评估框架** | 指标函数、时间切分、负采样协议、baseline（ItemCF + LR）一键跑通，固定随机种子 |
| 2 | **多路召回 + ANN 检索** | 双塔向量召回、ItemCF、热门兜底并行，输出召回率–延迟曲线 |
| 3 | **多任务精排模型** | 行为序列建模 + CTR / CVR / 时长多目标，含完整消融实验表 |
| 4 | **LLM 语义特征链路** | 行为序列文本化 → LoRA 微调小模型 → 产出 embedding 并验证增益（尤其冷启动用户） |
| 5 | **可部署的推理服务** | 蒸馏 + INT8 量化 + ONNX Runtime，给出 QPS 与 P99 实测数据 |
| 6 | **闭环实验与技术报告** | 离线反事实评估（IPS / DR）+ 显著性检验 + 可复现的开源仓库与 README 报告 |

只做前两项 = 课程作业；六项做完 = 端到端链路作品。

---

## 3. 技术栈

| 层 | 关键技术组合 | 面试官要看到的点 |
|---|---|---|
| 数据与评估 | Polars / DuckDB / PyArrow、Parquet；KuaiRec、MIND-small、Amazon-Reviews | 评估协议自己写得出、baseline 能复现 |
| 多路召回 | ItemCF / Swing、DSSM 双塔、Faiss / hnswlib、热门与冷启兜底 | 召回率与多样性、ANN 的 recall–latency 权衡 |
| 粗排 | 轻量双塔 / MLP、精排蒸馏、in-batch + hard negative | 为什么需要粗排、蒸馏如何对齐教师分数 |
| 精排 | DIN / DIEN / BST、MMoE / PLE 多任务、稀疏 Embedding 优化 | 序列建模为何有效、多目标 loss 如何配权 |
| LLM 增强 | 商品 / 行为文本化、Sentence-Embedding（bge-m3、Qwen3-Embedding-0.6B）、LoRA 微调 0.5B–1.5B | LLM 特征增益多少、消融是否可信 |
| 推理与服务 | ONNX Runtime（备选 Triton / WSL2）、INT8 量化、FastAPI + gRPC、Redis 实时特征 | P99 与吞吐、量化后精度掉多少 |
| 实验与评估 | MLflow / W&B、Prometheus + Grafana、全观测矩阵离线反事实评估 | 显著性与样本量、position bias 如何纠偏 |
| 工程规范 | Git 分支流、pytest、配置化、一键复现脚本 | 别人 clone 就能跑，报告数字可复现 |

**数据选型**：**KuaiRec**（含完整曝光日志 + fully-observed 交互矩阵，能做纠偏与离线反事实评估，三个里含金量最高）> MIND-small（新闻，文本丰富，适合 LLM 特征）> Amazon-Reviews（最省事，评估最弱）。

---

## 4. 8 周落地节奏

| 周 | 目标 | 关键产出 |
|---|---|---|
| **W1** | 数据与评估地基 | 指标函数、时间切分、可复现 baseline（ItemCF + LR）。这步做烂，后面所有数字都不可信 |
| **W2** | 多路召回 | 训练双塔 + 建 ANN 索引，画召回率–延迟曲线，确定各路召回配比 |
| **W3** | 特征与粗排 | 特征管道与样本构造、粗排上线并完成第一次蒸馏 |
| **W4–5** | 精排多任务 | DIN / DIEN 序列建模 + MMoE 多目标；序列长度、负采样、loss 配权消融 |
| **W6** | LLM 语义增强 | 行为序列文本化 + LoRA 微调小模型产 embedding；「有/无 LLM 特征」严格消融 |
| **W7** | 推理优化 | 精排蒸馏回粗排、INT8 量化、ONNX Runtime 部署，产出 P99 与 QPS |
| **W8** | 评估与报告 | 离线反事实评估与显著性检验，写技术报告，整理可复现仓库 |

节奏强度：每天 2–3 小时，周末补大块时间。

---

## 5. 该盯住的指标

| 指标 | 基线（先自己复现） | 目标区间（以实测为准） |
|---|---|---|
| HR@10 / NDCG@10（召回） | ItemCF / 热门 | 相对提升 8%–20% |
| AUC / GAUC（排序） | LR + 手工特征 或 Wide&Deep | AUC +0.01 ~ 0.03，GAUC 涨幅更关键 |
| 多目标任务 | 单任务 ShareBottom | 至少一个目标不掉点 |
| 推理 P99 | PyTorch 原生单请求 | ≤ 30 ms（量化 + ONNX 后） |
| 量化后精度保持 | FP32 基线 | AUC 掉幅 ≤ 0.002 |

---

## 6. 本机硬件与环境基线（实测）

| 项 | 实测值 | 影响 |
|---|---|---|
| 显卡 | **RTX 4060 Laptop 8GB**（Ada，compute 8.9，驱动 616.64，支持 bf16） | 可跑全链路；LLM 部分上限 1.5B LoRA |
| GPU 功耗 | 上限 140W，**默认仅 55W** | ⚠️ 不改设置所有训练慢一倍以上，插电 + 厂商性能模式 |
| CPU / 内存 | i7-14650HX（24 线程）/ **16 GB** | 内存是真正的瓶颈：放弃 MIND-large，Polars 流式落 Parquet |
| 磁盘 | C 盘剩 ~162 GB，D 盘剩 ~236 GB | 数据与 checkpoint 全放 D 盘 |
| 软件 | 系统 Python 3.13.15，已有 uv / git；无 conda、Docker。项目 `.venv` 已建：**Python 3.12.13 + torch 2.6.0+cu124，`cuda.is_available() = True`** | 用 uv 建 3.12 虚拟环境（3.13 上不少 ML 库轮子不全） |

**按 8GB 显存 / 16GB 内存标定的关键参数**

| 环节 | 本机现实 | 采用方案 |
|---|---|---|
| LLM 微调 | 8GB 显存，桌面已占 ~2.7GB | 只做 0.5B–1.5B LoRA；7B 直接排除（本项目用不上） |
| 精排训练 | 显存 6–8GB | 序列长度 50→30、batch 512、开梯度检查点 + bf16 |
| LoRA 主线（0.5B / 0.6B） | 约 3.5 GB 显存 | r=8 / alpha=16、seq_len 512、8 × 8 梯度累积、3–5 小时 |
| LoRA 加分项（1.5B / 1.7B） | 约 5.5 GB（必须先关浏览器） | r=8 / alpha=16、seq_len 512、4 × 16 梯度累积、10–15 小时 |
| 训练样本构造 | KuaiRec 仅 7176 用户 | ⚠️ 按「用户 + 滑动时间窗」切窗约 20 条/人，凑到 10 万量级，否则 LoRA 训不动 |
| 服务部署 | Triton 无 Windows 官方版 | onnxruntime-gpu + FastAPI；需要 Triton 再装 WSL2 |

**环境搭建（照抄即可）**

```powershell
# 1) 用 uv 装一个 3.12（3.13 上不少 ML 库轮子不全）
uv python install 3.12

# 2) 项目根目录（本仓库）
cd "D:/DeepSeek/recommended algorithm-LLM-impoved"
uv venv .venv --python 3.12
.venv/Scripts/Activate.ps1

# 3) CUDA 版 PyTorch
uv pip install torch --index-url https://download.pytorch.org/whl/cu124

# 4) 其余依赖
uv pip install polars duckdb pyarrow faiss-cpu hnswlib scikit-learn
uv pip install transformers peft datasets accelerate
uv pip install onnxruntime-gpu optimum

# 5) 验证：必须打印 True 和 NVIDIA GeForce RTX 4060 Laptop GPU
python -c "import torch;print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"

# 6) 训练前设置，减少显存碎片（否则 8GB 容易莫名 OOM）
$env:PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
```

---

## 7. 目录规划（随开发逐步落地）

```
.
├── configs/          # 实验配置文件（yaml），入库——实验记录的一部分
├── data/             # 原始与中间数据（不入库，见 .gitignore）
├── notebooks/        # 探索性分析（结论需回落到脚本）
├── scripts/          # 一键复现入口：数据处理 / 训练 / 评估 / 导出
├── src/              # 源码包：data / recall / rank / llm / serve / eval
├── tests/            # pytest 单测与数据契约测试
├── reports/          # 技术报告、消融表、图表（入库）
├── README.md         # 项目宪章：定位 / 交付 / 技术栈 / 节奏 / 红线
└── handoff.md        # 交接文档：可信数字、踩坑、未完成项（入库）
```

---

## 8. 红线

- ==绝不编造数字==：进简历的每个数字都必须来自本机终端真实跑出的输出，且能当场复现。
- 不做「只有离线好看」的模型：**特征穿越**是这类项目的第一死因——代码不报错，只让指标虚高。
- 不把本地模拟说成线上 A/B：写「模拟分流实验 / 离线反事实评估」才经得起追问。
- 不只做 demo：能解释每一步为什么这么做，比刷到 SOTA 重要。
- **AI 可以写代码，不能定标准**：评估协议、特征穿越排查、异常归因、消融对照设计、结果叙事必须本人拍板。
- **验收要可执行**：不接受「我检查过了」，只接受「跑这个脚本，退出码 0」。判据要能挂掉——放一个故意违规的探针验证过，才算它真的在检查。
- **踩坑要留档**：踩过的坑写进报告与交接文档，避免重犯。

---

## 9. 面试必被追问的五件事

1. 为什么用 GAUC 而不是全局 AUC？正负样本怎么采的？
2. LLM embedding 到底带来多少增益，去掉它会掉多少？（没有这张消融表，项目在面试官眼里就是蹭热点）
3. 精排蒸馏回粗排，教师分数怎么对齐？排序损失还是回归损失？
4. 评估跑了多少样本、显著性怎么算？「这个提升不显著」你如何反驳？
5. 特征穿越是在哪一步发现的？
