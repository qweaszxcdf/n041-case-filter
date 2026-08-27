# n041-case-filter

面向病案首页导出原始扁平表的 N041 病例筛选、数据提取与基础计算工具。

项目提供“筛选病例 + 提取明细 + 通用计算”，并内置 2026 年上海市医院评审细则中可由住院病案首页直接、可靠重建的一组指标。调用方也可以组合筛选条件，再使用 count / sum / mean / rate 计算自己的指标。

## 评审细则病案首页指标

`HomepageIndicators` 一次计算首页能够支持的病种/术种数量、平均住院日、三四级手术比例、日间手术比例、住院/手术/新生儿死亡率、再入院与再次手术、住院费用，以及评审细则给出 ICD-10 编码的手术、分娩和其他并发症指标：

~~~python
from n041_filter import HomepageIndicators, SpecialtyDefinition, load_table

df = load_table("cases.csv", encoding="utf-8")
report = HomepageIndicators(
    df,
    discharge_method_column="LYFS",  # 国家首页“离院方式”，5=死亡
    stay_days_column="SJZYTS",       # 可省略；缺少时用 RYSJ/CYSJ 计算
    newborn_age_days_column="RYQNL", # 可选，提供后计算新生儿指标
    patient_id_column="SFZH",         # 可选，提供后计算31天再住院
    total_cost_column="ZFY",
    drug_cost_column="XYF",          # 需要“药品费用”口径时可自行合计中西药字段
    # 本地首页的布尔/标志字段；值默认识别 1/是/Y/YES/TRUE
    cohort_columns={
        "day_surgery": "RJSSBZ",
        "elective_surgery": "ZQSSBZ",
        "infusion": "SFBYSY",
        "transfusion": "SFSX",
        "fall": "SFDD",
        "hemodialysis": "SFXYTX",
        "hospital_infection": "YYGR",
        "incision_class_i": "YLQK",
        "incision_infection": "QKGR",
        "clinical_pathway": "LCLJ",
    },
    # 若首页的“入院病情”4 表示住院后发生，可避免把既往合并症
    # 错计成院内/术后并发症；不传则兼容缺少入院病情的导出表。
    complication_admission_conditions=["4"],
).to_frame()
report.to_excel("homepage_indicators.xlsx", index=False)

# 科室运行、死亡、手术、抢救、住院日和费用指标
department_report = HomepageIndicators(df).by_department("CYKB")

# 44 专科目录完整内置；评审附件没有发布 ICD 值集，因此应接入本院
# 审核后的编码目录，而不是按疾病名称做不可靠的模糊匹配。
specialty_report = HomepageIndicators(df).specialty_summary({
    "心血管内科": SpecialtyDefinition(
        name="心血管内科",
        department_values=("心血管内科", "心内科"),
        key_diseases={"急性心肌梗死": ("I21",)},
        key_technologies={"经皮冠状动脉介入治疗": ("36.0",)},
    )
})

# 统一查看可直接计算、需要字段、仅供复核和无法由首页计算的项目
availability = HomepageIndicators(df).indicator_catalog()
~~~

返回列为 `key / name / numerator / denominator / value / unit`。百分比的 `value` 已乘 100；分母为 0 时为 `None`。诊断并发症会检查所有诊断 slot；三四级手术比例复用 `CaseFilter.procedure()`，按病例数统计，并要求手术代码和切口愈合类别均非空。

阴道分娩和剖宫产的手术编码可能采用本地扩展，只有显式传入 `vaginal_delivery_codes` / `cesarean_codes` 时才计算对应指标。`cohort_columns` 用于对接各院首页扩展字段；没有相应字段的指标不会出现在结果中。再次手术和再住院先按首页日期计算候选值，正式上报时仍须结合“非计划/非预期”标志复核。

同比费用指标使用当前年度计算器调用 `growth_from(上一年度计算器)`。DRG/CMI、低风险组、导管留置天数、器官捐献和治疗过程等指标需要分组器、设备日或首页之外的数据，因此不会仅凭诊断代码猜测。可使用下文的 `Calculator` 与本院参数继续扩展。

