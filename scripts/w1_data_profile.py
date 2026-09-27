"""W1 数据画像（A3）：规模 / 用户长尾 / 物品热度 / watch_ratio / 时长自洽 /
每日交互量 / 特征源可用性 / 全观测性 / 日期一致性

用法：
    .venv\\Scripts\\python.exe scripts\\w1_data_profile.py

设计原则：
  1. 只读，不修改任何数据文件。
  2. 一切路径来自 configs/data.yaml，脚本内不硬编码数据集目录名。
  3. 报告里每个数字都能在输出里找到对应行（A3-P2）。
  4. 退出码 0 = 全部判据通过；1 = 有未达成项（A3-P1）。
  5. 只出事实与数据支持度，不替用户拍板 B1–B6（A3-B1）。
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from data_paths import load_config, matrix_paths, side_file

CFG = load_config()
SMALL_CSV, SMALL_PQ = matrix_paths("small", CFG)
BIG_CSV, BIG_PQ = matrix_paths("big", CFG)

results: list[tuple[str, str, str, str]] = []


def check(cid: str, desc: str, ok: bool, evidence: str) -> None:
    results.append((cid, desc, "PASS" if ok else "FAIL", evidence))


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _sep(width: int = 72) -> None:
    print("─" * width)


def _quantile_row(s: pl.Series, qs: list[float]) -> dict[str, float]:
    return {f"p{int(q * 100)}": round(s.quantile(q), 4) for q in qs}


def _lt_stats(counts: pl.Series, thresh: int = 10) -> dict:
    """给定每用户/物品的交互计数序列，返回长尾统计。"""
    return {
        **_quantile_row(counts, [0.25, 0.50, 0.75, 0.90, 0.99]),
        "max": int(counts.max()),
        f"lt{thresh}_count": int((counts < thresh).sum()),
        f"lt{thresh}_pct": round(float((counts < thresh).sum()) / len(counts) * 100, 2),
    }


# ---------------------------------------------------------------------------
# 核心 profile（每矩阵调用一次）
# ---------------------------------------------------------------------------

def profile_matrix(name: str, pq: Path) -> dict:
    """对单个 Parquet 矩阵做全量统计，返回画像字典。"""
    lf = pl.scan_parquet(pq)

    # ── 规模 ─────────────────────────────────────────────────────────────
    agg = lf.select(
        pl.len().alias("rows"),
        pl.col("user_id").n_unique().alias("users"),
        pl.col("video_id").n_unique().alias("items"),
        pl.col("date").min().alias("date_min"),
        pl.col("date").max().alias("date_max"),
        pl.col("date").n_unique().alias("date_days"),
        pl.col("date").null_count().alias("date_null"),
    ).collect().to_dicts()[0]

    # ── watch_ratio 分布 ──────────────────────────────────────────────────
    wr_raw = lf.select(pl.col("watch_ratio")).collect()["watch_ratio"]
    wr = wr_raw.drop_nulls()
    wr_stats = {
        "min": round(float(wr.min()), 6),
        "max": round(float(wr.max()), 6),
        "mean": round(float(wr.mean()), 6),
        **_quantile_row(wr, [0.25, 0.50, 0.75, 0.90, 0.99]),
        "gt1_count": int((wr > 1).sum()),
        "gt1_pct": round(float((wr > 1).sum()) / len(wr) * 100, 4),
        "eq0_count": int((wr == 0).sum()),
        "eq0_pct": round(float((wr == 0).sum()) / len(wr) * 100, 4),
        "null_count": int(wr_raw.null_count()),
    }

    # ── 用户活跃度长尾（A3-C2）───────────────────────────────────────────
    user_counts = (
        lf.group_by("user_id").agg(pl.len().alias("cnt"))
        .select("cnt").collect()["cnt"]
    )
    user_lt = _lt_stats(user_counts, thresh=10)

    # ── 物品热度长尾（A3-C3）─────────────────────────────────────────────
    item_counts = (
        lf.group_by("video_id").agg(pl.len().alias("cnt"))
        .select("cnt").collect()["cnt"]
    )
    item_lt = _lt_stats(item_counts, thresh=10)

    # ── 时长自洽（A3-C5）：watch_ratio ≈ play_duration / video_duration ──
    # 仅对 video_duration > 0 且三列均非空的行检验
    c5_df = (
        lf.filter(
            pl.col("video_duration").is_not_null()
            & (pl.col("video_duration") > 0)
            & pl.col("play_duration").is_not_null()
            & pl.col("watch_ratio").is_not_null()
        )
        .select(
            pl.len().alias("eligible"),
            (
                (
                    pl.col("play_duration").cast(pl.Float64)
                    / pl.col("video_duration").cast(pl.Float64)
                    - pl.col("watch_ratio")
                ).abs() > 0.01
            ).sum().alias("mismatch"),
        )
        .collect()
        .to_dicts()[0]
    )

    # ── 日期与时间一致性（A3-V3）──────────────────────────────────────────
    # date 是 Int64 YYYYMMDD 格式；将 time 重建成同格式整数再比对
    v3_df = (
        lf.filter(
            pl.col("time").is_not_null() & pl.col("date").is_not_null()
        )
        .select(
            pl.len().alias("eligible"),
            (
                pl.col("time").dt.year().cast(pl.Int64) * 10000
                + pl.col("time").dt.month().cast(pl.Int64) * 100
                + pl.col("time").dt.day().cast(pl.Int64)
                != pl.col("date")
            ).sum().alias("mismatch"),
        )
        .collect()
        .to_dicts()[0]
    )

    # ── 每日交互量（A3-C1）───────────────────────────────────────────────
    daily = (
        lf.group_by("date")
        .agg(
            pl.len().alias("interactions"),
            pl.col("user_id").n_unique().alias("active_users"),
            pl.col("video_id").n_unique().alias("active_items"),
        )
        .sort("date")
        .collect()
    )

    return {
        "name": name,
        "rows": agg["rows"],
        "users": agg["users"],
        "items": agg["items"],
        "date_min": agg["date_min"],
        "date_max": agg["date_max"],
        "date_days_unique": agg["date_days"],
        "date_null": agg["date_null"],
        "wr": wr_stats,
        "user_lt": user_lt,
        "item_lt": item_lt,
        "c5": c5_df,
        "v3": v3_df,
        "daily": daily,
    }


# ---------------------------------------------------------------------------
# 全观测性（A3-V1，仅 small）
# ---------------------------------------------------------------------------

def profile_observability(pq: Path) -> dict:
    lf = pl.scan_parquet(pq)
    users = lf.select(pl.col("user_id").n_unique()).collect().item()
    items = lf.select(pl.col("video_id").n_unique()).collect().item()
    expected = users * items
    actual_pairs = (
        lf.select(["user_id", "video_id"]).unique()
        .select(pl.len()).collect().item()
    )
    dup_pairs = (
        lf.group_by(["user_id", "video_id"]).agg(pl.len().alias("cnt"))
        .filter(pl.col("cnt") > 1)
        .select(pl.len()).collect().item()
    )
    return {
        "users": users,
        "items": items,
        "expected_pairs": expected,
        "actual_pairs": actual_pairs,
        "gap": expected - actual_pairs,
        "coverage_pct": round(actual_pairs / expected * 100, 4),
        "dup_user_item_pairs": int(dup_pairs),
    }


# ---------------------------------------------------------------------------
# 特征源可用性（A3-C6）
# ---------------------------------------------------------------------------

def profile_feature_coverage(big_items: set, cfg: dict) -> dict:
    """item_daily_features 日期范围 / 列清单；caption 对 big 物品的覆盖率。"""
    idf_path = side_file("item_daily_features", cfg)
    cap_path = side_file("kuairec_caption_category", cfg)

    idf_lf = pl.scan_csv(idf_path)
    idf_cols = list(idf_lf.collect_schema().names())
    idf_rows = idf_lf.select(pl.len()).collect().item()
    idf_items = idf_lf.select(pl.col("video_id").n_unique()).collect().item()

    date_col = next((c for c in idf_cols if "date" in c.lower()), None)
    if date_col:
        d = idf_lf.select(
            pl.col(date_col).min().alias("dmin"),
            pl.col(date_col).max().alias("dmax"),
        ).collect().to_dicts()[0]
    else:
        d = {"dmin": None, "dmax": None}

    idf_item_set = set(idf_lf.select("video_id").collect()["video_id"].to_list())
    idf_cov = len(idf_item_set & big_items) / len(big_items) * 100 if big_items else 0.0

    cap_lf = pl.scan_csv(cap_path)
    cap_items = cap_lf.select(pl.col("video_id").n_unique()).collect().item()
    cap_item_set = set(cap_lf.select("video_id").collect()["video_id"].to_list())
    cap_cov = len(cap_item_set & big_items) / len(big_items) * 100 if big_items else 0.0

    return {
        "idf_cols": idf_cols,
        "idf_rows": idf_rows,
        "idf_items": idf_items,
        "idf_date_col": date_col,
        "idf_date_min": d["dmin"],
        "idf_date_max": d["dmax"],
        "idf_coverage_pct": round(idf_cov, 2),
        "cap_items": cap_items,
        "cap_coverage_pct": round(cap_cov, 2),
    }


# ---------------------------------------------------------------------------
# 打印 & 判据
# ---------------------------------------------------------------------------

def report_scale(p: dict) -> None:
    name = p["name"]
    print(f"\n{'='*72}")
    print(f"  {name.upper()} 矩阵规模盘点")
    print(f"{'='*72}")
    print(f"  行数          {p['rows']:>15,}")
    print(f"  用户数        {p['users']:>15,}")
    print(f"  物品数        {p['items']:>15,}")
    date_min, date_max = p["date_min"], p["date_max"]
    days_unique = p["date_days_unique"]
    print(f"\n  日期范围      {date_min} → {date_max}  （{days_unique} 个有数据的天）")
    print(f"  date 空值     {p['date_null']:,} 行")
    ok = p["rows"] > 0 and p["users"] > 0 and p["items"] > 0 and date_min is not None
    check(f"A3-C1-scale:{name}", f"{name}: 规模四项均已测量",
          ok, f"{p['rows']:,} 行/{p['users']:,} 用户/{p['items']:,} 物品/{date_min}→{date_max}")


def report_user_lt(p: dict) -> None:
    name, u = p["name"], p["user_lt"]
    print(f"\n  用户活跃度长尾（A3-C2，{name}）")
    _sep(60)
    print(f"  p25={u['p25']}  p50={u['p50']}  p75={u['p75']}  p90={u['p90']}  p99={u['p99']}  max={u['max']}")
    print(f"  交互数 < 10 的用户：{u['lt10_count']:,} 人 ({u['lt10_pct']:.2f}%)")
    check(f"A3-C2-user-lt:{name}", f"{name}: 用户活跃度长尾已测量", True,
          f"p50={u['p50']}, lt10={u['lt10_count']:,} ({u['lt10_pct']:.2f}%)")


def report_item_lt(p: dict) -> None:
    name, it = p["name"], p["item_lt"]
    print(f"\n  物品热度长尾（A3-C3，{name}）")
    _sep(60)
    print(f"  p25={it['p25']}  p50={it['p50']}  p75={it['p75']}  p90={it['p90']}  p99={it['p99']}  max={it['max']}")
    print(f"  曝光数 < 10 的物品：{it['lt10_count']:,} 个 ({it['lt10_pct']:.2f}%)")
    check(f"A3-C3-item-lt:{name}", f"{name}: 物品热度长尾已测量", True,
          f"p50={it['p50']}, lt10={it['lt10_count']:,} ({it['lt10_pct']:.2f}%)")


def report_watch_ratio(p: dict) -> None:
    name, wr = p["name"], p["wr"]
    print(f"\n  watch_ratio 分布（A3-C4，{name}）")
    _sep(60)
    print(f"  min={wr['min']}  max={wr['max']}  mean={wr['mean']}")
    print(f"  p25={wr['p25']}  p50={wr['p50']}  p75={wr['p75']}  p90={wr['p90']}  p99={wr['p99']}")
    print(f"  > 1: {wr['gt1_count']:,} 行 ({wr['gt1_pct']:.2f}%)   "
          f"= 0: {wr['eq0_count']:,} 行 ({wr['eq0_pct']:.2f}%)   null: {wr['null_count']:,}")
    check(f"A3-C4-wr:{name}", f"{name}: watch_ratio 分布已测量",
          wr["min"] is not None,
          f"p50={wr['p50']}, >1 {wr['gt1_pct']:.2f}%, =0 {wr['eq0_pct']:.2f}%, null={wr['null_count']}")


def report_duration(p: dict) -> None:
    name, c5 = p["name"], p["c5"]
    eligible, mismatch = c5["eligible"], c5["mismatch"]
    ok = mismatch == 0
    pct = round(mismatch / eligible * 100, 4) if eligible > 0 else 0.0
    print(f"\n  时长自洽（A3-C5，{name}）")
    _sep(60)
    print(f"  参与校验行：{eligible:,}  |watch_ratio − play/video| > 0.01：{mismatch:,} ({pct:.4f}%)")
    check(f"A3-C5-duration:{name}", f"{name}: watch_ratio ≈ play/video 自洽",
          ok, f"eligible={eligible:,}, mismatch={mismatch:,} ({pct:.4f}%)")


def report_date_time(p: dict) -> None:
    name, v3 = p["name"], p["v3"]
    eligible, mismatch = v3["eligible"], v3["mismatch"]
    ok = mismatch == 0
    print(f"\n  date / time 一致性（A3-V3，{name}）")
    _sep(60)
    print(f"  参与校验行（time & date 均非空）：{eligible:,}  不一致行：{mismatch:,}")
    check(f"A3-V3-datetime:{name}", f"{name}: date == time 的日期部分",
          ok, f"eligible={eligible:,}, mismatch={mismatch:,}")


def report_daily(p: dict) -> None:
    name, daily = p["name"], p["daily"]
    n = len(daily)
    print(f"\n  每日交互量（{name}，共 {n} 天有数据）")
    _sep(72)
    print(f"  {'date':>10}  {'interactions':>14}  {'active_users':>13}  {'active_items':>13}")
    _sep(72)
    for row in daily.iter_rows(named=True):
        print(f"  {str(row['date']):>10}  {row['interactions']:>14,}  "
              f"{row['active_users']:>13,}  {row['active_items']:>13,}")
    _sep(72)
    ia = daily["interactions"]
    print(f"  交互量 min={ia.min():,}  max={ia.max():,}  mean={ia.mean():.0f}  median={ia.median():.0f}")
    check(f"A3-C1-daily:{name}", f"{name}: 逐日交互量已测量", n > 0,
          f"{n} 天；min={ia.min():,} max={ia.max():,} mean={ia.mean():.0f}")


def report_observability(obs: dict) -> None:
    print(f"\n  全观测性（A3-V1，small）")
    _sep(60)
    print(f"  用户数 × 物品数 = {obs['users']:,} × {obs['items']:,} = {obs['expected_pairs']:,}")
    print(f"  实际 (user,item) 唯一对     ：{obs['actual_pairs']:,}")
    print(f"  差值（expected − actual）   ：{obs['gap']:,}")
    print(f"  覆盖率                       ：{obs['coverage_pct']:.4f}%")
    print(f"  有重复记录的 (user,item) 对  ：{obs['dup_user_item_pairs']:,}")
    ok = obs["coverage_pct"] >= 99.0
    check("A3-V1-observability", "small 矩阵全观测覆盖率 ≥ 99%",
          ok, f"{obs['coverage_pct']:.4f}% ({obs['actual_pairs']:,}/{obs['expected_pairs']:,}), gap={obs['gap']:,}")


def report_feature_coverage(fc: dict) -> None:
    print(f"\n  特征源可用性（A3-C6）")
    _sep(72)
    print(f"  item_daily_features 列：{fc['idf_cols']}")
    print(f"  行数 {fc['idf_rows']:,}，物品数 {fc['idf_items']:,}，"
          f"日期 {fc['idf_date_min']} → {fc['idf_date_max']}")
    print(f"  对 big 物品的覆盖率（item_daily_features） ：{fc['idf_coverage_pct']:.2f}%")
    print(f"  caption 物品数 {fc['cap_items']:,}，对 big 物品的覆盖率：{fc['cap_coverage_pct']:.2f}%")
    ok_idf = fc["idf_coverage_pct"] > 0
    ok_cap = fc["cap_coverage_pct"] > 0
    check("A3-C6-idf", "item_daily_features 日期范围与列已测量", ok_idf,
          f"行={fc['idf_rows']:,}, 物品={fc['idf_items']:,}, big覆盖={fc['idf_coverage_pct']:.2f}%")
    check("A3-C6-caption", "caption 对 big 物品覆盖率已测量", ok_cap,
          f"caption物品={fc['cap_items']:,}, big覆盖={fc['cap_coverage_pct']:.2f}%")


def report_compare(sp: dict, bp: dict) -> None:
    print(f"\n{'='*72}")
    print("  两矩阵对比")
    print(f"{'='*72}")
    s_days = {d for d in sp["daily"]["date"].to_list() if d is not None}
    b_days = {d for d in bp["daily"]["date"].to_list() if d is not None}
    overlap = s_days & b_days
    only_s = s_days - b_days
    only_b = b_days - s_days
    print(f"  small 有数据天数：{len(s_days)}，big：{len(b_days)}，交集：{len(overlap)}")
    print(f"  仅 small：{len(only_s)} 天" + (f"  → {sorted(only_s)}" if only_s else ""))
    print(f"  仅 big  ：{len(only_b)} 天" + (f"  → {sorted(only_b)}" if only_b else ""))
    check("A3-C1-compare", "两矩阵日期交集 > 0", len(overlap) > 0,
          f"small {len(s_days)} 天/big {len(b_days)} 天/交集 {len(overlap)} 天")
    print(f"\n  [B4 数据支持度]  small p50(wr)={sp['wr']['p50']}, >1 占比 {sp['wr']['gt1_pct']:.2f}%")
    print(f"                   big   p50(wr)={bp['wr']['p50']}, >1 占比 {bp['wr']['gt1_pct']:.2f}%")
    print(f"  （B4 标签阈值请本人拍板，此处只提供数据支持度）")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    for pq, name in [(SMALL_PQ, "small"), (BIG_PQ, "big")]:
        if not pq.exists():
            print(f"[ERROR] {name} Parquet 不存在：{pq}")
            print("请先运行转换脚本生成 Parquet，再跑本画像脚本。")
            return 1

    print("正在读取 Parquet（首次可能需要十几秒）...")
    sp = profile_matrix("small", SMALL_PQ)
    bp = profile_matrix("big", BIG_PQ)

    for p in [sp, bp]:
        report_scale(p)
        report_user_lt(p)
        report_item_lt(p)
        report_watch_ratio(p)
        report_duration(p)
        report_date_time(p)
        report_daily(p)

    report_compare(sp, bp)

    print("\n正在计算全观测性与特征源覆盖率...")
    obs = profile_observability(SMALL_PQ)
    report_observability(obs)

    big_items = set(
        pl.scan_parquet(BIG_PQ).select("video_id").collect()["video_id"].to_list()
    )
    fc = profile_feature_coverage(big_items, CFG)
    report_feature_coverage(fc)

    # ── 判据汇总 ─────────────────────────────────────────────────────────────
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

