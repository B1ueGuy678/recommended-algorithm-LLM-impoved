# W1 异常与重复扫描报告（A4）

> 生成日期：2026-09-27  
> 脚本：`scripts/w1_data_anomaly.py`（退出码 1，2 项 FAIL，见末节）  
> 数据源：`configs/data.yaml` 指向的 Parquet 文件，只读，未修改任何数据。

---

## 1. 完全重复行（A4-1）

| 矩阵 | 总行数 | 完全重复行数 | 占比 |
|---|---|---|---|
| small | 4,676,570 | **0** | 0.0000% |
| big | 12,530,806 | **965,819** | **7.7076%** |

big_matrix 有约 77 万行所有 8 列完全相同。结合 A4-2 的分析，这些重复行都属于同一 (user_id, video_id) 对的多条记录。

## 2. 重复 (user_id, video_id) 对（A4-2）

| 矩阵 | 有重复的 pair 数 | 涉及行数 | 占总行数 | 单 pair 最大重复次数 |
|---|---|---|---|---|
| small | **0** | 0 | 0.0000% | 1 |
| big | **1,841,544** | 4,071,381 | **14.6961%** | **2224** |

small_matrix 是严格的每个 (user,item) 对至多一条记录，这与它作为近全观测无偏评估矩阵的设计预期完全吻合。

big_matrix 中，184 万个 (user,video) 对出现超过一次，涉及行数超过 400 万（占 14.7%）。单个 pair 最多重复 2224 次，说明部分用户对同一视频有非常高频的反复播放行为。

**对后续任务的影响**：

- 样本构造时必须决定如何处理重复对：取最后一次记录、取最高 watch_ratio、聚合为用户行为序列特征，还是全部保留视为多个正样本。这是 B2 负采样策略的一部分，需本人拍板。
- big 的完全重复行（7.7%）是 (user,video) 重复对的子集，说明重复记录有时字段完全一致（watch_ratio、play_duration 等都相同），有时值不同（同一对用不同 watch_ratio 出现多次）。后一种情况在时序建模中可提取为行为序列，前一种更像数据冗余。

## 3. play_duration > video_duration（A4-3）

| 矩阵 | 参与校验行 | play > video 行数 | 占比 |
|---|---|---|---|
| small | 4,676,570 | **1,514,717** | **32.3895%** |
| big | 12,530,806 | **4,237,441** | **33.8162%** |

约三分之一的行出现播放时长超过视频时长。这**不是数据错误**，而是 `watch_ratio > 1` 现象的时长侧体现——用户重复观看（循环播放）导致累计播放时长超过单次视频时长。

与 A3-C4 的 `watch_ratio > 1` 占比（small 32.39%，big 33.82%）完全一致，印证了时长字段与 watch_ratio 完全自洽（A3-C5 PASS）。

## 4. video_duration = 0（A4-4）

| 矩阵 | video_duration = 0 | null |
|---|---|---|
| small | 0 | 0 |
| big | 0 | 0 |

两矩阵均无视频时长为零或空值的记录，分母安全，`watch_ratio` 计算无除零风险。

## 5. 时间戳越界（A4-5）⚠ FAIL

| 矩阵 | 参与校验行 | `timestamp` UTC+8 日期 ≠ `date` | 占比 | 判定 |
|---|---|---|---|---|
| small | 4,494,578 | **1,213** | 0.0270% | **FAIL** |
| big | 12,530,806 | **15,530** | 0.1239% | **FAIL** |

`timestamp`（UTC 秒）转换为 UTC+8 日期后，与 `date` 字段（YYYYMMDD）不一致的行数与 A3-V3 `time`/`date` 不一致行数完全相同（small 均为 1,213，big 均为 15,530）。这三条线索指向同一批行：

- `time`（UTC+8 Datetime）的日期部分 ≠ `date`（A3-V3）
- `timestamp`（UTC 秒 → UTC+8 日期） ≠ `date`（A4-5）

**归因（待确认）**：最可能的原因是原始数据记录时的跨午夜问题——行为发生在 UTC 16:00–24:00 之间时，UTC+8 已是次日，但 `date` 字段写入的是前一日（或反之）。这类边界错误在数据采集管道中很常见，但**目前仍是推测，未有原始日志佐证，标注「未归因」**。

**处理建议（供参考，不拍板）**：这 1,213（small）/ 15,530（big）行占比极小，但它们的日期字段不可信。若样本构造以 `date` 做时间切分，这些行的归属存疑；建议统一以 `timestamp` 为权威时间源，`date` 字段仅作参考。

---

## 判据汇总

| 判据 ID | 说明 | 结果 | 证据 |
|---|---|---|---|
| A4-1-dup-rows:small | small 完全重复行已计量 | PASS | 0 行 (0.0000%) |
| A4-2-dup-pairs:small | small 重复 (user,video) pair 已计量 | PASS | 0 pair, max=1 |
| A4-3-over-dur:small | small play>video_duration 异常已计量 | PASS | 1,514,717 行 (32.39%) |
| A4-4-vd-zero:small | small video_duration=0 已计量 | PASS | 0 行 |
| **A4-5-ts-bounds:small** | small 时间戳 UTC+8 日期与 date 一致 | **FAIL** | 1,213 行不一致 (0.0270%) |
| A4-1-dup-rows:big | big 完全重复行已计量 | PASS | 965,819 行 (7.71%) |
| A4-2-dup-pairs:big | big 重复 (user,video) pair 已计量 | PASS | 1,841,544 pair, 4,071,381 行 (14.70%), max=2224 |
| A4-3-over-dur:big | big play>video_duration 异常已计量 | PASS | 4,237,441 行 (33.82%) |
| A4-4-vd-zero:big | big video_duration=0 已计量 | PASS | 0 行 |
| **A4-5-ts-bounds:big** | big 时间戳 UTC+8 日期与 date 一致 | **FAIL** | 15,530 行不一致 (0.1239%) |

**汇总：8/10 通过，2 项 FAIL（均为 A4-5 时间戳越界，与 A3-V3 指向同一批行，未归因，量级 <0.13%）**