针对本文所列的上海首页 header，以下字段会自动使用，无需 `cohort_columns`：`SFJHZCRY` 非计划再入院、`SSLCLJ` 临床路径、`QJCS/QJCGCS` 抢救、`SWHZSJ` 尸检、`SFJHSS1..20` 非计划再次手术、`SFRJSS1..20` 日间手术、`SSLX1..20` 手术类型、`BAZL` 病案质量、`ZZJHSMC/JRSJ/TCSJ1..5` ICU、`YCHXJSYSJ` 有创呼吸机、`SXL_U/SXL_ML1..6` 输血量、`SXFY` 输血反应、`XSRTZ/XSRXB1..5` 新生儿和 `CHCX` 产后出血。全部现有费用分项也会生成次均费用及占总费用比例。

`SPECIALTY_NAMES` 和 `empty_specialty_catalog()` 包含评审附件的全部 44 个专科。附件只给出重点病种/关键技术名称和例数要求，没有给出权威 ICD-10/ICD-9-CM-3 值集；`specialty_summary()` 因此要求传入医院审核后的 `SpecialtyDefinition` 编码映射。也可用 `load_specialty_catalog()` 读取 CSV/XLSX，列为 `specialty/category/item/codes/department_values`，多个编码或科室值用 `|` 分隔。空目录项目会明确输出“需要字段”，不会通过中文名称模糊匹配伪造统计结果。

## 适用范围

输入通常是病案首页导出的病例级扁平表，每一行代表一个病例。项目负责按首页字段筛选、提取和计算，不内置某一项评审指标的业务公式。

病案首页中的重复诊断、手术字段通过相同的数字后缀组成 slot，例如：

~~~text
诊断：XY_JBDM1、XY_ZYZD1、XY_RYBQ1、XY_CYQK1
手术：SSBM1_S、SSJCZRQ1、SSJB1、SSMC1
~~~

默认手术 `slot 1` 是 principal；字段名不同或首页展开方式不同，可以通过自定义 schema 调整。

## 数据安全

examples/sample.csv 和 examples/procedure_params.csv 是合成数据。真实病例、参数表和筛选明细通常包含病案号、姓名、证件号等敏感信息：

- 不要把真实源文件、临时文件或筛选明细提交到仓库。
- 建议把真实数据放在 private-data/ 等受控目录，该目录已加入 .gitignore。
- 对外提供明细前，删除不必要的身份字段并限制访问权限。

## 安装

~~~bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
~~~

可选依赖：

~~~bash
pip install -e '.[xls]'  # 读取 .xls
pip install -e '.[dbf]'  # 读取 DBF
pip install -e '.[all]'  # 安装全部可选依赖
~~~

## 运行和修改示例

仓库示例使用合成 CSV，可直接运行：

~~~bash
python examples/example.py
~~~

examples/example.py 也是推荐模板。需要新指标或新筛选时，直接复制并修改输入路径、筛选链、分子/分母条件和输出逻辑即可。

示例会输出计算摘要，并将完整分母明细写入 examples/denominator_cases.xlsx；第一列 is_numerator 标记分子病例。

## 输入文件

病案首页字段应尽量保留原始表头，尤其是诊断、手术、手术日期、入院日期和出院日期字段，便于默认 schema 自动发现和同槽绑定。

load_table() 支持 CSV、XLSX、XLS 和 DBF，并保持原始扁平列名。CSV/Excel 中的字段按字符串读取，空单元格保持为 `""`，适合保留代码前导零和空值语义：

~~~python
from n041_filter import load_table

df = load_table("cases.csv", encoding="utf-8")
~~~

默认 CSV 编码为 gbk；CSV 若使用 UTF-8，请显式传 encoding="utf-8"。

DBF 默认使用严格字符解码；如果明确接受坏字节被忽略，可传 `errors="ignore"`。`CaseFilter` 要求输入 `DataFrame.index` 唯一；如果数据拼接后产生重复索引，请先调用 `reset_index(drop=True)`。

