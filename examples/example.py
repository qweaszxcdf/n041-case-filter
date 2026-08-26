from pathlib import Path

from n041_filter import Calculator, CaseFilter, load_table

HERE = Path(__file__).resolve().parent

df = load_table(HERE / "sample.csv", encoding="utf-8")

PROCEDURE_PARAMS = HERE / "procedure_params.csv"
# Excel 也可以直接使用 procedure_params.xlsx 或 procedure_params.xls。
手术科室列表 = ["04.01","04"]
# 仍然可以只筛病例。
cases = (
    CaseFilter(df, procedure_params=PROCEDURE_PARAMS)
    # .diagnosis(["K40", "K41"], principal=True)
    .procedure(incision_healing=any)
    .procedure("51.1100")
    .procedure("51.23")
    # .procedure(date_diff_hours=(24, 48))  # 相邻候选手术之间相差 1-2 天
    # .discharged_between("2025-01-01", "2025-12-31")
)
# print(cases.result())
# cases.result().to_csv(HERE / "cases.csv", index=False, encoding="utf-8-sig")

# 通用计算：分子在分母病例集上继续筛选。
calc = Calculator(df, procedure_params=PROCEDURE_PARAMS)
result = calc.rate(
    denominator=lambda c: c.procedure(incision_healing=any)#.contains("CYKB",手术科室列表),
    numerator=lambda c: c.procedure(level=[3,4],incision_healing=any),
    name="三四级手术占比",
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
# denominator_details.to_excel(
#     HERE / "denominator_cases.xlsx",
#     index=False,
# )
denominator_details.to_csv(
    HERE / "denominator_cases.csv",
    index=False,
    encoding="utf-8-sig",
)
# print(denominator_details)
# import pandas as pd; pd.read_excel("examples/202601---HN041_崇明县中心医院.xls").to_csv("examples/sample.csv", index=False, encoding="utf-8-sig")