from __future__ import annotations

from datetime import date, datetime
from numbers import Integral
import re

import numpy as np
import pandas as pd

from .procedure_params import procedure_params_mask
from .utils import (
    as_list,
    contains_values,
    match_codes,
    match_values,
    normalized_text,
    numeric_between,
    present_mask,
)


def diagnosis_mask(
    df: pd.DataFrame,
    slots: list[dict[str, object]],
    *,
    codes,
    principal: bool | None = None,
    name=None,
    name_contains=None,
    admission_condition=None,
    discharge_condition=None,
) -> pd.Series:
    """Return case-level mask for diagnosis criteria.

    The condition fields are evaluated on the SAME diagnosis slot as the code.
    """

    result = pd.Series(False, index=df.index)

    for slot in slots:
        if principal is not None and bool(slot.get("principal")) != principal:
            continue

        code_col = slot.get("code")
        if not code_col:
            continue
        
        code_series = df[str(code_col)]
        if codes is None:
            mask = normalized_text(code_series).ne("")
        else:
            mask = match_codes(code_series, codes, upper=False)

        if name is not None:
            col = slot.get("name")
            if not col:
                mask &= False
            else:
                mask &= match_values(df[str(col)], name)

        if name_contains is not None:
            col = slot.get("name")
            if not col:
                mask &= False
            else:
                mask &= contains_values(df[str(col)], name_contains)

        if admission_condition is not None:
            col = slot.get("admission_condition")
            if not col:
                mask &= False
            else:
                mask &= match_values(df[str(col)], admission_condition)

        if discharge_condition is not None:
            col = slot.get("discharge_condition")
            if not col:
                mask &= False
            else:
                mask &= match_values(df[str(col)], discharge_condition)

        result |= mask

    return result


def procedure_mask(
    df: pd.DataFrame,
    slots: list[dict[str, object]],
    *,
    codes=None,
    principal: bool | None = None,
    name=None,
    name_contains=None,
    level=None,
    incision_healing=None,
    unplanned=None,
    day_surgery=None,
    operation_type=None,
    date_start=None,
    date_end=None,
    date_diff_hours=None,
    procedure_params=None,
    params=None,
) -> pd.Series:
    """Return case-level mask for procedure criteria.

    External ``procedure_params`` are evaluated on the SAME procedure slot as
    the code and raw slot attributes, so metadata from another procedure in the
    same case can never satisfy the filter accidentally.
    """

    diff_bounds = _date_diff_hours_bounds(date_diff_hours)
    candidates: list[tuple[dict[str, object], pd.Series, pd.Series | None]] = []

    for slot in slots:
        if principal is not None and bool(slot.get("principal")) != principal:
            continue

        code_col = slot.get("code")
        if not code_col:
            continue

        code_series = df[str(code_col)]
        if codes is None:
            mask = normalized_text(code_series).ne("")
        else:
            mask = match_codes(code_series, codes, upper=False)

        if name is not None:
            col = slot.get("name")
            if not col:
                mask &= False
            else:
                mask &= match_values(df[str(col)], name)

        if name_contains is not None:
            col = slot.get("name")
            if not col:
                mask &= False
            else:
                mask &= contains_values(df[str(col)], name_contains)

        if level is not None:
            col = slot.get("level")
            if not col:
                mask &= False
            else:
                mask &= match_values(df[str(col)], level)

        if incision_healing is not None:
            col = slot.get("incision_healing")
            if not col:
                mask &= False
            elif incision_healing is any:
                mask &= present_mask(df[str(col)])
            else:
                mask &= match_values(df[str(col)], incision_healing)

        for attribute, values in (
            ("unplanned", unplanned),
            ("day_surgery", day_surgery),
            ("operation_type", operation_type),
        ):
            if values is None:
                continue
            col = slot.get(attribute)
            if not col:
                mask &= False
            elif values is any:
                mask &= present_mask(df[str(col)])
            else:
                mask &= match_values(df[str(col)], values, case_insensitive=True)

        if date_start is not None or date_end is not None:
            col = slot.get("date")
            if not col:
                mask &= False
            else:
                mask &= date_between_mask(
                    df,
                    str(col),
                    start=date_start,
                    end=date_end,
                )

        if params:
            mask &= procedure_params_mask(code_series, procedure_params, params)

        date_values = None
        if diff_bounds is not None and slot.get("date"):
            date_values = pd.to_datetime(
                df[str(slot["date"])],
                format="mixed",
                errors="coerce",
            )
        candidates.append((slot, mask, date_values))

    if diff_bounds is None:
        result = pd.Series(False, index=df.index)
        for _, mask, _ in candidates:
            result |= mask
        return result

    lower, upper = diff_bounds
    return _adjacent_date_diff_mask(
        candidates,
        lower=pd.Timedelta(hours=lower),
        upper=pd.Timedelta(hours=upper),
        index=df.index,
    )


