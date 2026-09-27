"""W1 异常与重复扫描（A4）

检查项：
  A4-1  完全重复行（所有列相同）
  A4-2  重复 (user_id, video_id) 对（同一用户对同一视频的多条记录）
  A4-3  play_duration > video_duration（播放时长超过视频时长）
  A4-4  video_duration = 0（视频时长为零，watch_ratio 意义丧失）
  A4-5  时间戳越界：timestamp 对应的 UTC+8 日期不在 date 字段声明的范围内

用法：
    .venv\\Scripts\\python.exe scripts\\w1_data_anomaly.py

设计原则：
  1. 只读，不修改任何数据文件。
  2. 路径全来自 configs/data.yaml，不硬编码数据集目录名。
  3. 每个异常数字都能在输出里追溯。
  4. 退出码 0 = 全部判据通过（不代表数据完美，而是所有可量化项均已测量）；
     1 = 有判据未达成。
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from data_paths import load_config, matrix_paths

CFG = load_config()
SMALL_CSV, SMALL_PQ = matrix_paths("small", CFG)
BIG_CSV, BIG_PQ = matrix_paths("big", CFG)

results: list[tuple[str, str, str, str]] = []


def check(cid: str, desc: str, ok: bool, evidence: str) -> None:
    results.append((cid, desc, "PASS" if ok else "FAIL", evidence))


def _sep(width: int = 72) -> None:
    print("─" * width)


# ---------------------------------------------------------------------------
# 逐矩阵扫描
# ---------------------------------------------------------------------------

def scan_anomalies(name: str, pq: Path) -> None:
    print(f"\n{'='*72}")
    print(f"  {name.upper()} 矩阵异常扫描")
    print(f"{'='*72}")

    df = pl.read_parquet(pq)
    total = len(df)
    print(f"  总行数：{total:,}")

    # ── A4-1  完全重复行 ──────────────────────────────────────────────────
    dup_rows = total - df.unique().height
    pct_dup_rows = round(dup_rows / total * 100, 4)
    print(f"\n  [A4-1] 完全重复行（所有列相同）")
    print(f"         重复行数：{dup_rows:,}  ({pct_dup_rows:.4f}%)")
    check(f"A4-1-dup-rows:{name}",
          f"{name}: 完全重复行已计量",
          True,
          f"{dup_rows:,} 行 ({pct_dup_rows:.4f}%)")

    # ── A4-2  重复 (user_id, video_id) 对 ────────────────────────────────
    pair_counts = (
        df.group_by(["user_id", "video_id"])
        .agg(pl.len().alias("cnt"))
    )
    dup_pairs = int((pair_counts["cnt"] > 1).sum())
    dup_pair_rows = int(pair_counts.filter(pl.col("cnt") > 1)["cnt"].sum())
    pct_dup_pairs = round(dup_pairs / total * 100, 4) if total else 0.0
    # 最大重复次数
    max_dup = int(pair_counts["cnt"].max())
    print(f"\n  [A4-2] 重复 (user_id, video_id) 对")
    print(f"         有重复的 pair 数：{dup_pairs:,}，涉及行数：{dup_pair_rows:,}  ({pct_dup_pairs:.4f}%)")
    print(f"         单 pair 最大重复次数：{max_dup}")
    check(f"A4-2-dup-pairs:{name}",
          f"{name}: 重复 (user,video) pair 已计量",
          True,
          f"dup pairs={dup_pairs:,}, dup rows={dup_pair_rows:,} ({pct_dup_pairs:.4f}%), max={max_dup}")

    # ── A4-3  play_duration > video_duration ─────────────────────────────
    # 仅对两列均非空且 video_duration > 0 的行判断
    mask_valid = (
        pl.col("play_duration").is_not_null()
        & pl.col("video_duration").is_not_null()
        & (pl.col("video_duration") > 0)
    )
    eligible_pd = int(df.filter(mask_valid).height)
    over_dur = int(
        df.filter(mask_valid & (pl.col("play_duration") > pl.col("video_duration"))).height
    )
    pct_over = round(over_dur / eligible_pd * 100, 4) if eligible_pd else 0.0
    print(f"\n  [A4-3] play_duration > video_duration")
    print(f"         参与校验行（两列非空且 video_duration>0）：{eligible_pd:,}")
    print(f"         play_duration > video_duration：{over_dur:,}  ({pct_over:.4f}%)")
    # 不判 FAIL，只要计量完成就 PASS；异常数量供用户参考
    check(f"A4-3-over-dur:{name}",
          f"{name}: play>video_duration 异常已计量",
          True,
          f"eligible={eligible_pd:,}, over={over_dur:,} ({pct_over:.4f}%)")

    # ── A4-4  video_duration = 0 ──────────────────────────────────────────
    vd_zero = int(df.filter(pl.col("video_duration") == 0).height)
    vd_null = int(df["video_duration"].null_count())
    pct_vd_zero = round(vd_zero / total * 100, 4)
    print(f"\n  [A4-4] video_duration = 0")
    print(f"         video_duration = 0：{vd_zero:,}  ({pct_vd_zero:.4f}%)  null：{vd_null:,}")
    check(f"A4-4-vd-zero:{name}",
          f"{name}: video_duration=0 已计量",
          True,
          f"zero={vd_zero:,} ({pct_vd_zero:.4f}%), null={vd_null:,}")

    # ── A4-5  时间戳越界 ──────────────────────────────────────────────────
    # 只对 timestamp 和 date 都非空的行检验
    # timestamp 单位：秒（UTC）; date 是 UTC+8 的日期
    # UTC+8 日期 = (timestamp + 28800) 换算出来的日期
    ts_valid = df.filter(
        pl.col("timestamp").is_not_null() & pl.col("date").is_not_null()
    )
    eligible_ts = len(ts_valid)

    if eligible_ts > 0:
        # timestamp is Float64 seconds (UTC); date is Int64 YYYYMMDD (UTC+8)
        # UTC+8 = timestamp + 28800s; reconstruct as YYYYMMDD integer to compare
        ts_date = (
            ts_valid
            .with_columns(
                pl.from_epoch(
                    (pl.col("timestamp") + 28800).cast(pl.Int64), time_unit="s"
                ).alias("ts_dt_utc8")
            )
            .with_columns(
                (
                    pl.col("ts_dt_utc8").dt.year().cast(pl.Int64) * 10000
                    + pl.col("ts_dt_utc8").dt.month().cast(pl.Int64) * 100
                    + pl.col("ts_dt_utc8").dt.day().cast(pl.Int64)
                ).alias("ts_date_int")
            )
        )
        mismatch_ts = int(
            ts_date.filter(pl.col("ts_date_int") != pl.col("date")).height
        )
    else:
        mismatch_ts = 0

    pct_ts = round(mismatch_ts / eligible_ts * 100, 4) if eligible_ts else 0.0
    print(f"\n  [A4-5] 时间戳越界（timestamp UTC+8 日期 ≠ date）")
    print(f"         参与校验行：{eligible_ts:,}  不一致行：{mismatch_ts:,}  ({pct_ts:.4f}%)")
    # 不一致 = 0 才算无越界异常
    ok_ts = mismatch_ts == 0
    check(f"A4-5-ts-bounds:{name}",
          f"{name}: 时间戳 UTC+8 日期与 date 一致",
          ok_ts,
          f"eligible={eligible_ts:,}, mismatch={mismatch_ts:,} ({pct_ts:.4f}%)")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    for pq, name in [(SMALL_PQ, "small"), (BIG_PQ, "big")]:
        if not pq.exists():
            print(f"[ERROR] {name} Parquet 不存在：{pq}")
            print("请先运行转换脚本生成 Parquet，再跑本扫描脚本。")
            return 1

    scan_anomalies("small", SMALL_PQ)
    scan_anomalies("big", BIG_PQ)

    # ── 判据汇总 ─────────────────────────────────────────────────────────
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
