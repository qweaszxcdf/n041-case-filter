import pandas as pd
import pytest

from n041_filter import (
    CaseFilter, HomepageIndicators, SpecialtyDefinition, SPECIALTY_NAMES,
    load_specialty_catalog,
)


def sample():
    return pd.DataFrame(
        {
            "RYSJ": ["2026-01-01", "2026-02-01", "2026-03-01"],
            "CYSJ": ["2026-01-06", "2026-02-11", "2026-03-04"],
            "LYFS": ["1", "5", "1"],
            "XY_JBDM": ["I21.01", "J18.90", "I10"],
            "XY_JBDM1": ["I26.0", "T81.3", ""],
            "SSBM1_S": ["36.0101", "81.0200", ""],
            "SSJB1": ["4", "2", ""],
            "QKYHLB1": ["1", "1", ""],
            "SSJCZRQ1": ["2026-01-02", "2026-02-02", ""],
            "SSBM2_S": ["36.0200", "", ""],
            "QKYHLB2": ["1", "", ""],
            "SSJCZRQ2": ["2026-01-03", "", ""],
            "SSJB2": ["3", "", ""],
            "SFJHSS2": ["1", "", ""],
        }
    )


def by_key(results):
    return {item.key: item for item in results}


def test_optional_homepage_procedure_schema_fields_are_nonintrusive():
    cases = CaseFilter(sample())

    assert "unplanned" not in cases.procedure_slots[0]
    assert "day_surgery" not in cases.procedure_slots[0]
    assert "operation_type" not in cases.procedure_slots[0]
    assert cases.procedure().count() == 2


def test_procedure_attributes_are_same_slot_and_case_insensitive():
    data = sample().assign(
        SSLX1=["择期", "择期", ""],
        SFRJSS1=["", "YES", ""],
        SFRJSS2=["1", "", ""],
    )

    selected = CaseFilter(data).procedure(
        operation_type=["择期"],
        day_surgery=["yes"],
    )

    assert list(selected.df.index) == [1]


def test_calculates_counts_stay_mortality_and_complications():
    result = by_key(HomepageIndicators(sample()).calculate())

    assert result["diagnosis_category_count"].numerator == 3
    assert result["procedure_category_count"].numerator == 2
    assert result["average_length_of_stay"].value == 6
    assert result["grade_3_4_operation_rate"].numerator == 1
    assert result["grade_3_4_operation_rate"].denominator == 2
    assert result["inpatient_mortality_rate"].value == pytest.approx(100 / 3)
    assert result["surgical_inpatient_mortality_rate"].value == 50
    assert result["postop_pulmonary_embolism_rate"].value == 50
    assert result["postop_wound_dehiscence_rate"].value == 50
    assert result["repeat_operation_within_48h_rate"].value == 50


def test_procedure_levels_with_decimal_text_are_counted():
    data = sample()
    data["SSJB1"] = ["4.0", "2.0", ""]
    data["SSJB2"] = ["3.0", "", ""]

    result = by_key(HomepageIndicators(data).calculate())

    assert result["grade_3_4_operation_rate"].numerator == 1
    assert result["grade_3_4_operation_rate"].denominator == 2


def test_to_frame_has_stable_reporting_columns():
    report = HomepageIndicators(sample()).to_frame()

    assert list(report.columns) == [
        "key", "name", "numerator", "denominator", "value", "unit"
    ]
    assert report["key"].is_unique


def test_optional_homepage_cohorts_and_cost_growth():
    current = sample().assign(
        DAY=["1", "0", "0"], ELECTIVE=["1", "1", "0"],
        INFUSION=["0", "1", "0"], PATH=["1", "0", "1"],
        ZFY=[200, 400, 600], YPFY=[20, 40, 60],
    )
    current.loc[1, "XY_JBDM1"] = "T80.1"
    previous = current.assign(ZFY=[100, 200, 300], YPFY=[10, 20, 30])
    kwargs = dict(
        total_cost_column="ZFY", drug_cost_column="YPFY",
        cohort_columns={
            "day_surgery": "DAY", "elective_surgery": "ELECTIVE",
            "infusion": "INFUSION", "clinical_pathway": "PATH",
        },
    )
    calculator = HomepageIndicators(current, **kwargs)
    result = by_key(calculator.calculate())

    assert result["day_surgery_among_elective_rate"].value == 50
    assert result["infusion_reaction_rate"].value == 100
    assert result["clinical_pathway_rate"].value == pytest.approx(200 / 3)
    assert result["inpatient_cost_per_case"].value == 400

    growth = by_key(calculator.growth_from(HomepageIndicators(previous, **kwargs)))
    assert growth["inpatient_cost_growth_rate"].value == 100
    assert growth["inpatient_drug_cost_growth_rate"].value == 100


