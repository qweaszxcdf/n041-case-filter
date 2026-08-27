"""The 44 specialty names in the review appendix and code-catalog support.

The review PDF names key diseases and technologies but does not publish their
ICD-10 / ICD-9-CM-3 value sets.  A hospital-approved code catalog can therefore
be supplied without embedding invented codes in the package.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping
from pathlib import Path

import pandas as pd


SPECIALTY_NAMES = (
    "心血管内科", "呼吸内科", "消化内科", "神经内科", "内分泌科", "肾病学科",
    "血液内科", "免疫学科", "普通外科", "骨科", "神经外科", "泌尿外科",
    "胸外科", "心脏大血管外科", "妇科", "产科", "新生儿科", "儿科（其他）",
    "眼科", "耳鼻咽喉科", "口腔科", "皮肤科", "精神科", "感染科", "肿瘤科",
    "放射治疗科", "急诊医学科", "康复医学科", "麻醉科", "重症医学科",
    "疼痛科", "中医科", "老年医学科", "全科医学科", "烧伤科", "变态反应科",
    "介入科", "整形外科", "医疗美容科", "放射诊断科", "医学检验科", "病理科",
    "超声医学科", "核医学科",
)


@dataclass(frozen=True)
class SpecialtyDefinition:
    """Approved code groups for one specialty.

    Values are code prefixes and use the same matching semantics as
    :meth:`CaseFilter.diagnosis` and :meth:`CaseFilter.procedure`.
    """

    name: str
    department_values: tuple[str, ...] = ()
    key_diseases: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    key_technologies: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


def empty_specialty_catalog() -> dict[str, SpecialtyDefinition]:
    """Return all 44 appendix specialties, ready for approved code mappings."""

    return {
        name: SpecialtyDefinition(name=name, department_values=(name,))
        for name in SPECIALTY_NAMES
    }


def load_specialty_catalog(path: str | Path) -> dict[str, SpecialtyDefinition]:
    """Load a hospital-approved CSV/XLSX code catalog.

    Required columns are ``specialty``, ``category``, ``item`` and ``codes``.
    ``codes`` and optional ``department_values`` use ``|`` separators.
    ``category`` must be ``重点病种`` or ``关键技术``.
    """

    path = Path(path)
    frame = pd.read_excel(path, dtype=str) if path.suffix.lower() in {".xlsx", ".xls"} else pd.read_csv(path, dtype=str)
    required = {"specialty", "category", "item", "codes"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"specialty catalog missing columns: {sorted(missing)}")
    result: dict[str, SpecialtyDefinition] = {}
    for specialty, rows in frame.fillna("").groupby("specialty", sort=False):
        diseases: dict[str, tuple[str, ...]] = {}
        technologies: dict[str, tuple[str, ...]] = {}
        departments: set[str] = {str(specialty).strip()}
        for _, row in rows.iterrows():
            category = str(row["category"]).strip()
            target = diseases if category == "重点病种" else technologies if category == "关键技术" else None
            if target is None:
                raise ValueError(f"unknown specialty catalog category: {category!r}")
            codes = tuple(value.strip() for value in str(row["codes"]).split("|") if value.strip())
            if not codes:
                raise ValueError(f"empty codes for {specialty}/{row['item']}")
            target[str(row["item"]).strip()] = codes
            if "department_values" in frame:
                departments.update(value.strip() for value in str(row["department_values"]).split("|") if value.strip())
        result[str(specialty)] = SpecialtyDefinition(
            name=str(specialty), department_values=tuple(sorted(departments)),
            key_diseases=diseases, key_technologies=technologies,
        )
    return result
