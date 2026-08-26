from pathlib import Path

import pandas as pd

from n041_filter import Calculator, load_table


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "output" / "sample_metrics.csv"

df = load_table(HERE / "sample.csv", encoding="utf-8")
procedure_params = HERE / "procedure_params.csv"
calc = Calculator(df, procedure_params=procedure_params)


def surgery_cases(cases):
    return cases.procedure(incision_healing=any)


def advanced_surgery_cases(cases):
    return cases.procedure(
        level=[3, 4],
        incision_healing=any,
    )


rows = [
    {
        "metric": "切口愈合类别非空病例数",
        "value": calc.count(surgery_cases),
    },
    {
        "metric": "三四级手术病例数",
        "value": calc.count(advanced_surgery_cases),
    },
    {
        "metric": "切口愈合类别非空手术总费用",
        "value": calc.sum("ZFY", surgery_cases),
    },
    {
        "metric": "切口愈合类别非空手术平均费用",
        "value": calc.mean("ZFY", surgery_cases),
    },
]

rate = calc.rate(
    denominator=surgery_cases,
    numerator=advanced_surgery_cases,
    name="三四级手术占切口愈合类别非空手术比例",
)
rate_data = rate.to_dict()
rows.append(
    {
        "metric": rate_data["name"],
        "value": rate_data["value"],
        "numerator": rate_data["numerator"],
        "denominator": rate_data["denominator"],
        "scale": rate_data["scale"],
    }
)

result = pd.DataFrame(rows)
OUTPUT.parent.mkdir(exist_ok=True)
result.to_csv(OUTPUT, index=False, encoding="utf-8-sig")
print(result.to_string(index=False))
print(f"\n已保存：{OUTPUT}")
