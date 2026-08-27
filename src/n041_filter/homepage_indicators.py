"""Indicators in the 2026 Shanghai hospital review rules derivable from a
standard inpatient medical-record homepage.

The module deliberately contains only definitions whose numerator and
denominator can be reconstructed from homepage fields.  Indicators requiring
clinical process, device-day, DRG grouping, infection surveillance or manual
reporting data are not guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable, Mapping

import pandas as pd

from .calculation import Calculator
from .engine import CaseFilter
from .schema import SlotSchema
from .specialty_catalog import SpecialtyDefinition, empty_specialty_catalog
from .utils import _numeric_series, normalized_text


@dataclass(frozen=True)
class IndicatorResult:
    """One calculated review indicator."""

    key: str
    name: str
    numerator: float
    denominator: float | None = None
    value: float | None = None
    unit: str = "例"

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "name": self.name,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "value": self.value,
            "unit": self.unit,
        }


# The rules express inclusive ranges.  Prefixes ending at a decimal category
# are sufficient with the package's ICD startswith semantics.
SURGICAL_COMPLICATIONS: Mapping[str, tuple[str, tuple[str, ...]]] = {
    "postop_pulmonary_embolism_rate": ("手术患者手术后肺栓塞发生率", ("I26",)),
    "postop_dvt_rate": ("手术患者手术后深静脉血栓发生率", ("I80.2", "I82.8")),
    "postop_sepsis_rate": ("手术患者手术后脓毒症发生率", ("A40", "A41", "T81.411", "B37.700", "B49")),
    "postop_bleeding_hematoma_rate": ("手术患者手术后出血或血肿发生率", ("T81.0",)),
    "postop_wound_dehiscence_rate": ("手术患者手术伤口裂开发生率", ("T81.3",)),
    "postop_sudden_death_rate": ("手术患者手术后猝死发生率", ("R96.0", "R96.1", "I46.1")),
    "postop_respiratory_failure_rate": ("手术患者手术后呼吸衰竭发生率", ("J95.800X004", "J96.0", "J96.1", "J96.9")),
    "postop_metabolic_disorder_rate": ("手术患者手术后生理/代谢紊乱发生率", ("E89",)),
    "procedure_related_infection_rate": ("与手术/操作相关感染发生率", ("T81.4",)),
    "retained_foreign_body_rate": ("手术过程中异物遗留发生率", ("T81.5", "T81.6")),
    "anesthesia_complication_rate": ("手术患者麻醉并发症发生率", ("T88.2", "T88.3", "T88.4", "T88.5")),
    "postop_pulmonary_complication_rate": ("手术患者肺部感染与肺机能不全发生率", ("J95.1", "J95.2", "J95.3", "J95.4", "J95.8", "J95.9", "J98.4", "J15", "J16", "J18")),
    "accidental_puncture_laceration_rate": ("手术意外穿刺伤或撕裂伤发生率", ("T81.2",)),
    "postop_acute_renal_failure_rate": ("手术后急性肾衰竭发生率", ("N17", "N99.0")),
    "postop_organ_complication_rate": ("手术后各系统/器官并发症发生率", ("K91", "I97.0", "I97.1", "I97.8", "I97.9", "G97", "I60", "I61", "I62", "I63", "I64", "H59.0", "H59.8", "H59.9", "H95.0", "H95.1", "H95.8", "H95.9", "M96", "N98", "N99", "K11.4", "T81.2")),
    "implant_complication_rate": ("植入物并发症（不包括脓毒症）发生率", ("T82", "T83", "T84", "T85")),
    "transplant_complication_rate": ("移植并发症发生率", ("T86",)),
    "replantation_amputation_complication_rate": ("再植和截肢并发症发生率", ("T87.0", "T87.1", "T87.2", "T87.3", "T87.4", "T87.5", "T87.6")),
    "other_postprocedure_complication_rate": ("介入操作与手术后其他并发症发生率", ("T81.1", "T81.7", "T81.8", "T81.9")),
}

OTHER_COMPLICATIONS: Mapping[str, tuple[str, tuple[str, ...]]] = {
    "pressure_injury_rate": ("2期及以上院内压力性损伤发生率", ("L89.1", "L89.2", "L89.3", "L89.9")),
    "iatrogenic_pneumothorax_rate": ("医源性气胸发生率", ("J93.8", "J93.9", "J95.804", "T81.218")),
    "adverse_drug_effect_rate": ("临床用药所致有害效应发生率", ("Y40", "Y42.3", "Y43.1", "Y43.3", "Y44.2", "Y44.3", "Y44.4", "Y44.5", "Y45", "Y52", "Y57.5", "Y57.6")),
}

COHORT_COMPLICATIONS: Mapping[str, tuple[str, str, tuple[str, ...]]] = {
    "infusion_reaction_rate": ("输注反应发生率", "infusion", ("T80.0", "T80.1", "T80.2", "T80.8", "T80.9")),
    "transfusion_reaction_rate": ("输血反应发生率", "transfusion", ("T80",)),
    "fall_hip_fracture_rate": ("院内跌倒/坠床所致髋部骨折发生率", "fall", ("S32.1", "S32.2", "S32.3", "S32.4", "S32.5", "S32.7", "S32.8", "S71.8", "S72.0")),
    "hemodialysis_complication_rate": ("血液透析所致并发症发生率", "hemodialysis", ("T80.6", "T80.8", "T80.9", "T82.4", "T82.7")),
}

NEWBORN_INJURY_CODES = tuple(f"P{i}" for i in range(10, 16))
VAGINAL_DELIVERY_COMPLICATION_CODES = ("O70.2", "O70.3", "O70.9", "O71", "O72", "O73.0", "O73.1", "O74", "O75", "O86", "O87", "O88", "O89", "O90.1", "O90.2", "O90.3", "O90.4", "O90.5", "O90.6", "O90.7", "O90.8", "O90.9", "O95", "A34")
CESAREAN_COMPLICATION_CODES = ("O71", "O72", "O73.0", "O73.1", "O74", "O75", "O86", "O87", "O88", "O89", "O90.0", "O90.2", "O90.3", "O90.4", "O90.5", "O90.6", "O90.7", "O90.8", "O90.9", "O95", "A34")

EXPENSE_COLUMNS: Mapping[str, str] = {
    "ZFY": "住院次均费用", "ZFJE": "次均自付金额", "ZFEJE": "次均自费金额",
    "YLFWF": "次均一般医疗服务费", "ZLCZF": "次均一般治疗操作费",
    "HLF": "次均护理费", "BLZDF": "次均病理诊断费", "SYSZDF": "次均实验室诊断费",
    "YXXZDF": "次均影像学诊断费", "LCZDXMF": "次均临床诊断项目费",
    "FSSZLXMF": "次均非手术治疗项目费", "WLZLF": "次均临床物理治疗费",
    "SSZLF": "次均手术治疗费", "MZF": "次均麻醉费", "SSF": "次均手术费",
    "KFF": "次均康复费", "ZYZLF": "次均中医治疗费", "XYF": "次均西药费",
    "KJYWF": "次均抗菌药物费用", "ZCYF": "次均中成药费", "ZCYF1": "次均中草药费",
    "XF": "次均血费", "JCYCLF": "次均检查耗材费", "ZLYCLF": "次均治疗耗材费",
    "SSYCLF": "次均手术耗材费",
}

class HomepageIndicators:
    """Calculate the review-rule indicators available on a homepage table.

    ``death_values`` defaults to the national homepage discharge-method code
    ``5``.  Delivery and transfusion/dialysis denominators cannot be inferred
    reliably from diagnoses alone, so their code lists are explicit optional
    inputs rather than hidden assumptions.
    """

    def __init__(
        self,
        data: pd.DataFrame | CaseFilter,
        *,
        schema: dict[str, SlotSchema] | None = None,
        discharge_method_column: str = "LYFS",
        death_values: Iterable[str] = ("5",),
        stay_days_column: str | None = None,
        newborn_age_days_column: str | None = None,
        vaginal_delivery_codes: Iterable[str] = ("72", "73"),
        cesarean_codes: Iterable[str] = ("74"),
        cohort_columns: Mapping[str, str] | None = None,
        true_values: Iterable[str] = ("1", "是", "有", "阳性", "Y", "YES", "TRUE"),
        patient_id_column: str | None = None,
        total_cost_column: str | None = None,
        drug_cost_column: str | None = None,
        complication_admission_conditions: Iterable[str] | None = None,
        elective_operation_values: Iterable[str] = ("1", "择期"),
    ):
        effective_schema = schema or (data.schema if isinstance(data, CaseFilter) else None)
        self.cases = CaseFilter(
            data.df if isinstance(data, CaseFilter) else data,
            schema=effective_schema,
            procedure_params=data.procedure_params if isinstance(data, CaseFilter) else None,
        )
        self.calculator = Calculator(self.cases)
        self.discharge_method_column = discharge_method_column
        self.death_values = tuple(death_values)
        self.stay_days_column = stay_days_column
        self.newborn_age_days_column = newborn_age_days_column
        self.vaginal_delivery_codes = tuple(vaginal_delivery_codes)
        self.cesarean_codes = tuple(cesarean_codes)
        self.cohort_columns = dict(cohort_columns or {})
        self.true_values = {str(value).strip().upper() for value in true_values}
        self.patient_id_column = patient_id_column
        self.total_cost_column = total_cost_column
        self.drug_cost_column = drug_cost_column
        self.complication_admission_conditions = (
            tuple(complication_admission_conditions)
            if complication_admission_conditions is not None else None
        )
        self.elective_operation_values = {
            str(value).strip().upper() for value in elective_operation_values
        }

    def _cohort(self, key: str, cases: CaseFilter | None = None) -> CaseFilter | None:
        column = self.cohort_columns.get(key)
        source = self.cases if cases is None else cases
        if not column or column not in source.df:
            return None
        return self._truth(column, source)

    def _matching_text_cases(
        self,
        column: str,
        values: Iterable[str],
        cases: CaseFilter | None = None,
    ) -> CaseFilter:
        expected = {str(value).strip().upper() for value in values}
        source = self.cases if cases is None else cases
        return source.filter(
            lambda frame: normalized_text(frame[column], upper=True).isin(expected)
        )

    def _truth(self, column: str, cases: CaseFilter | None = None) -> CaseFilter:
        return self._matching_text_cases(column, self.true_values, cases)

    def _positive_any_cases(
        self,
        columns: Iterable[str],
        cases: CaseFilter | None = None,
    ) -> CaseFilter:
        source = self.cases if cases is None else cases
        available = tuple(column for column in columns if column in source.df)
        if not available:
            return source.filter(lambda frame: False)
        return source.filter(
            lambda frame: pd.concat(
                [_numeric_series(frame[column]).fillna(0).gt(0) for column in available],
                axis=1,
            ).any(axis=1)
        )

    def _readmission_mask(self) -> pd.Series | None:
        """Mark admissions occurring within 31 days of the preceding discharge."""

        if not self.patient_id_column or self.patient_id_column not in self.cases.df:
            return None
        if not {"RYSJ", "CYSJ"}.issubset(self.cases.df.columns):
            return None
        work = pd.DataFrame(index=self.cases.df.index)
        work["patient"] = self.cases.df[self.patient_id_column].astype("string")
        work["admission"] = pd.to_datetime(self.cases.df["RYSJ"], errors="coerce")
        work["discharge"] = pd.to_datetime(self.cases.df["CYSJ"], errors="coerce")
        work = work.sort_values(["patient", "admission"])
        previous = work.groupby("patient", dropna=False)["discharge"].shift()
        days = (work["admission"] - previous).dt.total_seconds() / 86400
        return days.between(0, 31, inclusive="both").reindex(self.cases.df.index, fill_value=False)

    def _append_icu_metrics(self, results: list[IndicatorResult]) -> None:
        icu = pd.Series(False, index=self.cases.df.index)
        icu_hours = pd.Series(0.0, index=self.cases.df.index)
        for slot in range(1, 6):
            name, entered, exited = f"ZZJHSMC{slot}", f"JRSJ{slot}", f"TCSJ{slot}"
            if name in self.cases.df:
                icu |= self.cases.df.index.isin(self.cases.present(name).df.index)
            if entered in self.cases.df and exited in self.cases.df:
                start = pd.to_datetime(self.cases.df[entered], errors="coerce")
                end = pd.to_datetime(self.cases.df[exited], errors="coerce")
                hours = (end - start).dt.total_seconds().div(3600).clip(lower=0).fillna(0)
                icu_hours += hours
                icu |= hours.gt(0)
        if icu.any() or any(f"ZZJHSMC{i}" in self.cases.df for i in range(1, 6)):
            icu_rate = self.calculator.rate(
                numerator=lambda cases: cases.filter(
                    lambda frame: icu.reindex(frame.index, fill_value=False)
                ),
            )
            results.append(IndicatorResult(
                "icu_admission_rate",
                "ICU患者收治率",
                icu_rate.numerator,
                icu_rate.denominator,
                icu_rate.value,
                "%",
            ))
            stay = (
                _numeric_series(self.cases.df["SJZYTS"]).fillna(0).sum()
                if "SJZYTS" in self.cases.df else 0
            )
            icu_bed_days = float(icu_hours.sum() / 24)
            results.append(IndicatorResult(
                "icu_bed_day_rate",
                "ICU患者收治床日率",
                icu_bed_days,
                float(stay),
                icu_bed_days / stay * 100 if stay else None,
                "%",
            ))
        if "YCHXJSYSJ" in self.cases.df:
            ventilator = _numeric_series(self.cases.df["YCHXJSYSJ"]).fillna(0)
            ventilator_rate = self.calculator.rate(
                numerator=lambda cases: cases.filter(
                    lambda frame: ventilator.reindex(
                        frame.index,
                        fill_value=0,
                    ).gt(0)
                ),
            )
            results.append(IndicatorResult(
                "invasive_ventilation_patient_rate",
                "有创呼吸机使用患者比例",
                ventilator_rate.numerator,
                ventilator_rate.denominator,
                ventilator_rate.value,
                "%",
            ))
            results.append(IndicatorResult(
                "invasive_ventilation_total_time", "有创呼吸机使用总时间",
                float(ventilator.sum()), None, float(ventilator.sum()), "小时",
            ))

    def _append_transfusion_metrics(
        self, results: list[IndicatorResult], surgical: CaseFilter
    ) -> None:
        unit = pd.Series(0.0, index=self.cases.df.index)
        ml = pd.Series(0.0, index=self.cases.df.index)
        has_columns = False
        for slot in range(1, 7):
            for prefix, target in (("SXL_U", unit), ("SXL_ML", ml)):
                column = f"{prefix}{slot}"
                if column in self.cases.df:
                    has_columns = True
                    target += _numeric_series(self.cases.df[column]).fillna(0)
        if not has_columns:
            return
        transfused = unit.gt(0) | ml.gt(0)
        transfusion_rate = self.calculator.rate(
            numerator=lambda cases: cases.filter(
                lambda frame: transfused.reindex(
                    frame.index,
                    fill_value=False,
                )
            ),
        )
        results.append(IndicatorResult(
            "transfusion_patient_rate",
            "出院患者输血率",
            transfusion_rate.numerator,
            transfusion_rate.denominator,
            transfusion_rate.value,
            "%",
        ))
        for suffix, name, values, unit_name in (
            ("unit", "出院患者人均输血量（U）", unit, "U/例"),
            ("ml", "出院患者人均输血量（ml）", ml, "ml/例"),
        ):
            surgical_values = values.loc[surgical.df.index]
            total = float(values.sum())
            discharges = float(len(self.cases.df))
            results.append(IndicatorResult(
                f"transfusion_per_discharge_{suffix}",
                name,
                total,
                discharges,
                total / discharges if discharges else None,
                unit_name,
            ))
            surgical_total = float(surgical_values.sum())
            surgical_count = float(surgical.count())
            results.append(IndicatorResult(
                f"transfusion_per_surgical_case_{suffix}",
                f"手术患者人均输血量（{suffix}）",
                surgical_total,
                surgical_count,
                surgical_total / surgical_count if surgical_count else None,
                unit_name,
            ))
        if "SXFY" in self.cases.df:
            reaction_rate = self.calculator.rate(
                denominator=lambda cases: cases.filter(
                    lambda frame: transfused.reindex(
                        frame.index,
                        fill_value=False,
                    )
                ),
                numerator=lambda cases: self._truth("SXFY", cases),
            )
            results.append(IndicatorResult(
                "transfusion_reaction_rate",
                "输血反应发生率",
                reaction_rate.numerator,
                reaction_rate.denominator,
                reaction_rate.value,
                "%",
            ))

        for label, wanted in (("grade_1_2", {1, 2}), ("grade_3_4", {3, 4})):
            cohort = self.cases.procedure(level=wanted)
            for suffix, values, unit_name in (("unit", unit, "U/台"), ("ml", ml, "ml/台")):
                cohort_values = values.loc[cohort.df.index]
                denominator = cohort.count()
                numerator = float(cohort_values.sum())
                results.append(IndicatorResult(
                    f"{label}_operation_transfusion_{suffix}",
                    f"{'一二' if label == 'grade_1_2' else '三四'}级手术台均用血量（{suffix}）",
                    numerator,
                    denominator,
                    numerator / denominator if denominator else None,
                    unit_name,
                ))

    def _append_newborn_metrics(self, results: list[IndicatorResult]) -> None:
        births = giant = 0
        for slot in range(1, 6):
            weight_col, sex_col = f"XSRTZ{slot}", f"XSRXB{slot}"
            if weight_col not in self.cases.df:
                continue
            weights = _numeric_series(self.cases.df[weight_col])
            present = weights.gt(0)
            if sex_col in self.cases.df:
                present |= self.cases.df.index.isin(self.cases.present(sex_col).df.index)
            births += int(present.sum())
            giant += int((weights >= 4000).sum())
        if births:
            results.append(IndicatorResult(
                "macrosomia_rate",
                "巨大儿发生率",
                giant,
                births,
                giant / births * 100,
                "%",
            ))
            if "CHCX" in self.cases.df:
                hemorrhage_rate = self.calculator.rate(
                    denominator=lambda cases: self._positive_any_cases(
                        (f"XSRTZ{slot}" for slot in range(1, 6)),
                        cases,
                    ),
                    numerator=lambda cases: self._truth("CHCX", cases),
                )
                results.append(IndicatorResult(
                    "postpartum_hemorrhage_rate",
                    "产后出血发生率",
                    hemorrhage_rate.numerator,
                    hemorrhage_rate.denominator,
                    hemorrhage_rate.value,
                    "%",
                ))
            cesarean_rate = self.calculator.rate(
                denominator=lambda cases: self._positive_any_cases(
                    (f"XSRTZ{slot}" for slot in range(1, 6)),
                    cases,
                ),
                numerator=lambda cases: cases.procedure(self.cesarean_codes),
            )
            results.append(IndicatorResult(
                "cesarean_delivery_rate",
                "剖宫产率",
                cesarean_rate.numerator,
                cesarean_rate.denominator,
                cesarean_rate.value,
                "%",
            ))
            vaginal_rate = self.calculator.rate(
                denominator=lambda cases: self._positive_any_cases(
                    (f"XSRTZ{slot}" for slot in range(1, 6)),
                    cases,
                ),
                numerator=lambda cases: cases.procedure(
                    self.vaginal_delivery_codes
                ),
            )
            results.append(IndicatorResult(
                "vaginal_delivery_rate",
                "阴道分娩率",
                vaginal_rate.numerator,
                vaginal_rate.denominator,
                vaginal_rate.value,
                "%",
            ))
            for column, key, name in (
                ("XSRJBSC", "newborn_disease_screening_rate", "新生儿疾病筛查率"),
                ("RCMDSC", "maternal_syphilis_screening_rate", "妊娠梅毒筛查率"),
            ):
                if column in self.cases.df:
                    screening_rate = self.calculator.rate(
                        denominator=lambda cases: self._positive_any_cases(
                            (f"XSRTZ{slot}" for slot in range(1, 6)),
                            cases,
                        ),
                        numerator=lambda cases, column=column: self._truth(
                            column,
                            cases,
                        ),
                    )
                    results.append(IndicatorResult(
                        key,
                        name,
                        screening_rate.numerator,
                        screening_rate.denominator,
                        screening_rate.value,
                        "%",
                    ))

    def calculate(self) -> list[IndicatorResult]:
        """Return every indicator supported by the supplied homepage columns."""

        results: list[IndicatorResult] = []
        df = self.cases.df

        principal_diagnoses = self.cases.diagnosis(principal=True)
        principal_codes = {
            value[:5]
            for slot in principal_diagnoses.diagnosis_slots
            if slot.get("principal") and slot.get("code")
            for value in normalized_text(
                principal_diagnoses.df[str(slot["code"])], upper=True
            )
            if value
        }
        results.append(IndicatorResult("diagnosis_category_count", "收治病种数量（主要诊断ICD-10四位亚目）", len(principal_codes)))

        principal_procedures = self.cases.procedure(principal=True)
        procedure_codes = {
            value[:5]
            for slot in principal_procedures.procedure_slots
            if slot.get("principal") and slot.get("code")
            for value in normalized_text(
                principal_procedures.df[str(slot["code"])], upper=True
            )
            if value
        }
        results.append(IndicatorResult("procedure_category_count", "住院术种数量（主要手术ICD-9-CM-3四位亚目）", len(procedure_codes)))

        if self.stay_days_column and self.stay_days_column in df:
            stay = _numeric_series(df[self.stay_days_column])
        elif {"RYSJ", "CYSJ"}.issubset(df.columns):
            stay = (pd.to_datetime(df["CYSJ"], errors="coerce") - pd.to_datetime(df["RYSJ"], errors="coerce")).dt.total_seconds() / 86400
        else:
            stay = None
        if stay is not None:
            valid = stay.dropna()
            results.append(IndicatorResult("average_length_of_stay", "平均住院日", float(valid.sum()), float(valid.count()), float(valid.mean()) if len(valid) else None, "天"))

        grade_operation_rate = self.calculator.rate(
            denominator=lambda cases: cases.procedure(incision_healing=any),
            numerator=lambda cases: cases.procedure(
                level=[3, 4],
                incision_healing=any,
            ),
        )
        results.append(IndicatorResult(
            "grade_3_4_operation_rate",
            "出院患者三四级手术比例",
            grade_operation_rate.numerator,
            grade_operation_rate.denominator,
            grade_operation_rate.value,
            "%",
        ))

        if any(slot.get("operation_type") for slot in self.cases.procedure_slots):
            day_operation_rate = self.calculator.rate(
                denominator=lambda cases: cases.procedure(
                    operation_type=self.elective_operation_values,
                ),
                numerator=lambda cases: cases.procedure(
                    operation_type=self.elective_operation_values,
                    day_surgery=self.true_values,
                ),
            )
            results.append(IndicatorResult(
                "day_surgery_among_elective_rate",
                "日间手术占择期手术比例",
                day_operation_rate.numerator,
                day_operation_rate.denominator,
                day_operation_rate.value,
                "%",
            ))
        else:
            day_surgery = self._cohort("day_surgery")
            elective_surgery = self._cohort("elective_surgery")
            if day_surgery is not None and elective_surgery is not None:
                day_operation_rate = self.calculator.rate(
                    denominator=lambda cases: self._cohort(
                        "elective_surgery",
                        cases,
                    ),
                    numerator=lambda cases: self._cohort(
                        "day_surgery",
                        cases,
                    ),
                )
                results.append(IndicatorResult(
                    "day_surgery_among_elective_rate",
                    "日间手术占择期手术比例",
                    day_operation_rate.numerator,
                    day_operation_rate.denominator,
                    day_operation_rate.value,
                    "%",
                ))

        mortality_rate = self.calculator.rate(
            numerator=lambda cases: cases.where(
                self.discharge_method_column,
                self.death_values,
            ),
        )
        results.append(IndicatorResult(
            "inpatient_mortality_rate",
            "患者住院总死亡率",
            mortality_rate.numerator,
            mortality_rate.denominator,
            mortality_rate.value,
            "%",
        ))
        surgical = self.cases.procedure()
        surgical_mortality_rate = self.calculator.rate(
            denominator=lambda cases: cases.procedure(),
            numerator=lambda cases: cases.where(
                self.discharge_method_column,
                self.death_values,
            ),
        )
        results.append(IndicatorResult(
            "surgical_inpatient_mortality_rate",
            "手术患者住院总死亡率",
            surgical_mortality_rate.numerator,
            surgical_mortality_rate.denominator,
            surgical_mortality_rate.value,
            "%",
        ))

        readmission = self._readmission_mask()
        if readmission is not None:
            readmission_rate = self.calculator.rate(
                denominator=lambda cases: cases.exclude(
                    self.discharge_method_column,
                    self.death_values,
                ),
                numerator=lambda cases: cases.filter(
                    lambda frame: readmission.reindex(
                        frame.index,
                        fill_value=False,
                    )
                ),
            )
            results.append(IndicatorResult(
                "readmission_within_31_days_rate",
                "出院后0-31天再住院率（需结合非预期标志上报）",
                readmission_rate.numerator,
                readmission_rate.denominator,
                readmission_rate.value,
                "%",
            ))

        repeat_48h_rate = self.calculator.rate(
            denominator=lambda cases: cases.procedure(),
            numerator=lambda cases: cases.procedure(
                date_diff_hours=48,
            ).procedure(unplanned=self.true_values),
        )
        results.append(IndicatorResult(
            "repeat_operation_within_48h_rate",
            "48小时内再次手术率（需结合非计划标志上报）",
            repeat_48h_rate.numerator,
            repeat_48h_rate.denominator,
            repeat_48h_rate.value,
            "%",
        ))
        repeat_31d_rate = self.calculator.rate(
            denominator=lambda cases: cases.procedure(),
            numerator=lambda cases: cases.procedure(
                date_diff_hours=31 * 24,
            ).procedure(unplanned=self.true_values),
        )
        results.append(IndicatorResult(
            "repeat_operation_within_31d_rate",
            "31天内再次手术率（需结合非计划标志上报）",
            repeat_31d_rate.numerator,
            repeat_31d_rate.denominator,
            repeat_31d_rate.value,
            "%",
        ))

        if "SFJHZCRY" in df:
            unexpected_readmission_rate = self.calculator.rate(
                denominator=lambda cases: cases.exclude(
                    self.discharge_method_column,
                    self.death_values,
                ),
                numerator=lambda cases: self._truth("SFJHZCRY", cases),
            )
            results.append(IndicatorResult(
                "unexpected_readmission_rate",
                "非计划再次入院率（首页标志）",
                unexpected_readmission_rate.numerator,
                unexpected_readmission_rate.denominator,
                unexpected_readmission_rate.value,
                "%",
            ))

        if "SSLCLJ" in df:
            pathway_rate = self.calculator.rate(
                numerator=lambda cases: self._truth("SSLCLJ", cases),
            )
            results.append(IndicatorResult(
                "clinical_pathway_rate",
                "住院患者临床路径管理病例数占比",
                pathway_rate.numerator,
                pathway_rate.denominator,
                pathway_rate.value,
                "%",
            ))

        if {"QJCS", "QJCGCS"}.issubset(df.columns):
            rescues = _numeric_series(df["QJCS"]).fillna(0)
            successes = _numeric_series(df["QJCGCS"]).fillna(0)
            rescue_rate = self.calculator.rate(
                numerator=lambda cases: cases.filter(
                    lambda frame: rescues.reindex(
                        frame.index,
                        fill_value=0,
                    ).gt(0)
                ),
            )
            results.append(IndicatorResult(
                "inpatient_rescue_rate",
                "住院患者抢救率",
                rescue_rate.numerator,
                rescue_rate.denominator,
                rescue_rate.value,
                "%",
            ))
            rescue_count = float(rescues.sum())
            success_count = float(successes.sum())
            results.append(IndicatorResult(
                "rescue_success_rate",
                "抢救成功率",
                success_count,
                rescue_count,
                success_count / rescue_count * 100 if rescue_count else None,
                "%",
            ))

        if "SWHZSJ" in df:
            autopsy_rate = self.calculator.rate(
                denominator=lambda cases: cases.where(
                    self.discharge_method_column,
                    self.death_values,
                ),
                numerator=lambda cases: self._truth("SWHZSJ", cases),
            )
            results.append(IndicatorResult(
                "deceased_autopsy_rate",
                "死亡患者尸检率",
                autopsy_rate.numerator,
                autopsy_rate.denominator,
                autopsy_rate.value,
                "%",
            ))

        if self.newborn_age_days_column and self.newborn_age_days_column in df:
            newborn_mortality_rate = self.calculator.rate(
                denominator=lambda cases: cases.filter(
                    lambda frame: _numeric_series(
                        frame[self.newborn_age_days_column]
                    ).between(0, 28, inclusive="left")
                ),
                numerator=lambda cases: cases.where(
                    self.discharge_method_column,
                    self.death_values,
                ),
            )
            results.append(IndicatorResult(
                "newborn_inpatient_mortality_rate",
                "新生儿患者住院总死亡率",
                newborn_mortality_rate.numerator,
                newborn_mortality_rate.denominator,
                newborn_mortality_rate.value,
                "%",
            ))
            newborn_injury_rate = self.calculator.rate(
                denominator=lambda cases: cases.filter(
                    lambda frame: _numeric_series(
                        frame[self.newborn_age_days_column]
                    ).between(0, 28, inclusive="left")
                ),
                numerator=lambda cases: cases.diagnosis(NEWBORN_INJURY_CODES),
            )
            results.append(IndicatorResult(
                "newborn_birth_injury_rate",
                "新生儿产伤发生率",
                newborn_injury_rate.numerator,
                newborn_injury_rate.denominator,
                newborn_injury_rate.value,
                "%",
            ))

        complication_criteria = {}
        if self.complication_admission_conditions is not None:
            complication_criteria = {
                "principal": False,
                "admission_condition": self.complication_admission_conditions,
            }
        for key, (name, codes) in SURGICAL_COMPLICATIONS.items():
            if key == "replantation_amputation_complication_rate":
                # The rules require the procedure cohort but do not publish its
                # ICD-9-CM-3 list; callers can calculate it with Calculator.
                continue
            rate = self.calculator.rate(
                denominator=lambda cases: cases.procedure(),
                numerator=lambda cases, codes=codes: cases.diagnosis(
                    codes,
                    **complication_criteria,
                ),
            )
            results.append(IndicatorResult(
                key,
                name,
                rate.numerator,
                rate.denominator,
                rate.value,
                "%",
            ))

        for key, (name, codes) in OTHER_COMPLICATIONS.items():
            rate = self.calculator.rate(
                numerator=lambda cases, codes=codes: cases.diagnosis(
                    codes,
                    **complication_criteria,
                ),
            )
            results.append(IndicatorResult(
                key,
                name,
                rate.numerator,
                rate.denominator,
                rate.value,
                "%",
            ))

        for key, (name, cohort_key, codes) in COHORT_COMPLICATIONS.items():
            cohort = self._cohort(cohort_key)
            if cohort is not None:
                rate = self.calculator.rate(
                    denominator=lambda cases, cohort_key=cohort_key: self._cohort(
                        cohort_key,
                        cases,
                    ),
                    numerator=lambda cases, codes=codes: cases.diagnosis(
                        codes,
                        **complication_criteria,
                    ),
                )
                results.append(IndicatorResult(
                    key,
                    name,
                    rate.numerator,
                    rate.denominator,
                    rate.value,
                    "%",
                ))

        hospital_infection = self._cohort("hospital_infection")
        if hospital_infection is not None:
            hospital_infection_rate = self.calculator.rate(
                numerator=lambda cases: self._cohort(
                    "hospital_infection",
                    cases,
                ),
            )
            results.append(IndicatorResult(
                "hospital_infection_rate",
                "医院感染发生率",
                hospital_infection_rate.numerator,
                hospital_infection_rate.denominator,
                hospital_infection_rate.value,
                "%",
            ))
        incision_i = self._cohort("incision_class_i")
        if incision_i is not None:
            incision_infection = self._cohort("incision_infection", incision_i)
        else:
            incision_infection = None
        if incision_i is not None and incision_infection is not None:
            incision_infection_rate = self.calculator.rate(
                denominator=lambda cases: self._cohort(
                    "incision_class_i",
                    cases,
                ),
                numerator=lambda cases: self._cohort(
                    "incision_infection",
                    cases,
                ),
            )
            results.append(IndicatorResult(
                "class_i_incision_infection_rate",
                "I类切口手术部位感染率",
                incision_infection_rate.numerator,
                incision_infection_rate.denominator,
                incision_infection_rate.value,
                "%",
            ))
        clinical_pathway = self._cohort("clinical_pathway")
        if clinical_pathway is not None and "SSLCLJ" not in df:
            pathway_rate = self.calculator.rate(
                numerator=lambda cases: self._cohort(
                    "clinical_pathway",
                    cases,
                ),
            )
            results.append(IndicatorResult(
                "clinical_pathway_rate",
                "住院患者临床路径管理病例数占比",
                pathway_rate.numerator,
                pathway_rate.denominator,
                pathway_rate.value,
                "%",
            ))

        delivery_groups = (
            ("vaginal_delivery_complication_rate", "阴道分娩产妇分娩或产褥期并发症发生率", self.vaginal_delivery_codes, VAGINAL_DELIVERY_COMPLICATION_CODES),
            ("cesarean_delivery_complication_rate", "剖宫产分娩产妇分娩或产褥期并发症发生率", self.cesarean_codes, CESAREAN_COMPLICATION_CODES),
        )
        for key, name, procedure_codes_, complication_codes in delivery_groups:
            if procedure_codes_:
                rate = self.calculator.rate(
                    denominator=lambda cases, procedure_codes_=procedure_codes_: cases.procedure(
                        procedure_codes_
                    ),
                    numerator=lambda cases, complication_codes=complication_codes: cases.diagnosis(
                        complication_codes,
                        **complication_criteria,
                    ),
                )
                results.append(IndicatorResult(
                    key,
                    name,
                    rate.numerator,
                    rate.denominator,
                    rate.value,
                    "%",
                ))

        for key, name, column in (
            ("inpatient_cost_per_case", "住院次均费用", self.total_cost_column),
            ("inpatient_drug_cost_per_case", "住院次均药品费用", self.drug_cost_column),
        ):
            if column and column in df:
                values = _numeric_series(df[column]).dropna()
                results.append(IndicatorResult(
                    key, name, float(values.sum()), float(values.count()),
                    float(values.mean()) if len(values) else None, "元",
                ))

        # The supplied Shanghai homepage contains detailed expense fields.  In
        # addition to the two review growth bases, expose every available
        # per-discharge expense component and its share of total expense.
        total_expense = _numeric_series(df["ZFY"]) if "ZFY" in df else None
        for column, name in EXPENSE_COLUMNS.items():
            if column not in df:
                continue
            values = _numeric_series(df[column]).dropna()
            results.append(IndicatorResult(
                f"average_{column.lower()}", name, float(values.sum()),
                float(values.count()), float(values.mean()) if len(values) else None, "元",
            ))
            if column != "ZFY" and total_expense is not None:
                denominator = float(total_expense.fillna(0).sum())
                numerator = float(values.sum())
                results.append(IndicatorResult(
                    f"{column.lower()}_expense_share",
                    f"{name.removeprefix('次均')}占总费用比例",
                    numerator,
                    denominator,
                    numerator / denominator * 100 if denominator else None,
                    "%",
                ))

        if "BAZL" in df:
            grade_a_rate = self.calculator.rate(
                numerator=lambda cases: self._matching_text_cases(
                    "BAZL",
                    {"甲", "甲级", "A"},
                    cases,
                ),
            )
            results.append(IndicatorResult(
                "grade_a_medical_record_rate",
                "甲级病历率",
                grade_a_rate.numerator,
                grade_a_rate.denominator,
                grade_a_rate.value,
                "%",
            ))

        nursing_columns = {
            "SJZY_TJHL": "特级护理日占比", "SJZY_YJHL": "一级护理日占比",
            "SJZY_EJHL": "二级护理日占比", "SJZY_SJHL": "三级护理日占比",
        }
        nursing_days = {
            column: _numeric_series(df[column]).fillna(0)
            for column in nursing_columns if column in df
        }
        if nursing_days:
            denominator = float(sum((values.sum() for values in nursing_days.values()), 0))
            for column, values in nursing_days.items():
                numerator = float(values.sum())
                results.append(IndicatorResult(
                    f"{column.lower()}_share",
                    nursing_columns[column],
                    numerator,
                    denominator,
                    numerator / denominator * 100 if denominator else None,
                    "%",
                ))

        self._append_icu_metrics(results)
        self._append_transfusion_metrics(results, surgical)
        self._append_newborn_metrics(results)
        return results

    def growth_from(self, previous: "HomepageIndicators") -> list[IndicatorResult]:
        """Calculate the two year-on-year inpatient expense growth indicators."""

        current = {item.key: item for item in self.calculate()}
        prior = {item.key: item for item in previous.calculate()}
        results = []
        for source, key, name in (
            ("inpatient_cost_per_case", "inpatient_cost_growth_rate", "住院次均费用增幅"),
            ("inpatient_drug_cost_per_case", "inpatient_drug_cost_growth_rate", "住院次均药品费用增幅"),
        ):
            if source not in current or source not in prior:
                continue
            now, before = current[source].value, prior[source].value
            value = None if before in (None, 0) or now is None else (now - before) / before * 100
            results.append(IndicatorResult(key, name, float(now or 0), float(before or 0), value, "%"))
        for source, item in current.items():
            if not source.startswith("average_") or source not in prior:
                continue
            now, before = item.value, prior[source].value
            value = None if before in (None, 0) or now is None else (now - before) / before * 100
            results.append(IndicatorResult(
                f"{source}_growth_rate", f"{item.name}同比增幅", float(now or 0),
                float(before or 0), value, "%",
            ))
        return results

    def specialty_summary(
        self,
        catalog: Mapping[str, SpecialtyDefinition] | None = None,
        *,
        department_column: str = "CYKB",
    ) -> pd.DataFrame:
        """Calculate key-disease and key-technology volumes for 44 specialties.

        The review appendix itself contains names and thresholds rather than
        ICD value sets. Empty specialties are returned as ``需要字段`` until an
        approved hospital code catalog is supplied.
        """

        catalog = dict(catalog or empty_specialty_catalog())
        rows: list[dict[str, object]] = []
        for specialty, definition in catalog.items():
            if department_column in self.cases.df:
                department_cases = self.cases.where(
                    department_column,
                    definition.department_values or (definition.name,),
                )
            else:
                department_cases = self.cases
            denominator = department_cases.count()
            if not definition.key_diseases and not definition.key_technologies:
                rows.append({
                    "specialty": specialty, "category": None, "item": None,
                    "count": None, "department_discharges": denominator, "rate": None,
                    "status": "需要字段", "reason": "评审附件未发布ICD值集，需导入医院审核后的编码目录",
                })
                continue
            for category, groups in (
                ("重点病种", definition.key_diseases),
                ("关键技术", definition.key_technologies),
            ):
                for item, codes in groups.items():
                    selected_cases = (
                        department_cases.diagnosis(codes)
                        if category == "重点病种"
                        else department_cases.procedure(codes)
                    )
                    count = selected_cases.count()
                    rows.append({
                        "specialty": specialty, "category": category, "item": item,
                        "count": count, "department_discharges": denominator,
                        "rate": count / denominator * 100 if denominator else None,
                        "status": "可直接计算", "reason": None,
                    })
        return pd.DataFrame(rows)

    def indicator_catalog(self) -> pd.DataFrame:
        """Return a unified availability catalog for review-rule indicators."""

        calculated = self.calculate()
        review_only = {
            "readmission_within_31_days_rate", "repeat_operation_within_48h_rate",
            "repeat_operation_within_31d_rate",
        }
        rows = [{
            "key": item.key, "name": item.name,
            "status": "仅供复核" if item.key in review_only else "可直接计算",
            "reason": "需结合非预期/非计划业务认定" if item.key in review_only else None,
        } for item in calculated]
        required = (
            ("specialty_code_catalog", "44个专科重点病种与关键技术", "需医院审核后的ICD-10/ICD-9-CM-3值集"),
            ("low_risk_mortality", "ICD/DRG低风险组死亡率", "需年度低风险组目录或DRG分组结果"),
            ("vaginal_delivery_metrics", "阴道分娩相关指标", "需确认本院分娩操作编码值集"),
        )
        unavailable = (
            ("drg_metrics", "DRGs组数、CMI、时间指数、费用指数", "需要DRG分组器及全市基准"),
            ("device_day_infections", "VAP/CRBSI/CAUTI千设备日发生率", "首页没有完整设备日与感染监测事件"),
            ("clinical_process_metrics", "治疗前评估、bundle、规范预防及随访指标", "需要医嘱、病程或随访系统"),
        )
        rows.extend({"key": key, "name": name, "status": "需要字段", "reason": reason} for key, name, reason in required)
        rows.extend({"key": key, "name": name, "status": "无法由首页计算", "reason": reason} for key, name, reason in unavailable)
        return pd.DataFrame(rows).drop_duplicates("key", keep="first")

    def by_department(self, column: str = "CYKB") -> pd.DataFrame:
        """Return homepage-derived operating indicators for every department."""

        if column not in self.cases.df:
            raise KeyError(f"missing department column: {column}")
        df = self.cases.df
        stay = _numeric_series(df["SJZYTS"]) if "SJZYTS" in df else pd.Series(float("nan"), index=df.index)
        cost = _numeric_series(df["ZFY"]) if "ZFY" in df else pd.Series(float("nan"), index=df.index)
        rescue = _numeric_series(df["QJCS"]).fillna(0) if "QJCS" in df else pd.Series(0, index=df.index)
        success = _numeric_series(df["QJCGCS"]).fillna(0) if "QJCGCS" in df else pd.Series(0, index=df.index)
        rows = []
        for department in df.groupby(column, dropna=False).groups:
            if pd.isna(department):
                selected_cases = self.cases.filter(lambda frame: frame[column].isna())
            else:
                selected_cases = self.cases.where(column, department)
            operations_cases = selected_cases.procedure()
            death_cases = selected_cases.where(
                self.discharge_method_column, self.death_values
            )
            selected_rescue_cases = selected_cases.filter(
                lambda frame: rescue.reindex(frame.index, fill_value=0).gt(0)
            )
            count = selected_cases.count()
            operations = operations_cases.count()
            selected_index = selected_cases.df.index
            rescue_count = float(rescue.loc[selected_index].sum())
            rows.append({
                "department": department,
                "discharges": count,
                "surgical_cases": operations,
                "surgical_case_rate": operations / count * 100 if count else None,
                "deaths": death_cases.count(),
                "mortality_rate": death_cases.count() / count * 100 if count else None,
                "average_length_of_stay": float(stay.loc[selected_index].mean()) if stay.loc[selected_index].notna().any() else None,
                "average_cost": float(cost.loc[selected_index].mean()) if cost.loc[selected_index].notna().any() else None,
                "rescue_cases": selected_rescue_cases.count(),
                "rescue_rate": selected_rescue_cases.count() / count * 100 if count else None,
                "rescue_success_rate": float(success.loc[selected_index].sum()) / rescue_count * 100 if rescue_count else None,
            })
        return pd.DataFrame(rows)

    def to_frame(self) -> pd.DataFrame:
        """Calculate indicators and return a reporting-friendly table."""

        return pd.DataFrame(item.to_dict() for item in self.calculate())
