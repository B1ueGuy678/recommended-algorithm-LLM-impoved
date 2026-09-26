# W1 数据验收报告：A1 / A2

- 验收对象：A1（数据目录规范化）、A2（CSV → Parquet）
- 复现命令：`.venv\Scripts\python.exe scripts\w1_data_acceptance.py`
- 结论：**18 / 18 项通过，退出码 0**（0 项未达成）

> 本报告所有数字均来自第 6 节列出的可复现命令的实际输出，没有手工填写的数值。凡未实测的都不写。

---

## 1. 验收结果

| ID | 判据 | 结果 | 证据 |
|---|---|---|---|
| A1-1 | 全库只有一份权威副本（无重名文件） | PASS | 无重名文件 |
| A1-2 | 数据路径来自 `configs/data.yaml`，且脚本内无硬编码数据集目录名 | PASS | `configs/data.yaml` 声明矩阵 `['big', 'small']`；无脚本硬编码数据集目录名 |
| A1-3 | 数据目录都在 `data/` 下（已被 .gitignore 排除） | PASS | `raw_dir=data/KuaiRec 2.0/data` / `parquet_dir=data/KuaiRec 2.0/parquet` |
| A1-4 | 我们自己的代码没有落在 `data/` 下 | PASS | `data/` 下仅有数据集自带的 `loaddata.py` |
| A2-small-1 | 覆盖全部 8 列且无行丢失 | PASS | 8 列 / 4,676,570 行 / 1,411 用户 / 3,327 物品 |
| A2-small-2 | date 类型已统一（整数或 Date，不能是浮点） | PASS | 实际 `Int64`；date 空值 181,992 |
| A2-small-3 | time 解析为 Datetime **且无静默丢行** | PASS | `Datetime[us]`；time 空值 181,992 = date 空值 181,992 |
| A2-small-5 | time 与 timestamp 的偏移恒定 | PASS | 偏移取值 1 种，恒为 28,800,000 ms（= 8 小时） |
| A2-big-1 | 覆盖全部 8 列且无行丢失 | PASS | 8 列 / 12,530,806 行 / 7,176 用户 / 10,728 物品 |
| A2-big-2 | date 类型已统一（整数或 Date，不能是浮点） | PASS | 实际 `Int64`；date 空值 0 |
| A2-big-3 | time 解析为 Datetime **且无静默丢行** | PASS | `Datetime[us]`；time 空值 0 = date 空值 0 |
| A2-big-5 | time 与 timestamp 的偏移恒定 | PASS | 偏移取值 1 种，恒为 28,800,000 ms（= 8 小时） |
| A2-script:big_matrix_csv_to_parquet.py | 从 configs/data.yaml 读路径（无硬编码） | PASS | 引用 `data_paths`：是；硬编码数据集目录名：无 |
| A2-script:small_matrix_csv_to_parquet_cast_data.py | 从 configs/data.yaml 读路径（无硬编码） | PASS | 引用 `data_paths`：是；硬编码数据集目录名：无 |
| A2-paths:big | config 声明的 Parquet 路径 == 磁盘实际产物 | PASS | `data/KuaiRec 2.0/parquet/big_matrix.parquet` 存在 |
| A2-paths:small | config 声明的 Parquet 路径 == 磁盘实际产物 | PASS | `data/KuaiRec 2.0/parquet/small_matrix.parquet` 存在 |
| A2-small-4 | Parquet 体积更小且全量读入更快 | PASS | CSV 406.2 MB / 0.21s → Parquet 106.6 MB / 0.04s；体积 3.8x，速度 5.6x |
| A2-big-4 | Parquet 体积更小且全量读入更快 | PASS | CSV 1083.5 MB / 0.59s → Parquet 274.0 MB / 0.10s；体积 4.0x，速度 6.1x |

> `*-4` 的耗时在多次运行间有 ±10% 波动（同机负载），体积比稳定。

---

## 2. 数据路径的唯一权威来源（A1-2 的落地方式）

### `configs/data.yaml`

集中声明：`raw_dir`、`parquet_dir`、两个矩阵的 CSV / Parquet 文件名、7 个辅助文件（A3 画像与 LLM 语义特征源），以及转换参数（压缩、row group、时间格式）。相对路径一律相对仓库根目录解析。

关键设计：**`convert.time_format` 也放进 config**。上面那个 `%.f` / `%.3f` 的坑，一旦格式串在两个脚本里各写一份，就存在「只改了一个」的可能；放进 config 后只有一处定义。

### `scripts/data_paths.py`

路径的唯一入口，提供 `load_config()` / `matrix_paths(name)` / `convert_options()` / `side_file(key)`。两个转换脚本和验收脚本全部改为从这里取路径，脚本内不再出现数据集目录名。

