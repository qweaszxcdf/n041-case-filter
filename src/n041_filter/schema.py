from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable, Mapping


@dataclass(frozen=True)
class SlotSchema:
    """Describe one logical slot family in a flat table.

    All patterns are regular expressions by default.

    `principal` describes singleton fields (for example the principal diagnosis).
    `repeated` describes repeated fields and MUST expose a named `slot` group.
    """

    principal: Mapping[str, str] = field(default_factory=dict)
    repeated: Mapping[str, str] = field(default_factory=dict)
    principal_slots: tuple[str, ...] = ()


DEFAULT_SCHEMA = {
    "diagnosis": SlotSchema(
        principal={
            "code": r"^XY_JBDM$",
            "name": r"^XY_ZYZD$",
            "admission_condition": r"^XY_RYBQ$",
            "discharge_condition": r"^XY_CYQK$",
        },
        repeated={
            "code": r"^XY_JBDM(?P<slot>\d+)$",
            "name": r"^XY_QTZD(?P<slot>\d+)$",
            "admission_condition": r"^XY_RYBQ(?P<slot>\d+)$",
            "discharge_condition": r"^XY_CYQK(?P<slot>\d+)$",
        },
    ),
    "procedure": SlotSchema(
        repeated={
            "code": r"^SSBM(?P<slot>\d+)_S$",
            "name": r"^(?:SSJCZMC|SSMC)(?P<slot>\d+)$",
            "date": r"^SSJCZRQ(?P<slot>\d+)$",
            "level": r"^SSJB(?P<slot>\d+)$",
        },
        principal_slots=("1",),
    ),
}


def _sort_slot(value: str):
    if value.isdigit():
        return (0, int(value))
    return (1, value)


def _single_match(columns: list[str], pattern: str) -> str | None:
    regex = re.compile(pattern)
    matches = [c for c in columns if regex.fullmatch(c)]
    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError(f"Pattern {pattern!r} matched multiple singleton columns: {matches}")
    return matches[0]


def discover_slots(columns: Iterable[str], schema: SlotSchema) -> list[dict[str, object]]:
    """Discover logical slots from flat-table columns.

    Returned items contain actual column names. Repeated attributes are bound by
    the same captured `slot` value, preventing cross-slot mismatches. Multiple
    columns matching one repeated attribute in one slot are rejected as an
    ambiguous schema.
    """

    cols = [str(c) for c in columns]
    result: list[dict[str, object]] = []

    if schema.principal:
        item: dict[str, object] = {"slot": "principal", "principal": True}
        for attr, pattern in schema.principal.items():
            col = _single_match(cols, pattern)
            if col is not None:
                item[attr] = col
        if "code" in item:
            result.append(item)

    repeated_matches: dict[tuple[str, str], list[str]] = {}
    for attr, pattern in schema.repeated.items():
        regex = re.compile(pattern)
        if "slot" not in regex.groupindex:
            raise ValueError(
                f"Repeated pattern for {attr!r} must contain named group (?P<slot>...): {pattern!r}"
            )

        for col in cols:
            match = regex.fullmatch(col)
            if not match:
                continue
            slot = match.group("slot")
            repeated_matches.setdefault((slot, attr), []).append(col)

    for (slot, attr), matches in repeated_matches.items():
        if len(matches) > 1:
            raise ValueError(
                f"Repeated schema attribute {attr!r} matched multiple columns "
                f"for slot {slot!r}: {matches}"
            )

    repeated: dict[str, dict[str, object]] = {}
    for (slot, attr), matches in repeated_matches.items():
        repeated.setdefault(
            slot,
            {"slot": slot, "principal": slot in schema.principal_slots},
        )[attr] = matches[0]

    for slot in sorted(repeated, key=_sort_slot):
        item = repeated[slot]
        if "code" in item:
            result.append(item)

    return result
