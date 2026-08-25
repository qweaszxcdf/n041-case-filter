from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

import pandas as pd

from .utils import as_list, normalized_text


RESERVED_KEYS = {"codes"}


def _normalize_prefixes(codes) -> tuple[str, ...]:
    prefixes: list[str] = []
    for raw in as_list(codes) or []:
        code = str(raw).strip()
        if code:
            prefixes.append(code)
    return tuple(prefixes)


def _coerce_cell(value):
    """Normalize values loaded from CSV/XLS/XLSX parameter tables.

    Blank cells mean "do not assign this parameter". Common boolean strings are
    converted to real bool values so CSV and Excel behave consistently.
    """

    if pd.isna(value):
        return None

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        lowered = text.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        return text

    return value


def _load_parameter_table(path: str | Path, *, encoding: str = "utf-8-sig") -> pd.DataFrame:
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        try:
            return pd.read_csv(path, dtype=object, encoding=encoding)
        except UnicodeDecodeError:
            if encoding.lower().replace("_", "-") in {"gbk", "gb18030"}:
                raise
            return pd.read_csv(path, dtype=object, encoding="gb18030")

    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, dtype=object)

    raise ValueError("Procedure parameter files must be .csv, .xls or .xlsx")


def _table_to_rules(table: pd.DataFrame, *, source_name: str = "<DataFrame>") -> list[dict[str, object]]:
    table = table.copy()
    table.columns = [str(col).strip() for col in table.columns]

    code_columns = [col for col in table.columns if col.lower() == "code"]
    if len(code_columns) != 1:
        raise ValueError(f"{source_name}: procedure parameter table requires exactly one 'code' column")

    code_col = code_columns[0]
    parameter_columns = [col for col in table.columns if col != code_col]
    if not parameter_columns:
        raise ValueError(f"{source_name}: parameter table must contain at least one column besides 'code'")

    rules: list[dict[str, object]] = []
    for row_number, (_, row) in enumerate(table.iterrows(), start=2):
        code = _coerce_cell(row[code_col])
        if code is None:
            continue

        rule: dict[str, object] = {"codes": [str(code).strip()]}
        for column in parameter_columns:
            value = _coerce_cell(row[column])
            if value is not None:
                rule[column] = value

        if len(rule) == 1:
            raise ValueError(
                f"{source_name}: row {row_number} has code {code!r} but no parameter value"
            )
        rules.append(rule)

    return rules


def load_procedure_params(
    source,
    *,
    encoding: str = "utf-8-sig",
) -> list[dict[str, object]]:
    """Load external procedure metadata from CSV/XLS/XLSX files or DataFrames.

    File format: one procedure-code prefix per row. ``code`` is the required
    column; every other non-empty cell becomes a parameter for that code.

    Example CSV::

        code,minimally_invasive,level4,category
        36.,true,,
        36.01,,true,PCI

    Multiple sources can be supplied as a list. Sources and rows are evaluated
    in order; later matching rows override earlier values for the same parameter.
    """

    if source is None:
        return []

    if isinstance(source, pd.DataFrame):
        return _table_to_rules(source)

    if isinstance(source, (str, Path)):
        table = _load_parameter_table(source, encoding=encoding)
        return _table_to_rules(table, source_name=str(source))

    # Normalized rules are accepted internally so chained CaseFilter subsets do
    # not have to re-read files. Public usage should normally pass CSV/Excel paths.
    if isinstance(source, Iterable) and not isinstance(source, Mapping):
        items = list(source)
        if not items:
            return []

        if all(isinstance(item, Mapping) for item in items):
            return validate_procedure_params(items)

        rules: list[dict[str, object]] = []
        for item in items:
            if isinstance(item, pd.DataFrame):
                rules.extend(_table_to_rules(item))
            elif isinstance(item, (str, Path)):
                table = _load_parameter_table(item, encoding=encoding)
                rules.extend(_table_to_rules(table, source_name=str(item)))
            else:
                raise TypeError(
                    "procedure_params must be a CSV/XLS/XLSX path, DataFrame, or a list of those"
                )
        return rules

    raise TypeError("procedure_params must be a CSV/XLS/XLSX path, DataFrame, or a list of those")


def validate_procedure_params(rules) -> list[Mapping[str, object]]:
    """Validate already-normalized procedure parameter rules."""

    if rules is None:
        return []
    if isinstance(rules, Mapping):
        raise TypeError("procedure parameter rules must be a list/iterable of mappings")
    if not isinstance(rules, Iterable):
        raise TypeError("procedure parameter rules must be iterable")

    normalized: list[Mapping[str, object]] = []
    for index, rule in enumerate(rules):
        if not isinstance(rule, Mapping):
            raise TypeError(f"procedure_params[{index}] must be a mapping")
        if "codes" not in rule:
            raise ValueError(f"procedure_params[{index}] is missing required key 'codes'")
        if not _normalize_prefixes(rule["codes"]):
            raise ValueError(f"procedure_params[{index}]['codes'] must not be empty")
        if not any(key not in RESERVED_KEYS for key in rule):
            raise ValueError(f"procedure_params[{index}] must assign at least one parameter")
        normalized.append(dict(rule))
    return normalized


def resolve_procedure_params(code, rules) -> dict[str, object]:
    """Resolve all external parameters for one procedure code using startswith."""

    value = "" if code is None else str(code).strip()
    if not value:
        return {}

    result: dict[str, object] = {}
    for rule in rules or []:
        prefixes = _normalize_prefixes(rule.get("codes"))
        if prefixes and value.startswith(prefixes):
            for key, parameter_value in rule.items():
                if key not in RESERVED_KEYS:
                    result[key] = parameter_value
    return result


def _parameter_matches(actual, expected) -> bool:
    wanted = as_list(expected) or []
    for item in wanted:
        if actual == item:
            return True
        if isinstance(actual, bool) or isinstance(item, bool):
            if str(actual).strip().lower() == str(item).strip().lower():
                return True
        elif str(actual).strip() == str(item).strip():
            return True
    return False


def procedure_params_mask(
    series: pd.Series,
    rules,
    criteria: Mapping[str, object] | None,
) -> pd.Series:
    """Return a mask for external parameters resolved from each procedure code."""

    if not criteria:
        return pd.Series(True, index=series.index)

    validated = validate_procedure_params(rules)
    values = normalized_text(series)
    cache: dict[str, dict[str, object]] = {}

    def matches(code: str) -> bool:
        if code not in cache:
            cache[code] = resolve_procedure_params(code, validated)
        params = cache[code]

        for key, expected in criteria.items():
            if key not in params or not _parameter_matches(params[key], expected):
                return False
        return True

    return values.map(matches).astype(bool)