def _adjacent_date_diff_mask(
    candidates: list[tuple[dict[str, object], pd.Series, pd.Series | None]],
    *,
    lower: pd.Timedelta,
    upper: pd.Timedelta,
    index: pd.Index,
) -> pd.Series:
    """Match cases with an in-range gap between adjacent qualifying dates."""

    date_columns = [
        date_values.where(mask)
        for _, mask, date_values in candidates
        if date_values is not None
    ]
    if len(date_columns) < 2:
        return pd.Series(False, index=index)

    values = pd.concat(date_columns, axis=1).to_numpy(dtype="datetime64[ns]")
    valid = ~pd.isna(values)
    sentinel = np.iinfo(np.int64).max
    numeric = values.astype("int64", copy=True)
    numeric[~valid] = sentinel
    numeric.sort(axis=1)

    sorted_valid = numeric != sentinel
    adjacent = sorted_valid[:, 1:] & sorted_valid[:, :-1]
    differences = np.zeros_like(numeric[:, 1:])
    differences[adjacent] = numeric[:, 1:][adjacent] - numeric[:, :-1][adjacent]

    lower_ns = lower.value
    upper_ns = upper.value
    matched = adjacent & (differences >= lower_ns) & (differences <= upper_ns)
    return pd.Series(matched.any(axis=1), index=index)


def _date_diff_hours_bounds(date_diff_hours) -> tuple[int, int] | None:
    """Normalize an upper hour bound or inclusive ``(start, end)`` range."""

    if date_diff_hours is None:
        return None

    if isinstance(date_diff_hours, Integral) and not isinstance(date_diff_hours, bool):
        value = int(date_diff_hours)
        if value < 0:
            raise ValueError("date_diff_hours cannot be negative")
        return 0, value

    if isinstance(date_diff_hours, (tuple, list)) and len(date_diff_hours) == 2:
        start, end = date_diff_hours
        if (
            isinstance(start, Integral)
            and not isinstance(start, bool)
            and isinstance(end, Integral)
            and not isinstance(end, bool)
        ):
            start, end = int(start), int(end)
            if start < 0 or end < 0 or start > end:
                raise ValueError(
                    "date_diff_hours must be a non-negative upper bound or an ordered range"
                )
            return start, end

    raise TypeError("date_diff_hours must be an integer upper bound or a (start, end) range")


def date_between_mask(df: pd.DataFrame, column: str, *, start=None, end=None) -> pd.Series:
    values = pd.to_datetime(df[column], format="mixed", errors="coerce")
    mask = pd.Series(True, index=df.index)
    if start is not None:
        mask &= values >= pd.Timestamp(start)
    if end is not None:
        end_value = pd.Timestamp(end)
        if _is_date_only(end):
            mask &= values < end_value + pd.Timedelta(days=1)
        else:
            mask &= values <= end_value
    return mask


def _is_date_only(value) -> bool:
    if isinstance(value, date) and not isinstance(value, datetime):
        return True
    return isinstance(value, str) and bool(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip())
    )


def value_mask(df: pd.DataFrame, column: str, values) -> pd.Series:
    return match_values(df[column], as_list(values))


def contains_mask(df: pd.DataFrame, column: str, values) -> pd.Series:
    return contains_values(df[column], values)


def numeric_between_mask(
    df: pd.DataFrame,
    column: str,
    *,
    start=None,
    end=None,
) -> pd.Series:
    return numeric_between(df[column], start=start, end=end)


def present_column_mask(df: pd.DataFrame, column: str) -> pd.Series:
    return present_mask(df[column])