放在 `scripts/` 而不是 `src/`：目前还没有正式包（没有 `pyproject.toml`），`scripts/` 下的脚本互相 import 零配置即可工作。等 `src/` 变成可安装的包之后，这个模块应整体搬过去并改为 `from recsys.data_paths import ...`。

### 判据为什么这样写

A1-2 的判据不是「有没有 config 文件」，而是**路径是否真的只由 config 决定**：

1. `configs/data.yaml` 存在，且声明的矩阵集合 == `{small, big}`；
2. 扫描 `scripts/*.py`，不允许任何脚本出现数据集目录名字面量。

只要还有脚本写着硬编码路径，config 就是摆设——改一处漏一处，重跑就会在旁边生成第二份副本。第 2 条是这条判据真正会咬人的地方。

---

## 3. 修复历史（均已实测确认）

| 轮次 | 问题 | 状态 |
|---|---|---|
| 第 1 轮 | 两个转换脚本声明的输出目录不一致，重跑会造出第二份副本 | 已修：脚本改名 + 输出统一到 `data/KuaiRec 2.0/parquet/` |
| 第 2 轮 | `time` 用 `%.3f` 解析，静默丢掉 big 10.00% / small 9.58% 的行 | 已修：改为 `%.f`，格式串移入 config |
| 第 2 轮 | 验收脚本只看 dtype，放过了上面的静默丢行 | 已修：判据改为 `time` 空值 ≤ `date` 空值 |
| 第 3 轮 | `configs/` 为空，数据路径硬编码在脚本里 | 已修：新增 `configs/data.yaml` + `scripts/data_paths.py`，三个脚本全部改读 config |

---

## 4. `time` 静默丢行的根因与修复

### 根因

原始 CSV 的 `time` 字符串**小数位数不固定**，有 1 / 2 / 3 位三种：

```
2020-07-05 00:08:23.438   3 位，长度 23  → 正常解析
2020-07-05 01:00:25.5     1 位，长度 21  → %.3f 下变 null
2020-07-05 03:28:02.32    2 位，长度 22  → %.3f 下变 null
```

原脚本用固定 3 位小数的 `format="%Y-%m-%d %H:%M:%S%.3f"`，只接受恰好 3 位；配合 `strict=False`，其余行被**静默**变成 `null`，不报任何错。

实测失败行的长度分布（big_matrix）：长度 22 有 1,127,254 行、长度 21 有 125,452 行，合计 1,252,706 —— 与空值数完全吻合，证据链闭合。

| 数据集 | 行数 | 原始 CSV 空值 | 修复前 `%.3f` | 修复后 `%.f` |
|---|---|---|---|---|
| big_matrix | 12,530,806 | 0 | **1,252,706（10.00%）** | **0** |
| small_matrix | 4,676,570 | 181,992 | **629,783** | **181,992** |

### 修复

格式串统一改为 `%.f`，定义在 `configs/data.yaml` 的 `convert.time_format`；两个转换脚本内也各留了注释说明为什么不能用 `%.3f`。`time` 精度由 ms 提升到 us（保留原始字符串的全部小数位）。

### 修复后的正确性验证（不只是「不为 null」）

用 `timestamp` 数值列作**独立基准**反推时间（`timestamp` 是 UTC 秒，加 8 小时应精确等于本地挂钟 `time`）——这条路径完全绕开字符串解析，任何小数秒缩放错误都会暴露：

| 数据集 | 参与比对行数 | 不符行数 | 最大偏差 |
|---|---|---|---|
| big_matrix | 12,530,806 | **0** | **0 us** |
| small_matrix | 4,494,578 | **0** | **0 us** |

抽样确认三种小数位数都被正确解析（无缩放错误）：

```
1 位: raw='2020-07-05 01:00:25.5'     -> parsed=2020-07-05 01:00:25.500000
2 位: raw='2020-07-05 03:28:02.32'    -> parsed=2020-07-05 03:28:02.320000
3 位: raw='2020-07-05 00:08:23.438'   -> parsed=2020-07-05 00:08:23.438000
```

---

## 5. 验收脚本自身修过的四个缺陷（记录，避免重犯）

四次都是**判据 / 测量方法**的错，不是数据的问题：

