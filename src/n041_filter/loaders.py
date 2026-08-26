from __future__ import annotations

from pathlib import Path
import pandas as pd


def load_table(
    path: str | Path,
    *,
    encoding: str = "gbk",
    errors: str = "strict",
) -> pd.DataFrame:
    """Load CSV/XLSX/XLS/DBF while preserving text fields and empty cells.

    For DBF inputs, ``errors`` is passed to the character decoder and defaults
    to strict decoding.
    """

    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        return pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            encoding=encoding,
        )
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(
            path,
            dtype=str,
            keep_default_na=False,
        )
    if suffix == ".dbf":
        try:
            from dbfread import DBF
        except ImportError as exc:
            raise RuntimeError(
                "DBF support requires the optional dependency: pip install 'n041-case-filter[dbf]'"
            ) from exc
        table = DBF(str(path), encoding=encoding, char_decode_errors=errors)
        return pd.DataFrame(iter(table))

    raise ValueError(f"Unsupported input format: {suffix}")
