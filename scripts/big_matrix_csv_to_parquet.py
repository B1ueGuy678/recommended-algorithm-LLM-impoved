"""big_matrix.csv -> Parquet（time -> Datetime）

路径、压缩参数、时间格式全部来自 configs/data.yaml，脚本内不硬编码。
用法（在仓库根目录）：
    .venv\\Scripts\\python.exe scripts\\big_matrix_csv_to_parquet.py
"""

import polars as pl

from data_paths import convert_options, matrix_paths

# ===================== 配置来自 configs/data.yaml =====================
CSV_PATH, PARQUET_OUT = matrix_paths("big")
OPT = convert_options()
# ======================================================================
PARQUET_OUT.parent.mkdir(parents=True, exist_ok=True)

if not CSV_PATH.exists():
    raise FileNotFoundError(f"原始CSV不存在：{CSV_PATH}\n请检查 configs/data.yaml 的 raw_dir 与 matrices.big.csv")

print(f"✅ 成功定位原始CSV：{CSV_PATH}")

# 流式懒加载读取CSV
lf = pl.scan_csv(CSV_PATH, low_memory=True)

# 仅转换：time列 String -> Datetime
# 【坑】原始CSV的小数秒位数不固定，有 1 位/2 位/3 位三种：
#   2020-07-05 00:08:23.438 (3位) / 01:00:25.5 (1位) / 03:28:02.32 (2位)
# 必须用 %.f（接受任意位数小数秒）。用 %.3f 只认恰好3位，配合 strict=False
# 会把其余行【静默】变成 null —— 实测 12,530,806 行里丢掉 1,252,706 行(10.00%)，
# 且不报任何错。判定依据：time 空值必须等于 date 空值（本数据集 date 空值为 0）。
# 格式串定义在 configs/data.yaml 的 convert.time_format。
lf = lf.with_columns(
    pl.col("time").str.to_datetime(format=OPT["time_format"], strict=False)
)

# 流式写入parquet
lf.sink_parquet(
    PARQUET_OUT,
    compression=OPT["compression"],
    row_group_size=OPT["row_group_size"],
    maintain_order=False,
)

print(f"\n✅ 12M数据集转换完成！time列转为Datetime")
print(f"输出Parquet文件：{PARQUET_OUT}")
print("\n=== 输出Schema信息 ===")
print(lf.collect_schema())
