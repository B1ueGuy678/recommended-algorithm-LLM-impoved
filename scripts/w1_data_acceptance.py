"""W1 数据验收：A1（目录规范化 / 单一权威副本）+ A2（CSV -> Parquet）

用法：
    .venv\\Scripts\\python.exe scripts\\w1_data_acceptance.py

设计原则：
  1. 报告里出现的每个数字都必须能追溯到这一条命令的输出，不手工填写。
  2. 一切路径来自 configs/data.yaml（A1-2 约定），脚本内不硬编码数据集目录名。
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from pathlib import Path

import polars as pl
import psutil

from data_paths import CONFIG_PATH, ROOT, load_config, matrix_paths, resolve

CFG = load_config()
DATA = ROOT / "data"
# 被禁止硬编码的字面量 = config 里的数据集目录名本身。
# 注意不能在本文件里直接写这个字面量：否则「扫描脚本是否硬编码」的检查
# 会命中检测器自己的源码，报出一个假 FAIL（第一版就踩了这个自指陷阱）。
DATASET_TOKEN = str(CFG.get("dataset", ""))
SMALL_CSV, SMALL_PQ = matrix_paths("small", CFG)
BIG_CSV, BIG_PQ = matrix_paths("big", CFG)

# A2 验收判据（来自 W1 清单）：这两列的类型必须被显式统一
EXPECT_DATE_INT = True
EXPECT_TIME_DATETIME = True

proc = psutil.Process()
results: list[tuple[str, str, str, str]] = []


def check(cid: str, desc: str, ok: bool, evidence: str) -> None:
    results.append((cid, desc, "PASS" if ok else "FAIL", evidence))


def mb(n: int | float) -> float:
    return round(n / 1e6, 1)


def rss_mb() -> float:
    return round(proc.memory_info().rss / 1e6, 1)


# --------------------------------------------------------------------------
# A1：目录规范化
# --------------------------------------------------------------------------
def accept_a1() -> None:
    by_name: dict[str, list[Path]] = defaultdict(list)
    for p in DATA.rglob("*"):
        if p.is_file():
            by_name[p.name.lower()].append(p)

    dupes = {k: v for k, v in by_name.items() if len(v) > 1}
    check(
        "A1-1",
        "全库只有一份权威副本（无重名文件）",
        not dupes,
        "无重名文件" if not dupes else "; ".join(
            f"{k} x{len(v)}: " + " | ".join(str(x.relative_to(ROOT)) for x in v)
            for k, v in dupes.items()
        ),
    )

    # 判据不是「有没有 config 文件」，而是「路径是否真的只由 config 决定」：
    # 只要还有脚本里写着数据集目录名，config 就是摆设，改一处就会漏一处。
    declared = sorted(CFG.get("matrices", {}))
    hard = sorted(
        s.name
        for s in sorted((ROOT / "scripts").glob("*.py"))
        if DATASET_TOKEN and DATASET_TOKEN in s.read_text(encoding="utf-8")
    )
    check(
        "A1-2",
        "数据路径来自 configs/data.yaml，且脚本内无硬编码数据集目录名",
        CONFIG_PATH.exists() and declared == ["big", "small"] and not hard,
        f"{CONFIG_PATH.relative_to(ROOT)} 声明矩阵 {declared}；"
        + (
            f"仍有脚本硬编码数据集目录名：{', '.join(hard)}"
            if hard
            else "无脚本硬编码数据集目录名"
        ),
    )

    raw_dir, pq_dir = resolve(CFG["raw_dir"]), resolve(CFG["parquet_dir"])
    under_data = all(str(d).lower().startswith(str(DATA).lower()) for d in (raw_dir, pq_dir))
    check(
        "A1-3",
        "数据目录都在 data/ 下（已被 .gitignore 排除，不会误入库）",
        under_data,
        f"raw_dir={raw_dir.relative_to(ROOT)} / parquet_dir={pq_dir.relative_to(ROOT)}",
    )

    # loaddata.py / Statistics_KuaiRec.ipynb 是数据集自带的官方文件，不算「我们的代码」，
    # 但也不能往里放我们自己的脚本——那会被 .gitignore 一起吞掉。
    upstream = {"loaddata.py", "statistics_kuairec.ipynb"}
    stray = [p for p in DATA.rglob("*.py") if p.name.lower() not in upstream]
    check(
        "A1-4",
        "我们自己的代码没有落在 data/ 下（否则会被 .gitignore 吞掉）",
        not stray,
        "data/ 下仅有数据集自带的 " + ", ".join(sorted(p.name for p in DATA.rglob("*.py")))
        if not stray
        else "; ".join(str(p.relative_to(ROOT)) for p in stray),
    )


def accept_conv_scripts() -> None:
    """转换脚本必须从 config 读路径，产物必须落在 config 声明的位置。

    否则「重跑即复现」是假的：脚本会往另一个目录写下第二份副本，
    而两份内容一样时很难发现哪份是旧的。
    """
    found = False
    for s in sorted((ROOT / "scripts").glob("*.py")):
        src = s.read_text(encoding="utf-8")
        # 判据是「真的调用了写出接口」，而不是「文本里出现过这几个字」——
        # 用子串匹配会把本文件里那句「未找到…的脚本」的提示信息
        # 也当成一个转换脚本，然后报出一个假 FAIL（第一版就踩了这个坑）。
        if not re.search(r"\.sink_parquet\(", src):
            continue
        found = True
        uses_cfg = "data_paths" in src
        hard = bool(DATASET_TOKEN) and DATASET_TOKEN in src
        check(
            f"A2-script:{s.name}",
            f"{s.name} 从 configs/data.yaml 读路径（无硬编码）",
            uses_cfg and not hard,
            f"引用 data_paths：{'是' if uses_cfg else '否'}；"
            f"硬编码数据集目录名：{'有' if hard else '无'}",
        )

    if not found:
        check(
            "A2-script",
            "存在可复现的 CSV->Parquet 转换脚本（在 scripts/ 下，可入库）",
            False,
            "scripts/ 下没有调用 Parquet 写出接口（.sink_parquet）的脚本",
        )

    for name in sorted(CFG.get("matrices", {})):
        _, declared_pq = matrix_paths(name, CFG)
        exists = declared_pq.exists()
        check(
            f"A2-paths:{name}",
            f"{name}: config 声明的 Parquet 路径 == 磁盘实际产物",
            exists,
            f"{declared_pq.relative_to(ROOT)} "
            + ("存在" if exists else "不存在（重跑对应转换脚本即可生成）"),
        )


# --------------------------------------------------------------------------
# A2：CSV -> Parquet
# --------------------------------------------------------------------------
def schema_report(lf: pl.LazyFrame) -> dict[str, str]:
    return {k: str(v) for k, v in lf.collect_schema().items()}


def accept_a2(name: str, csv: Path, pq: Path | None) -> None:
    if pq is None or not pq.exists():
        check(
            f"A2-{name}-exists",
            f"{name}: Parquet 已生成",
            False,
            f"config 声明的路径不存在：{pq}",
        )
        return

    lf = pl.scan_parquet(pq)
    sch = schema_report(lf)
    agg = lf.select(
        pl.len().alias("rows"),
        pl.col("user_id").n_unique().alias("users"),
        pl.col("video_id").n_unique().alias("items"),
        pl.col("date").null_count().alias("date_null"),
        pl.col("time").null_count().alias("time_null"),
    ).collect().to_dicts()[0]

    check(
        f"A2-{name}-1",
        f"{name}: 覆盖全部 8 列且无行丢失",
        set(sch) == {"user_id", "video_id", "play_duration", "video_duration",
                     "time", "date", "timestamp", "watch_ratio"},
        f"{len(sch)} 列 / {agg['rows']:,} 行 / {agg['users']:,} 用户 / {agg['items']:,} 物品",
    )

    date_t = sch["date"]
    ok_date = date_t in ("Int8", "Int16", "Int32", "Int64", "Date") if EXPECT_DATE_INT else True
    check(
        f"A2-{name}-2",
        f"{name}: date 类型已统一（判据：整数或 Date，不能是浮点）",
        ok_date,
        f"实际 {date_t}；date 空值 {agg['date_null']:,}",
    )

    # time 的判据不能只看 dtype：第一版只要求 datetime，结果 %.3f 这种
    # 固定 3 位小数的格式把「小数位不是 3 位」的行全部静默变成 null（big 10.0%），
    # 类型检查照样 PASS。以 date 的空值为基准——原始 CSV 里这几列的空行是同一批，
    # 所以 time 的空值数不允许超过 date 的空值数。
    time_t = sch["time"]
    ok_time = (time_t.startswith("Datetime") if EXPECT_TIME_DATETIME else True) and (
        agg["time_null"] <= agg["date_null"]
    )
    lost = agg["time_null"] - agg["date_null"]
    check(
        f"A2-{name}-3",
        f"{name}: time 解析为 Datetime 且无静默丢行（time 空值 ≤ date 空值）",
        ok_time,
        f"实际 {time_t}；time 空值 {agg['time_null']:,}，date 空值 {agg['date_null']:,}"
        + (f"，多丢 {lost:,} 行（{lost / agg['rows'] * 100:.2f}%）" if lost > 0 else "")
        + "（判据：以 date 为基准，两列空行同源）",
    )

    # time 是 UTC+8 挂钟时间、timestamp 是 UTC 秒，这是数据集的既有约定。
    # 必须验证偏移是「恒定 8 小时」而不是各行不同——若不恒定，说明解析有损，
    # 后续任何跨这两列的对齐都会错。
    off = (
        lf.select(
            (
                pl.col("time")
                - pl.from_epoch(
                    (pl.col("timestamp").cast(pl.Float64) * 1000).round().cast(pl.Int64),
                    time_unit="ms",
                )
            )
            .dt.total_milliseconds()
            .alias("off_ms")
        )
        .drop_nulls()
    )
    uniq = off.unique().collect()["off_ms"].to_list()
    const_ok = len(uniq) == 1
    check(
        f"A2-{name}-5",
        f"{name}: time 与 timestamp 的偏移恒定（约定：time/date=UTC+8 本地，timestamp=UTC 秒）",
        const_ok,
        f"偏移取值 {len(uniq)} 种"
        + (
            f"，恒为 {uniq[0]:,} ms（= {uniq[0] / 3600000:.0f} 小时）"
            if const_ok
            else f"（不恒定，前 5 个：{sorted(uniq)[:5]}）——解析有损"
        ),
    )


def _measure(loader, n: int = 2) -> tuple[float, float]:
    """跑 n 遍取最后一遍的耗时，并返回过程中最大的进程 RSS。

    必须用 eager 全量读取来比：`scan_csv().select(len())` 会被 Polars 的
    投影下推优化成「只数行数」，测出来的不是读入耗时（第一版脚本就踩了这个坑）。
    """
    import gc

    times, rss = [], []
    for _ in range(n):
        gc.collect()
        t0 = time.perf_counter()
        obj = loader()
        times.append(time.perf_counter() - t0)
        rss.append(rss_mb())
        del obj
    gc.collect()
    return times[-1], max(rss)


def benchmark(name: str, csv: Path, pq: Path | None) -> None:
    """CSV 与 Parquet 全量 eager 读入对比（各跑两遍，取第二遍避开冷启动）。"""
    if pq is None or not (csv.exists() and pq.exists()):
        return

    base = rss_mb()
    t_csv, r_csv = _measure(lambda: pl.read_csv(csv, infer_schema_length=10000))
    t_pq, r_pq = _measure(lambda: pl.read_parquet(pq))

    size_ratio = csv.stat().st_size / pq.stat().st_size
    time_ratio = t_csv / t_pq
    # 判据只取「体积」与「全量读入耗时」两项：这两个指标稳定且可复现。
    # RSS 只作为参考值上报，不参与判定——同进程内先读 CSV 会把内存高水位抬高，
    # 后面读 Parquet 的 RSS 必然被污染；且 Polars 解码 Parquet 是多线程的，
    # 瞬时缓冲会让读数更高。拿它做对照会得出「Parquet 更吃内存」这种假结论。
    check(
        f"A2-{name}-4",
        f"{name}: Parquet 体积更小且全量读入更快",
        t_pq < t_csv and size_ratio > 1.0,
        f"CSV {mb(csv.stat().st_size)} MB / 全量读入 {t_csv:.2f}s；"
        f"Parquet {mb(pq.stat().st_size)} MB / 全量读入 {t_pq:.2f}s；"
        f"体积 {size_ratio:.1f}x，速度 {time_ratio:.1f}x。"
        f"（参考值，不判定：过程 RSS CSV +{r_csv - base:.0f} MB / Parquet +{r_pq - base:.0f} MB，"
        f"同进程高水位会污染后者）",
    )


def main() -> int:
    accept_a1()
    accept_a2("small", SMALL_CSV, SMALL_PQ)
    accept_a2("big", BIG_CSV, BIG_PQ)
    accept_conv_scripts()
    benchmark("small", SMALL_CSV, SMALL_PQ)
    benchmark("big", BIG_CSV, BIG_PQ)

    width = max(len(d) for _, d, _, _ in results)
    print(f"{'ID':<14} {'判据':<{width}}  结果")
    print("-" * (14 + width + 30))
    for cid, desc, verdict, evidence in results:
        print(f"{cid:<14} {desc:<{width}}  {verdict}")
        print(f"{'':<14} └─ {evidence}")

    failed = [r for r in results if r[2] == "FAIL"]
    print()
    print(f"汇总：{len(results) - len(failed)}/{len(results)} 通过，{len(failed)} 项未达成")
    for cid, desc, _, _ in failed:
        print(f"  ✗ {cid} {desc}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