## 快速开始

~~~python
from n041_filter import CaseFilter, load_table

df = load_table("cases.csv", encoding="utf-8")

cases = (
    CaseFilter(df)
    .diagnosis(
        "I21",
        principal=True,
        admission_condition=["1", "2"],
    )
    .procedure(["36.0"], level="4")
    .where("CYKB", ["a", "b"])
    .discharged_between("2025-01-01", "2025-12-31")
)

print(cases.count())
result = cases.result()
~~~

## 可用 filter

所有 filter 都返回新的 CaseFilter，可以继续链式调用：

- 链式调用之间是 AND。
- 同一次调用传入列表时，列表中的值是 OR。
- 诊断/手术会遍历所有 slot，slot 之间是 OR；同一次调用中的代码、名称、日期和其他属性必须来自同一 slot。
- 普通字段 filter 只做值匹配，不解析 SQL 或正则表达式。
- 诊断和手术代码使用 startswith()；普通字段 where() 使用规范化后的精确值。

| filter | 作用和参数 |
| --- | --- |
| diagnosis(codes, principal=None, name=None, name_contains=None, admission_condition=None, discharge_condition=None) | 按诊断代码及同槽属性筛选。 |
| without_diagnosis(codes, **criteria) | 排除命中诊断条件的病例；条件与 diagnosis 相同。 |
| procedure(codes, principal=None, name=None, name_contains=None, level=None, incision_healing=None, unplanned=None, day_surgery=None, operation_type=None, date_start=None, date_end=None, date_diff_hours=None, params=None) | 按手术代码及同槽属性筛选；`incision_healing`、`unplanned`、`day_surgery`、`operation_type` 均支持 `any` 表示非空；`date_diff_hours` 按日期排序后比较相邻候选手术。 |
| without_procedure(codes, **criteria) | 排除命中手术条件的病例；条件与 procedure 相同。 |
| where(column, values) / exclude(column, values) | 普通字段精确匹配或排除；values 可为单值或列表。 |
| filter(predicate) | 接收当前完整 `DataFrame`，返回按 index 对齐的布尔 mask。 |
| contains(column, values) / not_contains(column, values) | 普通字段包含或排除文本；不区分大小写。 |
| numeric_between(column, start=None, end=None) | 包含边界的数值范围；支持带千分位的费用文本。 |
| present(column) / missing(column) | 非空或空值筛选；空字符串、空白和缺失值视为无值。 |
| where_any(columns, values, *, codes=False, contains=False) | 多个字段任一命中；codes=True 使用代码前缀，contains=True 使用文本包含。 |
| between(column, *, start=None, end=None) | 任意日期列范围，边界包含。 |
| admitted_between(start=None, end=None, column="RYSJ") | 入院日期范围。 |
| discharged_between(start=None, end=None, column="CYSJ") | 出院日期范围。 |

例如，where("CYKB", ["a", "b"]) 有效，表示 CYKB 等于 a 或 b：

~~~python
cases = (
    CaseFilter(df)
    .where("CYKB", ["a", "b"])
    .contains("BRLY", "急诊")
    .numeric_between("ZFY", 10000, 50000)
)
~~~

### 自定义筛选

`filter()` 的 predicate 接收当前完整 `DataFrame`，返回按 index 对齐的布尔 mask。适合比较两栏、组合复杂条件或使用暂未内置的判断：

~~~python
import pandas as pd

def stay_within_30_days(data):
    admitted = pd.to_datetime(data["RYSJ"], format="mixed", errors="coerce")
    discharged = pd.to_datetime(data["CYSJ"], format="mixed", errors="coerce")
    hours = (discharged - admitted).dt.total_seconds() / 3600
    return hours.between(0, 720, inclusive="both")

cases = CaseFilter(df).filter(stay_within_30_days)
~~~

自定义筛选可以继续链式调用，也可以用于 `Calculator` 的分子或分母 selector：