def test_complication_can_require_hospital_onset_secondary_diagnosis():
    data = sample()
    data["XY_RYBQ1"] = ["1", "4", ""]
    result = by_key(HomepageIndicators(
        data, complication_admission_conditions=["4"]
    ).calculate())

    assert result["postop_pulmonary_embolism_rate"].numerator == 0
    assert result["postop_wound_dehiscence_rate"].numerator == 1


def test_supplied_homepage_headers_are_used_automatically():
    data = sample().assign(
        CYKB=["心内科", "心内科", "内科"], SJZYTS=[5, 10, 3],
        QJCS=[0, 2, 1], QJCGCS=[0, 1, 1], SWHZSJ=["0", "1", "0"],
        SSLCLJ=["1", "0", "1"], SFJHZCRY=["0", "1", "0"],
        BAZL=["甲", "乙", "A"], ZFY=[100, 200, 300], XYF=[10, 40, 30],
        SSLX1=["择期", "择期", ""], SFRJSS1=["1", "0", ""],
        SJZY_TJHL=[0, 1, 0], SJZY_YJHL=[1, 2, 0],
        ZZJHSMC1=["", "CCU", ""], JRSJ1=["", "2026-02-01", ""],
        TCSJ1=["", "2026-02-03", ""], YCHXJSYSJ=[0, 24, 0],
        SXL_U1=[0, 2, 0], SXL_ML1=[0, 200, 0], SXFY=["0", "1", "0"],
        XSRTZ1=[0, 4100, 3000], XSRXB1=["", "男", "女"], CHCX=["0", "1", "0"],
    )
    result = by_key(HomepageIndicators(data).calculate())

    assert result["rescue_success_rate"].value == pytest.approx(200 / 3)
    assert result["clinical_pathway_rate"].value == pytest.approx(200 / 3)
    assert result["day_surgery_among_elective_rate"].value == 50
    assert result["icu_admission_rate"].value == pytest.approx(100 / 3)
    assert result["transfusion_reaction_rate"].value == 100
    assert result["grade_1_2_operation_transfusion_unit"].value == 2
    assert result["macrosomia_rate"].value == 50
    assert result["grade_a_medical_record_rate"].value == pytest.approx(200 / 3)
    assert result["xyf_expense_share"].value == pytest.approx(80 / 600 * 100)

    departments = HomepageIndicators(data).by_department()
    heart = departments.set_index("department").loc["心内科"]
    assert heart["discharges"] == 2
    assert heart["mortality_rate"] == 50
    assert heart["average_cost"] == 150


def test_44_specialty_catalog_and_availability_statuses():
    assert len(SPECIALTY_NAMES) == 44
    data = sample().assign(CYKB=["心血管内科", "心血管内科", "内科"])
    catalog = {
        "心血管内科": SpecialtyDefinition(
            name="心血管内科", department_values=("心血管内科",),
            key_diseases={"急性心肌梗死": ("I21",)},
            key_technologies={"冠状动脉介入": ("36.0",)},
        )
    }
    report = HomepageIndicators(data).specialty_summary(catalog)

    assert set(report["category"]) == {"重点病种", "关键技术"}
    assert report.set_index("item").loc["急性心肌梗死", "count"] == 1
    assert report.set_index("item").loc["冠状动脉介入", "count"] == 1

    availability = HomepageIndicators(data).indicator_catalog()
    assert set(availability["status"]) == {
        "可直接计算", "仅供复核", "需要字段", "无法由首页计算"
    }


def test_load_hospital_approved_specialty_catalog(tmp_path):
    path = tmp_path / "catalog.csv"
    pd.DataFrame([
        {"specialty": "心血管内科", "category": "重点病种", "item": "急性心肌梗死", "codes": "I21|I22", "department_values": "心内科|心血管内科"},
        {"specialty": "心血管内科", "category": "关键技术", "item": "PCI", "codes": "36.0", "department_values": "心内科|心血管内科"},
    ]).to_csv(path, index=False)

    catalog = load_specialty_catalog(path)
    assert catalog["心血管内科"].key_diseases["急性心肌梗死"] == ("I21", "I22")
    assert set(catalog["心血管内科"].department_values) == {"心内科", "心血管内科"}
