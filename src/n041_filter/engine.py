from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Mapping
import pandas as pd

from .filters import (
    contains_mask,
    date_between_mask,
    diagnosis_mask,
    numeric_between_mask,
    procedure_mask,
    present_column_mask,
    value_mask,
)
from .procedure_params import load_procedure_params
from .schema import DEFAULT_SCHEMA, SlotSchema, discover_slots
from .utils import as_list, match_codes


@dataclass(frozen=True)
class CaseFilter:
    """Immutable-ish chainable filter over the original flat DataFrame."""

    df: pd.DataFrame
    schema: dict[str, SlotSchema] | None = None
    procedure_params: object | None = None

    def __post_init__(self):
        object.__setattr__(self, "schema", self.schema or DEFAULT_SCHEMA)
        object.__setattr__(self, "procedure_params", load_procedure_params(self.procedure_params))
        object.__setattr__(self, "diagnosis_slots", discover_slots(self.df.columns, self.schema["diagnosis"]))
        object.__setattr__(self, "procedure_slots", discover_slots(self.df.columns, self.schema["procedure"]))

    def _subset(self, mask: pd.Series) -> "CaseFilter":
        return CaseFilter(
            self.df.loc[mask].copy(),
            schema=self.schema,
            procedure_params=self.procedure_params,
        )

    def diagnosis(
        self,
        codes=None,
        *,
        principal: bool | None = None,
        name=None,
        name_contains=None,
        admission_condition=None,
        discharge_condition=None,
    ) -> "CaseFilter":
        mask = diagnosis_mask(
            self.df,
            self.diagnosis_slots,
            codes=codes,
            principal=principal,
            name=name,
            name_contains=name_contains,
            admission_condition=admission_condition,
            discharge_condition=discharge_condition,
        )
        return self._subset(mask)

    def without_diagnosis(self, codes=None, **criteria) -> "CaseFilter":
        """Keep cases with no diagnosis slot matching the supplied criteria."""

        mask = diagnosis_mask(
            self.df,
            self.diagnosis_slots,
            codes=codes,
            **criteria,
        )
        return self._subset(~mask)

    def procedure(
        self,
        codes=None,
        *,
        principal: bool | None = None,
        name=None,
        name_contains=None,
        level=None,
        date_start=None,
        date_end=None,
        date_diff_hours=None,
        params=None,
    ) -> "CaseFilter":
        mask = procedure_mask(
            self.df,
            self.procedure_slots,
            codes=codes,
            principal=principal,
            name=name,
            name_contains=name_contains,
            level=level,
            date_start=date_start,
            date_end=date_end,
            date_diff_hours=date_diff_hours,
            procedure_params=self.procedure_params,
            params=params,
        )
        return self._subset(mask)

    def without_procedure(self, codes=None, **criteria) -> "CaseFilter":
        """Keep cases with no procedure slot matching the supplied criteria."""

        mask = procedure_mask(
            self.df,
            self.procedure_slots,
            codes=codes,
            procedure_params=self.procedure_params,
            **criteria,
        )
        return self._subset(~mask)

    def between(self, column: str, *, start=None, end=None) -> "CaseFilter":
        return self._subset(date_between_mask(self.df, column, start=start, end=end))

    def where(self, column: str, values) -> "CaseFilter":
        return self._subset(value_mask(self.df, column, values))

    def filter(
        self,
        predicate: Callable[[pd.DataFrame], object],
    ) -> "CaseFilter":
        """Apply a custom predicate to the current complete DataFrame.

        The predicate receives the current DataFrame and must return a boolean
        Series, array-like mask, or scalar boolean. The DataFrame should be
        treated as read-only.
        """

        if not callable(predicate):
            raise TypeError("predicate must be callable")

        raw_mask = predicate(self.df)
        if isinstance(raw_mask, pd.Series):
            if not raw_mask.index.is_unique:
                raise ValueError("custom predicate result must have a unique index")
            mask = raw_mask.reindex(self.df.index)
        else:
            mask = pd.Series(raw_mask, index=self.df.index)

        try:
            mask = mask.astype("boolean").fillna(False).astype(bool)
        except (TypeError, ValueError) as exc:
            raise TypeError("predicate must return a boolean mask") from exc

        return self._subset(mask)

    def exclude(self, column: str, values) -> "CaseFilter":
        """Exclude cases whose field equals any supplied value."""

        return self._subset(~value_mask(self.df, column, values))

    def contains(self, column: str, values) -> "CaseFilter":
        """Keep cases whose field contains any supplied text."""

        return self._subset(contains_mask(self.df, column, values))

    def not_contains(self, column: str, values) -> "CaseFilter":
        return self._subset(~contains_mask(self.df, column, values))

    def numeric_between(self, column: str, start=None, end=None) -> "CaseFilter":
        """Filter an inclusive numeric range, for example age, LOS or cost."""

        return self._subset(
            numeric_between_mask(self.df, column, start=start, end=end)
        )

    def present(self, column: str) -> "CaseFilter":
        return self._subset(present_column_mask(self.df, column))

    def missing(self, column: str) -> "CaseFilter":
        return self._subset(~present_column_mask(self.df, column))

    def where_any(self, columns, values, *, codes: bool = False, contains: bool = False) -> "CaseFilter":
        """Keep cases matching a value in any of several header columns.

        ``codes=True`` applies the same prefix semantics as diagnosis and
        procedure codes. ``contains=True`` applies case-insensitive text
        containment. The two modes are mutually exclusive.
        """

        if codes and contains:
            raise ValueError("codes and contains cannot both be True")

        result = pd.Series(False, index=self.df.index)
        wanted = as_list(values)
        for column in as_list(columns) or []:
            series = self.df[str(column)]
            if codes:
                result |= match_codes(series, wanted, upper=False)
            elif contains:
                result |= contains_mask(self.df, str(column), wanted)
            else:
                result |= value_mask(self.df, str(column), wanted)
        return self._subset(result)

    def admitted_between(self, start=None, end=None, *, column="RYSJ") -> "CaseFilter":
        return self.between(column, start=start, end=end)

    def discharged_between(self, start=None, end=None, *, column="CYSJ") -> "CaseFilter":
        return self.between(column, start=start, end=end)

    def result(self) -> pd.DataFrame:
        return self.df.copy()

    def count(self) -> int:
        return len(self.df)

    def slots(self) -> dict[str, list[dict[str, object]]]:
        return {
            "diagnosis": list(self.diagnosis_slots),
            "procedure": list(self.procedure_slots),
        }