~~~python
result = calc.rate(
    denominator=lambda c: c.filter(stay_within_30_days),
    numerator=lambda c: c.procedure(level="4"),
)
~~~

DataFrame predicate 应使用向量化表达式；大表上的常见条件仍应优先使用内置 filter。

## slot 规则与 schema

### 当前默认 slot

同一 slot 的字段必须使用相同的数字后缀：

~~~text
诊断：XY_JBDM1 <-> XY_RYBQ1 <-> XY_CYQK1
手术：SSBM1_S <-> SSJCZRQ1 <-> SSJB1 <-> SSMC1
~~~

默认 schema 的核心映射：

~~~python
# diagnosis:
# code=XY_JBDM / XY_JBDM(?P<slot>\d+)
# admission_condition=XY_RYBQ / XY_RYBQ(?P<slot>\d+)
# discharge_condition=XY_CYQK / XY_CYQK(?P<slot>\d+)

# procedure:
# code=SSBM(?P<slot>\d+)_S
# date=SSJCZRQ(?P<slot>\d+)
# level=SSJB(?P<slot>\d+)
# name=(SSJCZMC|SSMC)(?P<slot>\d+)
~~~

手术默认 principal_slots=("1",)，所以 principal=True 默认只筛 slot 1。用 cases.slots() 查看实际发现和绑定结果：

~~~python
cases = CaseFilter(df)
print(cases.slots())
~~~

### 后续新增 slot

如果只是新增同类 slot 的序号，且字段名仍符合正则，不需要改代码。例如下面字段会自动发现为手术 slot 21：

~~~text
SSBM21_S
SSJCZRQ21
SSJB21
SSMC21
~~~

若需要将 slot 21 也视为主要手术，在自定义 schema 中设置：

~~~python
principal_slots=("1", "21")
~~~

### 新增字段或更换字段名

先修改对应 SlotSchema。每个重复属性都必须使用 (?P<slot>...)，否则不能保证同槽匹配：

~~~python
from n041_filter import CaseFilter
from n041_filter.schema import DEFAULT_SCHEMA, SlotSchema

schema = {
    "diagnosis": DEFAULT_SCHEMA["diagnosis"],
    "procedure": SlotSchema(
        repeated={
            "code": r"^OP_CODE_(?P<slot>\d+)$",
            "name": r"^OP_NAME_(?P<slot>\d+)$",
            "date": r"^OP_DATE_(?P<slot>\d+)$",
            "level": r"^OP_LEVEL_(?P<slot>\d+)$",
        },
        principal_slots=("1",),
    ),
}

cases = CaseFilter(df, schema=schema)
~~~

slot 属性与现有 filter 的对应关系：

| schema 属性 | filter 参数 |
| --- | --- |
| code | codes |
| name | name / name_contains |
| admission_condition | admission_condition |
| discharge_condition | discharge_condition |
| date | date_start / date_end / date_diff_hours |
| level | level |
| incision_healing | incision_healing（切口愈合类别 QKYHLB） |
| unplanned | 首页非计划手术标志（SFJHSS） |
| day_surgery | 首页日间手术标志（SFRJSS） |
| operation_type | 首页手术类型（SSLX） |
| principal | principal |

`procedure()` 默认按任一 procedure slot 匹配。`date_start` / `date_end` 是绝对日期；`date_diff_hours` 会先筛选满足其他手术条件的 slot，再按手术日期升序排列，只比较相邻候选手术的时间差：

`incision_healing=any` 表示当前手术 slot 的 `QKYHLB` 有值；空字符串、空白和缺失值不匹配，数值或字符串 `"0"` 仍属于非空值。

~~~python
# 相邻的满足 codes 条件的手术，时间差不超过 48 小时
two_days = CaseFilter(df).procedure("36.", date_diff_hours=48)

# 相邻的满足 codes 条件的手术，相差 24-720 小时（1-30 天）
thirty_days = CaseFilter(df).procedure("36.", date_diff_hours=(24, 720))
~~~

