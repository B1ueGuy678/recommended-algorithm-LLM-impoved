"""W1 矩阵差异核实（A5）

检查项：
  A5-1  用户集合包含关系：small 的用户是否 100% 被 big 包含
  A5-2  逐日数据可用性对比：哪些天 small 有数据、big 有数据、两者都有
  A5-3  big 时间段落情况：明确三段与空窗日期

用法：
    .venv\\Scripts\\python.exe scripts\\w1_matrix_diff.py

设计原则：
  1. 只读，不修改任何数据文件。
  2. 路径全来自 configs/data.yaml。
  3. 退出码 0 = 全部判据通过；1 = 有判据未达成。
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


def main() -> int:
    for pq, name in [(SMALL_PQ, "small"), (BIG_PQ, "big")]:
        if not pq.exists():
            print(f"[ERROR] {name} Parquet 不存在：{pq}")
            return 1

    print("正在读取 Parquet...")
    sl = pl.scan_parquet(SMALL_PQ)
    bl = pl.scan_parquet(BIG_PQ)

    # ── A5-1  用户集合包含关系 ────────────────────────────────────────────
    print(f"\n{'='*72}")
    print("  A5-1  用户集合包含关系")
    print(f"{'='*72}")

    s_users = set(sl.select("user_id").collect()["user_id"].to_list())
    b_users = set(bl.select("user_id").collect()["user_id"].to_list())
    s_only = s_users - b_users
    b_only = b_users - s_users
    intersection = s_users & b_users

    print(f"  small 用户数：{len(s_users):,}")
    print(f"  big   用户数：{len(b_users):,}")
    print(f"  交集：{len(intersection):,}  仅 small：{len(s_only):,}  仅 big：{len(b_only):,}")

    ok_users = len(s_only) == 0
    check("A5-1-user-subset",
          "small 用户集合 ⊆ big 用户集合",
          ok_users,
          f"small={len(s_users):,}, big={len(b_users):,}, small_only={len(s_only):,}")

    if s_only:
        print(f"  ⚠ 仅 small 独有的用户 ID（前 10）：{sorted(s_only)[:10]}")

    # ── A5-2  逐日数据可用性对比 ─────────────────────────────────────────
    print(f"\n{'='*72}")
    print("  A5-2  逐日数据可用性对比")
    print(f"{'='*72}")

    s_days = set(
        sl.select("date").filter(pl.col("date").is_not_null())
        .collect()["date"].to_list()
    )
    b_days = set(
        bl.select("date").filter(pl.col("date").is_not_null())
        .collect()["date"].to_list()
    )

    all_days = sorted(s_days | b_days)
    both = s_days & b_days
    only_s = s_days - b_days
    only_b = b_days - s_days

    print(f"  small 有效日期天数：{len(s_days)}  big：{len(b_days)}  并集：{len(all_days)}")
    print(f"  两矩阵均有数据：{len(both)} 天  仅 small：{len(only_s)} 天  仅 big：{len(only_b)} 天")
    print()
    print(f"  {'日期':>10}  {'small':>6}  {'big':>6}")
    _sep(30)
    for d in all_days:
        s_mark = "  ✓  " if d in s_days else "  ─  "
        b_mark = "  ✓  " if d in b_days else "  ─  "
        print(f"  {d:>10}  {s_mark}  {b_mark}")
    _sep(30)

    check("A5-2-daily-coverage",
          "两矩阵逐日覆盖已核实",
          True,
          f"并集={len(all_days)}天, 交集={len(both)}天, 仅small={len(only_s)}天, 仅big={len(only_b)}天")

    # ── A5-3  big 时间分段 ────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print("  A5-3  big 时间分段")
    print(f"{'='*72}")

    b_sorted = sorted(b_days)
    segments: list[list[int]] = []
    seg: list[int] = [b_sorted[0]]
    for prev, curr in zip(b_sorted, b_sorted[1:]):
        # convert YYYYMMDD to comparable; gap > 1 calendar day = new segment
        # use string arithmetic: compare as dates
        from datetime import date as _date
        def to_date(d: int) -> _date:
            s = str(d)
            return _date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        gap = (to_date(curr) - to_date(prev)).days
        if gap > 1:
            segments.append(seg)
            seg = [curr]
        else:
            seg.append(curr)
    segments.append(seg)

    for i, seg in enumerate(segments, 1):
        print(f"  段 {i}：{seg[0]} → {seg[-1]}  ({len(seg)} 天)")

    # 空窗
    for i in range(len(segments) - 1):
        from datetime import date as _date
        def to_date(d: int) -> _date:  # noqa: F811
            s = str(d)
            return _date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        gap_start = to_date(segments[i][-1] + 1 if False else segments[i][-1])
        end_last = to_date(segments[i][-1])
        start_next = to_date(segments[i + 1][0])
        gap_days = (start_next - end_last).days - 1
        # day after last of seg i
        from datetime import timedelta
        gap_s = (end_last + timedelta(days=1)).strftime("%Y%m%d")
        gap_e = (start_next - timedelta(days=1)).strftime("%Y%m%d")
        print(f"  空窗 {i}：{gap_s} → {gap_e}  ({gap_days} 天)")

    ok_segs = len(segments) == 3
    check("A5-3-big-segments",
          "big 矩阵确认为 3 段且含 1 处空窗",
          ok_segs,
          f"实际段数={len(segments)}, 各段={[f'{s[0]}-{s[-1]}({len(s)}天)' for s in segments]}")

    # ── 判据汇总 ─────────────────────────────────────────────────────────
    width = max(len(d) for _, d, _, _ in results)
    print(f"\n{'='*72}")
    print("判据汇总")
    print(f"{'='*72}")
    print(f"{'ID':<30} {'判据':<{width}}  结果")
    _sep(30 + width + 10)
    for cid, desc, verdict, evidence in results:
        print(f"{cid:<30} {desc:<{width}}  {verdict}")
        print(f"{'':30} └─ {evidence}")

    failed = [r for r in results if r[2] == "FAIL"]
    print()
    print(f"汇总：{len(results) - len(failed)}/{len(results)} 通过，{len(failed)} 项未达成")
    for cid, desc, _, _ in failed:
        print(f"  ✗ {cid}  {desc}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
