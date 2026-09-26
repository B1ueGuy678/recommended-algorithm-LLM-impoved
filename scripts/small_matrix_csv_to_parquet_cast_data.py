"""small_matrix.csv -> Parquet（date -> Int64，time -> Datetime）

路径、压缩参数、时间格式全部来自 configs/data.yaml，脚本内不硬编码。
用法（在仓库根目录）：
    .venv\\Scripts\\python.exe scripts\\small_matrix_csv_to_parquet_cast_data.py
"""

import polars as pl

from data_paths import convert_options, matrix_paths

# ===================== 配置来自 configs/data.yaml =====================
CSV_PATH, PARQUET_OUT = matrix_paths("small")
OPT = convert_options()
# ======================================================================
PARQUET_OUT.parent.mkdir(parents=True, exist_ok=True)

if not CSV_PATH.exists():
    raise FileNotFoundError(f"原始CSV不存在：{CSV_PATH}\n请检查 configs/data.yaml 的 raw_dir 与 matrices.small.csv")

print(f"✅ 成功定位原始CSV：{CSV_PATH}")

# 流式懒加载读取CSV
lf = pl.scan_csv(CSV_PATH, low_memory=True)

# 类型转换：date列 float64 -> Int64；time列 String -> Datetime
# 【坑】time 的小数秒位数不固定（1位/2位/3位），格式串必须用 %.f 而不是 %.3f：
# %.3f 只认恰好3位，配合 strict=False 会把其余行【静默】变成 null ——
# 实测 4,676,570 行里 time 空值从 181,992 涨到 629,783（多丢 447,791 行）。
# 格式串定义在 configs/data.yaml 的 convert.time_format，改错了会静默丢行。
lf = lf.with_columns(
    pl.col("date").cast(pl.Int64),
    pl.col("time").str.to_datetime(format=OPT["time_format"], strict=False),
)

# 流式写入parquet
lf.sink_parquet(
    PARQUET_OUT,
    compression=OPT["compression"],
    row_group_size=OPT["row_group_size"],
    maintain_order=False,
)

print(f"\n✅ 数据集转换完成！date转为Int64，time转为Datetime")
print(f"输出Parquet文件：{PARQUET_OUT}")
print("\n=== 输出Schema信息 ===")
print(lf.collect_schema())