`date_diff_hours` 的单位是小时。传入单个整数 `N` 表示时间差 `0 <= diff <= N`；传入 `(start, end)` 表示闭区间，精确值可写为 `(N, N)`。时间差按排序后的相邻日期计算，区间两端均包含；日期列包含时分秒时会保留到实际时间计算。与 `codes`、`level`、`name`、`unplanned`、`day_surgery`、`operation_type`、`params` 一起使用时，这些条件绑定在参与比较的候选手术 slot 上。`without_procedure(..., date_diff_hours=...)` 也支持同样的条件。

日期范围的纯日期 `end`（例如 `"2025-12-31"`）包含该日期的整天；如果传入带时间的值，则按精确时间作为上界。

只在 schema 中增加一个没有对应参数的属性，它只会出现在 cases.slots() 中，不会自动成为 filter。同一 slot 的同一 repeated 属性如果匹配多个列，会抛出 `ValueError`，不会按输入列顺序静默选择。

### 新增对应 filter

如果评审规则要求新增属性与代码严格同槽：

1. 在 schema.py 增加属性 pattern。
2. 在 filters.py 的对应 *_mask() 增加参数，并在 for slot in slots 内合并条件。
3. 在 engine.py 的公共方法增加并传递同名参数。
4. 检查 without_... 是否通过 **criteria 自动复用。
5. 增加正向、排除、跨 slot 防误匹配验证，并更新本节映射。

不要先用 where("OPERATOR1", ...) 再筛手术代码；这种写法不能保证两个字段属于同一 slot。

如果要新增全新的逻辑类型（例如 implant()），仅向 schema 增加 key 不够，还需要扩展 CaseFilter 的 slot 发现、mask、公共方法和计算示例。普通非 slot 字段则直接使用 where、contains、numeric_between 或 where_any。

## 外部手术参数表

手术参数可用 CSV、XLS 或 XLSX 维护，默认推荐 CSV：

~~~csv
code,minimally_invasive,level4,category
36.,true,,PCI
36.01,,true,PCI
88.56,false,,diagnostic
~~~

规则：

- code 必填，代码按 startswith() 匹配。
- 其他非空列是额外参数，CSV 中 true/false 自动转换为布尔值。
- 多条规则按顺序匹配，后面的同名参数覆盖前面的值。
- 参数始终绑定当前手术 slot，不会拿同一病例另一个手术的参数误配。
- 读取 .xls 需要安装 xlrd。

~~~python
cases = CaseFilter(
    df,
    procedure_params="procedure_params.csv",
)

level4_cases = cases.procedure(
    params={"level4": True},
)
~~~

也可以按顺序叠加多个参数文件：

~~~python
cases = CaseFilter(
    df,
    procedure_params=[
        "procedure_base.csv",
        "procedure_override.xlsx",
    ],
)
~~~

## 通用计算

~~~python
from n041_filter import Calculator

calc = Calculator(
    df,
    procedure_params="procedure_params.csv",
)

count = calc.count(lambda c: c.diagnosis("I21"))
total_cost = calc.sum("ZFY", lambda c: c.diagnosis("I21"))
average_cost = calc.mean("ZFY", lambda c: c.diagnosis("I21"))
~~~

`sum()` 和 `mean()` 与 `numeric_between()` 使用相同的数值解析规则，费用文本中的英文千分位逗号会被正确处理。

分子筛选会应用在分母病例集上：

~~~python
result = calc.rate(
    denominator=lambda c: c.procedure(),
    numerator=lambda c: c.procedure(level="4"),
    name="示例手术占比",
    keep_cases=True,
)

print(result.numerator)
print(result.denominator)
print(result.value)
~~~

输出完整分母并在第一列标记分子：

~~~python
details = result.denominator_cases.copy()
details.insert(
    0,
    "is_numerator",
    details.index.isin(result.numerator_cases.index),
)
details.to_excel(
    "denominator_cases.xlsx",
    index=False,
)
~~~

分母为 0 时 result.value 为 None；使用 scale=1 可返回比例而不是百分比。

## License

MIT License，详见 [LICENSE](LICENSE)。
