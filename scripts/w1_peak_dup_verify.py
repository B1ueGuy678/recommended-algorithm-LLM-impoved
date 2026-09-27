"""W1 峰值日重复写入核实（A4 补充 V1–V10）

背景：
    A3 逐日画像发现 big_matrix 有两个异常峰值日——8/05（1,300,721 行）与
    8/31（682,368 行）。本脚本检验一个具体假设：

        「这两个峰值是数据采集层面的重复写入，不是真实的行为爆发。」

    该假设若成立，则 B1 切分窗口（训练期含 8/05、测试期含 8/31）无需修改，
    但会给 B2（重复记录处置）与 W3（样本构造）划出明确红线。

检查项：
    V1   8/05 是完全重复行最集中的一天（全期 argmax）
    V2   8/05 的两个相邻日（8/04、8/06）完全重复行为 0
    V3   逐日行数的全期 argmax 是 8/05
    V4   按完全重复行去重后，8/05 不再是 argmax
    V5   去重后 8/05 行数与相邻日均值的相对偏差 ≤ 20%
    V6   8/31 的每一行都属于某个重复 (user,video) 对（占比 = 100%）
    V7   8/31 完全重复行数 = 当日行数 / 2（整日两两重复）
    V8   去重后 8/31 行数与相邻日均值的相对偏差 ≤ 20%
    V9   复现 A4 的全局数字：重复 pair 1,841,544 / 完全重复行 965,819
    V10  去重后全期无单日超过全期中位数的 2 倍（峰值整体消失）

用法：
    .venv\\Scripts\\python.exe scripts\\w1_peak_dup_verify.py

设计原则：
    1. 只读，不修改任何数据文件。
    2. 路径全来自 configs/data.yaml，不硬编码数据集目录名。
    3. 判据先写死再跑，不因结果回调阈值；FAIL 就如实报 FAIL。
    4. 退出码 0 = 全部判据通过；1 = 有判据未达成。
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from data_paths import load_config, matrix_paths

CFG = load_config()
SMALL_CSV, SMALL_PQ = matrix_paths("small", CFG)
BIG_CSV, BIG_PQ = matrix_paths("big", CFG)

# 被检验的两个峰值日，以及各自的相邻对照日
PEAK_A, PEAK_A_NEIGHBORS = 20200805, (20200804, 20200806)
PEAK_B, PEAK_B_NEIGHBORS = 20200831, (20200830, 20200901)

# A4 报告已公布的全局数字，用于交叉复现
A4_DUP_PAIRS = 1_841_544
A4_DUP_ROWS_REMOVED = 965_819

results: list[tuple[str, str, str, str]] = []


def check(cid: str, desc: str, ok: bool, evidence: str) -> None:
    results.append((cid, desc, "PASS" if ok else "FAIL", evidence))


def _sep(width: int = 72) -> None:
    print("─" * width)


# ---------------------------------------------------------------------------
# 逐日重复结构
# ---------------------------------------------------------------------------

def daily_dup_table(df: pl.DataFrame) -> pl.DataFrame:
    """返回逐日：总行数 / 完全重复行 / 去重后行数 / 重复 pair 数 / 重复 pair 涉及行数 / 去重后独立 pair 数。"""
    g_all = df.group_by("date").agg(pl.len().alias("rows"))

    uniq = df.unique()
    g_uniq = uniq.group_by("date").agg(pl.len().alias("uniq_rows"))

    pair = df.group_by(["date", "user_id", "video_id"]).agg(pl.len().alias("cnt"))
    g_pairs = pair.group_by("date").agg(pl.len().alias("distinct_pairs"))

    g_pair_dup = (
        pair.filter(pl.col("cnt") > 1)
        .group_by("date")
        .agg(
            pl.col("cnt").sum().alias("dup_pair_rows"),
            pl.len().alias("dup_pairs"),
        )
    )

    daily = (
        g_all.join(g_uniq, on="date", how="left")
        .join(g_pairs, on="date", how="left")
        .join(g_pair_dup, on="date", how="left")
        .with_columns(
            (pl.col("rows") - pl.col("uniq_rows")).alias("removed_dups"),
            pl.col("dup_pair_rows").fill_null(0),
            pl.col("dup_pairs").fill_null(0),
        )
        .sort("date")
    )
    return daily


def verify_big(pq: Path) -> tuple[pl.DataFrame, dict]:
    print(f"\n{'='*72}")
    print("  BIG 矩阵：峰值日重复写入核实")
    print(f"{'='*72}")

    df = pl.read_parquet(pq)
    total = len(df)
    print(f"  总行数：{total:,}   列数：{df.width}")

    # ── 全局重复结构（复现 A4）────────────────────────────────────────────
    uniq_total = df.unique().height
    removed_total = total - uniq_total
    pair_all = df.group_by(["user_id", "video_id"]).agg(pl.len().alias("cnt"))
    dup_pairs_total = int((pair_all["cnt"] > 1).sum())
    dup_pair_rows_total = int(pair_all.filter(pl.col("cnt") > 1)["cnt"].sum())
    max_repeat = int(pair_all["cnt"].max())
    print(f"\n  [全局] 完全重复行（被去除）：{removed_total:,}  ({removed_total/total*100:.4f}%)")
    print(f"  [全局] 重复 (user,video) pair：{dup_pairs_total:,}")
    print(f"  [全局] 重复 pair 涉及行数：{dup_pair_rows_total:,}  "
          f"({dup_pair_rows_total/total*100:.4f}% 的**行**，注意分母是行不是 pair)")
    print(f"  [全局] 单 pair 最大重复次数：{max_repeat:,}")

    distinct_pairs_global = pair_all.height
    pair_dedup_removed = total - distinct_pairs_global
    print(f"  [全局] (user,video) 级去重后行数：{distinct_pairs_global:,} "
          f"（去重删除 {pair_dedup_removed:,} 行 = {pair_dedup_removed/total*100:.4f}%）")

    check("V9-global-repro",
          "复现 A4 全局数字：dup pair 1,841,544 / 完全重复行 965,819",
          dup_pairs_total == A4_DUP_PAIRS and removed_total == A4_DUP_ROWS_REMOVED,
          f"dup pairs={dup_pairs_total:,} (期望 {A4_DUP_PAIRS:,}), "
          f"removed={removed_total:,} (期望 {A4_DUP_ROWS_REMOVED:,})")

    # ── 逐日表 ────────────────────────────────────────────────────────────
    daily = daily_dup_table(df)
    print(f"\n  逐日结构（{len(daily)} 天）：")
    print("    removed = 完全重复行（整行去重被去除的行数）")
    print("    uniq    = 整行去重后行数；pairs = (user,video) 级去重后行数（= 独立 pair 数）")
    print("    removed_pairs = 整行去重后又因 pair 重复被去除的行数（= rows - pairs - removed）")
    print(f"\n  {'date':<10} {'rows':>10} {'removed':>10} {'uniq':>10} {'pairs':>10} "
          f"{'rm_pairs':>9} {'dup_pairs':>10} {'dup_pair_rows':>14}")
    _sep(100)
    for r in daily.iter_rows(named=True):
        mark = ""
        if r["date"] in (PEAK_A, PEAK_B):
            mark = "  ← 峰值"
        elif r["date"] in PEAK_A_NEIGHBORS + PEAK_B_NEIGHBORS:
            mark = "  ← 对照"
        removed_pairs = r["rows"] - r["distinct_pairs"] - r["removed_dups"]
        print(f"  {r['date']:<10} {r['rows']:>10,} {r['removed_dups']:>10,} "
              f"{r['uniq_rows']:>10,} {r['distinct_pairs']:>10,} "
              f"{removed_pairs:>9,} {r['dup_pairs']:>10,} "
              f"{r['dup_pair_rows']:>14,}{mark}")

    # ── 两级去重的差额：整行去重 vs pair 级去重 ──────────────────────────
    print("\n  [两级去重差额] 整行去重后仍存在的「同 pair 不同值」重复行：")
    for d in (PEAK_A, PEAK_B) + PEAK_A_NEIGHBORS + PEAK_B_NEIGHBORS:
        r = daily.filter(pl.col("date") == d).row(0, named=True)
        diff = r["uniq_rows"] - r["distinct_pairs"]
        print(f"    {d}  uniq={r['uniq_rows']:>9,}  distinct_pairs={r['distinct_pairs']:>9,}  "
              f"差额={diff:>7,}  ({diff/r['rows']*100:6.3f}% of rows)")

    # ── V1  8/05 是完全重复行最集中的一天 ────────────────────────────────
    top_removed = daily.sort("removed_dups", descending=True).row(0, named=True)
    check("V1-peakA-dup-concentration",
          "8/05 是全期完全重复行最多的一天",
          top_removed["date"] == PEAK_A,
          f"argmax removed_dups = {top_removed['date']} ({top_removed['removed_dups']:,} 行)")

    # ── V2  8/05 相邻日完全重复行为 0 ────────────────────────────────────
    neigh_a = daily.filter(pl.col("date").is_in(list(PEAK_A_NEIGHBORS)))
    neigh_a_removed = {int(r["date"]): int(r["removed_dups"]) for r in neigh_a.iter_rows(named=True)}
    check("V2-peakA-neighbors-clean",
          "8/05 的两个相邻日完全重复行为 0",
          all(v == 0 for v in neigh_a_removed.values()) and len(neigh_a_removed) == 2,
          f"8/04={neigh_a_removed.get(PEAK_A_NEIGHBORS[0], -1):,}, "
          f"8/06={neigh_a_removed.get(PEAK_A_NEIGHBORS[1], -1):,}")

    # ── V3  逐日行数 argmax 是 8/05 ──────────────────────────────────────
    top_rows = daily.sort("rows", descending=True).row(0, named=True)
    check("V3-raw-argmax-is-peakA",
          "逐日原始行数的全期峰值为 8/05",
          top_rows["date"] == PEAK_A,
          f"argmax rows = {top_rows['date']} ({top_rows['rows']:,} 行)")

    # ── V4  去重后 8/05 不再是 argmax ────────────────────────────────────
    top_uniq = daily.sort("uniq_rows", descending=True).row(0, named=True)
    check("V4-uniq-argmax-not-peakA",
          "按完全重复行去重后，8/05 不再是全期峰值日",
          top_uniq["date"] != PEAK_A,
          f"去重后 argmax = {top_uniq['date']} ({top_uniq['uniq_rows']:,} 行)")

    # ── V5  去重后 8/05 与相邻日同量级（±20%）────────────────────────────
    row_a = daily.filter(pl.col("date") == PEAK_A).row(0, named=True)
    neigh_mean_a = sum(neigh_vals(daily, PEAK_A_NEIGHBORS, "uniq_rows")) / 2
    dev_a = abs(row_a["uniq_rows"] - neigh_mean_a) / neigh_mean_a
    check("V5-peakA-uniq-close-to-neighbors",
          "去重后 8/05 行数在相邻日均值 ±20% 内",
          dev_a <= 0.20,
          f"8/05 去重后={row_a['uniq_rows']:,}, 相邻日均值={neigh_mean_a:,.0f}, "
          f"偏差={dev_a*100:.2f}%")

    # ── V6 8/31 每行都属于重复 pair ──────────────────────────────────────
    row_b = daily.filter(pl.col("date") == PEAK_B).row(0, named=True)
    frac_b = row_b["dup_pair_rows"] / row_b["rows"]
    check("V6-peakB-all-rows-in-dup-pairs",
          "8/31 全部行都属于重复 (user,video) 对（占比 = 100%）",
          frac_b == 1.0,
          f"dup_pair_rows={row_b['dup_pair_rows']:,} / rows={row_b['rows']:,} = {frac_b*100:.4f}%")

    # ── V7 8/31 完全重复行 = 行数 / 2 ────────────────────────────────────
    check("V7-peakB-pairwise-duplicate",
          "8/31 完全重复行数 = 当日行数 / 2（整日两两重复）",
          row_b["removed_dups"] * 2 == row_b["rows"],
          f"removed={row_b['removed_dups']:,}, rows/2={row_b['rows']//2:,}, "
          f"去重后={row_b['uniq_rows']:,}")

    # ── V8 去重后 8/31 与相邻日同量级 ────────────────────────────────────
    neigh_b_vals = neigh_vals(daily, PEAK_B_NEIGHBORS, "uniq_rows")
    neigh_mean_b = sum(neigh_b_vals) / len(neigh_b_vals)
    dev_b = abs(row_b["uniq_rows"] - neigh_mean_b) / neigh_mean_b
    check("V8-peakB-uniq-close-to-neighbors",
          "去重后 8/31 行数在相邻日均值 ±20% 内",
          dev_b <= 0.20,
          f"8/31 去重后={row_b['uniq_rows']:,}, 相邻日均值={neigh_mean_b:,.0f}, "
          f"偏差={dev_b*100:.2f}%")

    # ── V10 去重后无单日超过中位数 2 倍 ──────────────────────────────────
    median_rows = daily["rows"].median()
    median_uniq = daily["uniq_rows"].median()
    ratio_before = float(daily["rows"].max()) / float(median_rows)
    ratio_after = float(daily["uniq_rows"].max()) / float(median_uniq)
    check("V10-uniq-no-outlier-day",
          "去重后全期无单日超过全期中位数的 2 倍",
          ratio_after <= 2.0,
          f"去重前 max/median={ratio_before:.3f}（max={daily['rows'].max():,}）, "
          f"去重后 max/median={ratio_after:.3f}（max={daily['uniq_rows'].max():,}, "
          f"median={median_uniq:,.0f}）")

    # ── V12 全局完全重复行是否全部集中在这两天 ──────────────────────────
    peak_days_removed = int(
        daily.filter(pl.col("date").is_in([PEAK_A, PEAK_B]))["removed_dups"].sum()
    )
    other_days_removed = int(
        daily.filter(~pl.col("date").is_in([PEAK_A, PEAK_B]))["removed_dups"].sum()
    )
    check("V12-dup-rows-localized",
          "全局完全重复行 100% 来自 8/05 与 8/31，其余 26 天为 0",
          other_days_removed == 0 and peak_days_removed == removed_total,
          f"两天合计={peak_days_removed:,}（8/05 {int(row_a['removed_dups']):,} + "
          f"8/31 {int(row_b['removed_dups']):,}）, 其余 26 天={other_days_removed:,}, "
          f"全局={removed_total:,}")

    # ── V14 pair 级去重的影响面是否只限坏天 ─────────────────────────────
    daily_pair_removed = int((daily["rows"] - daily["distinct_pairs"]).sum())
    normal_pair_removed = int(
        daily.filter(~pl.col("date").is_in([PEAK_A, PEAK_B]))
        .select((pl.col("uniq_rows") - pl.col("distinct_pairs")).sum())
        .item()
    )
    check("V14-pair-dedup-not-localized",
          "pair 级去重会删到正常日（不是「只修坏天」的操作）",
          normal_pair_removed > 0,
          f"pair 级去重全期删除 {daily_pair_removed:,} 行，"
          f"其中非峰值 26 天占 {normal_pair_removed:,} 行 "
          f"({normal_pair_removed/daily_pair_removed*100:.2f}%)")

    # ── 三级去重阶梯（全部数字在本脚本内算出，供报告直接引用）────────────
    stage1 = removed_total
    stage2 = daily_pair_removed - removed_total
    stage3 = pair_dedup_removed - daily_pair_removed
    peak_pair_removed = int(
        daily.filter(pl.col("date").is_in([PEAK_A, PEAK_B]))
        .select((pl.col("uniq_rows") - pl.col("distinct_pairs")).sum())
        .item()
    )
    print("\n  [三级去重阶梯]")
    print(f"    原始                              {total:>12,}")
    print(f"      − 整行完全重复                  {stage1:>12,}   ← 100% 来自 8/05 与 8/31")
    print(f"      = 整行去重后                    {total-stage1:>12,}")
    print(f"      − 日内同 pair 不同值            {stage2:>12,}   "
          f"← 正常日 {normal_pair_removed:,} + 峰值日 {peak_pair_removed:,}")
    print(f"      = 日内 (user,video) 去重后      {total-stage1-stage2:>12,}")
    print(f"      − 跨日重复 pair                 {stage3:>12,}   ← 横跨不同日期，不可归属单日")
    print(f"      = 全局 (user,video) 去重后      {total-pair_dedup_removed:>12,}")
    assert stage1 + stage2 + stage3 == pair_dedup_removed, "三级去重阶梯不自洽"
    assert peak_pair_removed + normal_pair_removed == stage2, "日内 pair 阶段的两天拆分不自洽"

    facts = {
        "total": total,
        "removed_total": removed_total,
        "dup_pairs_total": dup_pairs_total,
        "dup_pair_rows_total": dup_pair_rows_total,
        "max_repeat": max_repeat,
        "peak_a": row_a,
        "peak_b": row_b,
        "neigh_a_uniq_mean": neigh_mean_a,
        "neigh_b_uniq_mean": neigh_mean_b,
        "dev_a": dev_a,
        "dev_b": dev_b,
        "ratio_before": ratio_before,
        "ratio_after": ratio_after,
        "median_rows": float(median_rows),
        "median_uniq": float(median_uniq),
        "top_uniq": top_uniq,
        "top_rows": top_rows,
        "top_removed": top_removed,
        "peak_days_removed": peak_days_removed,
        "other_days_removed": other_days_removed,
        "daily_pair_removed": daily_pair_removed,
        "normal_pair_removed": normal_pair_removed,
        "distinct_pairs_global": distinct_pairs_global,
        "pair_dedup_removed": pair_dedup_removed,
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3,
        "peak_pair_removed": peak_pair_removed,
    }
    return daily, facts


def neigh_vals(daily: pl.DataFrame, days: tuple[int, ...], col: str) -> list[int]:
    sub = daily.filter(pl.col("date").is_in(list(days))).sort("date")
    return [int(v) for v in sub[col].to_list()]


# ---------------------------------------------------------------------------
# small 矩阵对照（它是无偏评估矩阵，8/31 落在测试窗口内）
# ---------------------------------------------------------------------------

def report_small(pq: Path) -> None:
    print(f"\n{'='*72}")
    print("  SMALL 矩阵：评估矩阵重复结构（对照）")
    print(f"{'='*72}")

    df = pl.read_parquet(pq)
    total = len(df)
    uniq = df.unique().height
    print(f"  总行数：{total:,}")
    print(f"  完全重复行（被去除）：{total - uniq:,}  ({(total-uniq)/total*100:.4f}%)")

    pair = df.group_by(["user_id", "video_id"]).agg(pl.len().alias("cnt"))
    dp = int((pair["cnt"] > 1).sum())
    print(f"  重复 (user,video) pair：{dp:,}")

    d31 = df.filter(pl.col("date") == PEAK_B)
    print(f"  8/31 行数：{len(d31):,}；完全重复行：{len(d31) - d31.unique().height:,}")
    d05 = df.filter(pl.col("date") == PEAK_A)
    print(f"  8/05 行数：{len(d05):,}；完全重复行：{len(d05) - d05.unique().height:,}")

    check("V11-small-no-duplicates",
          "small 矩阵无完全重复行（保持全观测评估矩阵的洁净）",
          total - uniq == 0,
          f"removed={total-uniq:,} ({((total-uniq)/total*100):.4f}%)")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    for pq, name in [(BIG_PQ, "big"), (SMALL_PQ, "small")]:
        if not pq.exists():
            print(f"[ERROR] {name} Parquet 不存在：{pq}")
            print("请先运行转换脚本生成 Parquet，再跑本核实脚本。")
            return 1

    daily, facts = verify_big(BIG_PQ)
    report_small(SMALL_PQ)

    width = max(len(d) for _, d, _, _ in results)
    print(f"\n{'='*72}")
    print("判据汇总")
    print(f"{'='*72}")
    print(f"{'ID':<36} {'判据':<{width}}  结果")
    _sep(36 + width + 10)
    for cid, desc, verdict, evidence in results:
        print(f"{cid:<36} {desc:<{width}}  {verdict}")
        print(f"{'':36} └─ {evidence}")

    failed = [r for r in results if r[2] == "FAIL"]
    print()
    print(f"汇总：{len(results) - len(failed)}/{len(results)} 通过，{len(failed)} 项未达成")
    for cid, desc, _, _ in failed:
        print(f"  ✗ {cid}  {desc}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