1. **CSV 读入耗时不可比**：初版用 `pl.scan_csv(...).select(pl.len()).collect()` 计时，Polars 的投影下推把它优化成「只数行数」，测出 0.04s / 406 MB 这种不可能的读数。现改为与 Parquet 同口径的**全量 eager 读入**（`pl.read_csv`）。
2. **RSS 不能作为判据**：同进程内先读 CSV 会把内存高水位抬高，随后读 Parquet 的 RSS 必然被污染；且 Polars 解码 Parquet 是多线程的，瞬时缓冲会让读数偏高。初版据此判出「Parquet 更吃内存」的假结论。现在 RSS 只作为参考值上报，**判定只用体积与耗时**两项稳定指标。
3. **只看 dtype 的判据会放过静默丢行**：`time` 的判据初版只要求是 `Datetime`，于是 `%.3f` 把 big 的 10% 行变成 `null` 仍然 PASS。现改为**以 `date` 的空值为基准**，要求 `time` 空值 ≤ `date` 空值，多出来的就算丢行。
4. **检测器把自己扫了进去（自指陷阱）**：A1-2 要扫描「脚本里有没有硬编码数据集目录名」，而这条判据的源码里恰好写着那个目录名字面量，于是它命中自己、报出一个假 FAIL。修法不是把字面量拆开藏起来，而是**让被禁的 token 来自 config**（它就是 `configs/data.yaml` 的 `dataset` 字段值），检测器源码里从此不含该字面量。同一轮还修了「用子串 `sink_parquet` 判断某脚本是不是转换脚本」的写法——它把本文件里那句提示信息也算成了一个转换脚本，现改为匹配真实调用 `.sink_parquet(`。

### 判据的可证伪性测试

一个「永远 PASS」的判据没有价值，所以对第 3 轮新增的判据做了一次反向验证：临时放入一个故意硬编码路径的探针脚本（`scripts/_tmp_hardcode_probe.py`），确认验收**挂掉并指名违规文件**：

```
A1-2   FAIL  └─ ...仍有脚本硬编码数据集目录名：_tmp_hardcode_probe.py
A2-script:_tmp_hardcode_probe.py  FAIL
汇总：17/19 通过，2 项未达成
```

随后删除探针，恢复 18/18（退出码 0）。探针已删除，不属于项目代码。

---

## 6. 复现方式

```powershell
# 在项目根目录
$env:PYTHONIOENCODING="utf-8"

# 1) 验收（退出码：0 = 全部通过；1 = 有未达成项）
.venv\Scripts\python.exe scripts\w1_data_acceptance.py

# 2) 重跑转换（路径来自 configs/data.yaml，重跑安全，不会产生第二份副本）
.venv\Scripts\python.exe scripts\small_matrix_csv_to_parquet_cast_data.py
.venv\Scripts\python.exe scripts\big_matrix_csv_to_parquet.py
```

第 4 节的根因复核（直接读原始 CSV，不经过验收脚本）：

```powershell
.venv\Scripts\python.exe -c "import polars as pl; df=pl.read_csv('data/KuaiRec 2.0/data/big_matrix.csv', columns=['time'], schema_overrides={'time': pl.Utf8}, infer_schema_length=0); s=df['time']; print('%.3f ->', s.str.to_datetime(format='%Y-%m-%d %H:%M:%S%.3f', strict=False).null_count()); print('%.f   ->', s.str.to_datetime(format='%Y-%m-%d %H:%M:%S%.f', strict=False).null_count())"
```

---

## 7. 实测数据事实（供 A3 使用）

| 维度 | small_matrix | big_matrix |
|---|---|---|
| 行数 | 4,676,570 | 12,530,806 |
| 用户数 | 1,411 | 7,176 |
| 物品数 | 3,327 | 10,728 |
| 列数 | 8 | 8 |
| date 空值 | 181,992（3.89%） | 0 |
| time 空值（= 原始 CSV 空行） | 181,992 | 0 |
| 有交互的天数 | 63 天连续（7/05–9/05） | 只有 28 天 |
| 时间结构 | 连续无缺口 | 三段：7/05–7/12、8/01–8/10、8/27–9/05 |
| `time` 精度 | `Datetime[us]` | `Datetime[us]` |
| 覆盖关系 | 用户与物品 100% 被 big 包含 | — |

- `small_matrix.csv` 中 181,992 行的 `time/date/timestamp` 三列**在原始 CSV 里就是空的**（形如 `14,6177,4407,7013,,,,0.6284043918437188`），已逐行扫描原始文件确认，不是转换缺陷。这也是其 `date` 列曾被推断为 `Float64` 的根因。
- `big_matrix` 的日期断成三段，**8/11–8/26 完全无数据**，直接限缩了 B1（时间切分）的可选窗口。
- **时区约定**：`time` / `date` 是 UTC+8 本地挂钟时间，`timestamp` 是 UTC 秒。两者相差恒为 28,800,000 ms（恰好 8 小时），在全部 12,530,806 + 4,494,578 行上取值唯一。这不是缺陷，但**跨这两列对齐时必须先统一时区**，否则按天聚合会在 UTC 16:00–24:00 的边界上错位一天。
- Parquet 产物：`data/KuaiRec 2.0/parquet/small_matrix.parquet`（106.6 MB，zstd）、`big_matrix.parquet`（274.0 MB，zstd），均 `row_group_size=100_000`。
