"""数据路径的唯一入口：一切路径都从 configs/data.yaml 读，禁止在脚本里硬编码。

用法（脚本放在 scripts/ 下时可直接 import，因为 python 会把脚本所在目录
放进 sys.path）：

    from data_paths import matrix_paths, side_file
    csv_path, parquet_path = matrix_paths("small")

放在 scripts/ 而不是 src/ 的原因：现在还没有正式包（没有 pyproject.toml），
scripts/ 下的脚本互相 import 零配置即可工作；等 src/ 变成可安装的包之后，
这个模块应该整体搬过去并改成 `from recsys.data_paths import ...`。
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "data.yaml"


def load_config(path: Path | None = None) -> dict:
    """读取数据配置。缺文件时直接报错，不要静默回退到默认路径。"""
    p = path or CONFIG_PATH
    if not p.exists():
        raise FileNotFoundError(f"数据配置不存在：{p}")
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve(rel: str | Path) -> Path:
    """把配置里的相对路径解析成绝对路径（相对路径一律相对仓库根目录）。"""
    p = Path(rel)
    return p if p.is_absolute() else (ROOT / p)


def matrix_paths(name: str, cfg: dict | None = None) -> tuple[Path, Path]:
    """返回某个矩阵的 (csv 路径, parquet 路径)。"""
    cfg = cfg or load_config()
    try:
        m = cfg["matrices"][name]
    except KeyError as e:
        raise KeyError(f"configs/data.yaml 里没有 matrices.{name}") from e
    return (
        resolve(cfg["raw_dir"]) / m["csv"],
        resolve(cfg["parquet_dir"]) / m["parquet"],
    )


def convert_options(cfg: dict | None = None) -> dict:
    """CSV -> Parquet 的转换参数（压缩、row group、时间格式）。"""
    cfg = cfg or load_config()
    return dict(cfg.get("convert", {}))


def side_file(key: str, cfg: dict | None = None) -> Path:
    """辅助文件路径（A3 画像 / LLM 语义特征源）。"""
    cfg = cfg or load_config()
    try:
        return resolve(cfg["raw_dir"]) / cfg["side_files"][key]
    except KeyError as e:
        raise KeyError(f"configs/data.yaml 里没有 side_files.{key}") from e
