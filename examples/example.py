from pathlib import Path

from n041_filter import Calculator, CaseFilter, load_table

HERE = Path(__file__).resolve().parent

df = load_table(HERE / "sample.csv", encoding="utf-8")

PROCEDURE_PARAMS = HERE / "procedure_params.csv"
# Excel 也可以直接使用 procedure_params.xlsx 或 procedure_params.xls。

# 仍然可以只筛病例。
cases = (
    CaseFilter(df, procedure_params=PROCEDURE_PARAMS)
    # .diagnosis(["K40", "K41"], principal=True)
    .procedure(level=4)
    # .procedure(date_diff_hours=(24, 48))  # 相邻候选手术之间相差 1-2 天
    # .discharged_between("2025-01-01", "2025-12-31")
)
# print(cases.result())
# cases.result().to_csv(HERE / "cases.csv", index=False, encoding="utf-8-sig")

# 通用计算：分子在分母病例集上继续筛选。
calc = Calculator(df, procedure_params=PROCEDURE_PARAMS)
result = calc.rate(
    denominator=lambda c: c.procedure(),
    numerator=lambda c: c.procedure(level=4),
    name="example_rate",
    keep_cases=True,
)
print(result.to_dict())

# 输出完整分母病例，并在第一列标记属于分子的病例。
denominator_details = result.denominator_cases.copy()
denominator_details.insert(
    0,
    "is_numerator",
    denominator_details.index.isin(result.numerator_cases.index),
)
denominator_details.to_excel(
    HERE / "denominator_cases.xlsx",
    index=False,
)
# print(denominator_details)
