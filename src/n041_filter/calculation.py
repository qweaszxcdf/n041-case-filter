from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Mapping

import pandas as pd

from .engine import CaseFilter
from .schema import SlotSchema
from .utils import _numeric_series


Selector = Callable[[CaseFilter], CaseFilter]


@dataclass(frozen=True)
class RateResult:
    """Result of a case-based numerator / denominator calculation."""

    numerator: int
    denominator: int
    value: float | None
    scale: float = 100.0
    name: str | None = None
    numerator_cases: pd.DataFrame | None = None
    denominator_cases: pd.DataFrame | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "value": self.value,
            "scale": self.scale,
        }


class Calculator:
    """Thin calculation layer built on top of :class:`CaseFilter`.

    No indicator-specific formulas are embedded here. Callers compose existing
    case filters to define a denominator and then continue filtering that
    denominator to define the numerator.
    """

    def __init__(
        self,
        data: pd.DataFrame | CaseFilter,
        *,
        schema: dict[str, SlotSchema] | None = None,
        procedure_params: object | None = None,
    ):
        if isinstance(data, CaseFilter):
            if schema is not None or procedure_params is not None:
                raise ValueError(
                    "schema/procedure_params must be configured on CaseFilter "
                    "when Calculator is created from an existing CaseFilter"
                )
            self.base = data
        else:
            self.base = CaseFilter(
                data,
                schema=schema,
                procedure_params=procedure_params,
            )

    @staticmethod
    def _select(cases: CaseFilter, selector: Selector | None) -> CaseFilter:
        if selector is None:
            return cases

        selected = selector(cases)
        if not isinstance(selected, CaseFilter):
            raise TypeError("selector must return CaseFilter")

        # A calculation selector is expected to narrow the supplied case set,
        # not silently replace it with an unrelated DataFrame.
        if not selected.df.index.isin(cases.df.index).all():
            raise ValueError("selector must return a subset of the supplied cases")

        return selected

    def cases(self, selector: Selector | None = None) -> CaseFilter:
        return self._select(self.base, selector)

    def count(self, selector: Selector | None = None) -> int:
        return self.cases(selector).count()

    def sum(self, column: str, selector: Selector | None = None) -> float:
        cases = self.cases(selector)
        values = _numeric_series(cases.df[column])
        return float(values.sum())

    def mean(self, column: str, selector: Selector | None = None) -> float | None:
        cases = self.cases(selector)
        values = _numeric_series(cases.df[column])
        value = values.mean()
        if pd.isna(value):
            return None
        return float(value)

    def rate(
        self,
        *,
        denominator: Selector | None = None,
        numerator: Selector | None = None,
        scale: float = 100.0,
        name: str | None = None,
        keep_cases: bool = False,
    ) -> RateResult:
        """Calculate a case-based numerator / denominator rate.

        ``denominator`` is applied to the calculator's base case set.
        ``numerator`` is then applied to the denominator case set, which makes
        numerator ⊆ denominator the natural/default calculation semantics.
        """

        denominator_cases = self._select(self.base, denominator)
        numerator_cases = self._select(denominator_cases, numerator)

        denominator_count = denominator_cases.count()
        numerator_count = numerator_cases.count()

        value = None
        if denominator_count:
            value = numerator_count / denominator_count * scale

        return RateResult(
            name=name,
            numerator=numerator_count,
            denominator=denominator_count,
            value=value,
            scale=scale,
            numerator_cases=numerator_cases.result() if keep_cases else None,
            denominator_cases=denominator_cases.result() if keep_cases else None,
        )
