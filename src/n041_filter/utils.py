from __future__ import annotations

from collections.abc import Iterable
import pandas as pd
import re


def as_list(value):
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return list(value)
    return [value]


def normalized_text(series: pd.Series, *, upper: bool = False) -> pd.Series:
    out = series.fillna("").astype(str).str.strip()
    if upper:
        out = out.str.upper()
    return out


def match_codes(series: pd.Series, codes, *, upper: bool = True) -> pd.Series:
    """Match codes using startswith semantics.

    Every supplied code is treated as a prefix. This naturally allows broad
    category codes and more specific codes to be mixed in one call, e.g.
    ["I21", "I22.1", "C34.11"].
    """

    values = normalized_text(series, upper=upper)
    wanted: list[str] = []

    for raw in as_list(codes) or []:
        code = str(raw).strip()
        if upper:
            code = code.upper()
        if code:
            wanted.append(code)

    if not wanted:
        return pd.Series(False, index=series.index)

    return values.str.startswith(tuple(wanted), na=False)


def normalize_value(value):
    if value is None:
        return ""

    missing = pd.isna(value)
    try:
        if bool(missing):
            return ""
    except (TypeError, ValueError):
        # Non-scalar values are not expected in a normal cell, but retain the
        # existing string-normalization behavior if one is supplied.
        pass

    text = str(value).strip()

    # 4.0 / 4.00 -> 4
    if re.fullmatch(r"-?\d+\.0+", text):
        return text.split(".", 1)[0]

    return text


def match_values(series, values, *, case_insensitive: bool = False):
    wanted = {
        normalize_value(v)
        for v in (as_list(values) or [])
    }

    actual = series.map(normalize_value)
    if case_insensitive:
        wanted = {value.upper() for value in wanted}
        actual = actual.str.upper()

    return actual.isin(wanted)


def contains_values(series: pd.Series, values, *, case: bool = False) -> pd.Series:
    """Match rows whose text contains any supplied value."""

    wanted = [
        str(value).strip()
        for value in (as_list(values) or [])
        if value is not None and str(value).strip()
    ]
    if not wanted:
        return pd.Series(False, index=series.index)

    actual = normalized_text(series)
    result = pd.Series(False, index=series.index)
    for value in wanted:
        result |= actual.str.contains(value, case=case, regex=False, na=False)
    return result


def numeric_between(series: pd.Series, *, start=None, end=None) -> pd.Series:
    """Match numeric values in an inclusive range.

    Thousands separators are accepted in source values, which is common in
    exported fee columns such as ``ZFY``.
    """

    numbers = _numeric_series(series)
    mask = numbers.notna()

    def bound(value):
        if value is None:
            return None
        parsed = pd.to_numeric(str(value).replace(",", ""), errors="coerce")
        if pd.isna(parsed):
            raise ValueError(f"Numeric range bound must be numeric: {value!r}")
        return parsed

    lower = bound(start)
    upper = bound(end)
    if lower is not None:
        mask &= numbers >= lower
    if upper is not None:
        mask &= numbers <= upper
    return mask


def _numeric_series(series: pd.Series) -> pd.Series:
    actual = normalized_text(series).str.replace(",", "", regex=False)
    return pd.to_numeric(actual, errors="coerce")


def present_mask(series: pd.Series) -> pd.Series:
    return normalized_text(series).ne("")
