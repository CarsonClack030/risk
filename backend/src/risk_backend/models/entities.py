from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

# 统一的零值常量。
# 因为项目里大量使用 Decimal，如果到处手写 Decimal("0") 会非常啰嗦，
# 也不利于阅读公式。
ZERO = Decimal("0")


def to_decimal(value: Any, default: Decimal = ZERO) -> Decimal:
    """把任意输入尽量稳妥地转成 Decimal。

    这个函数存在的原因是：
    1. 数据库读出来的可能是字符串、数字或者 None。
    2. 前端传回来的表单值通常是字符串。
    3. 风险计算里不希望因为一次类型转换失败就直接崩溃。

    因此这里采用“尽量转换，失败则回退默认值”的策略。
    """
    if value in (None, "", "None"):
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


@dataclass
class Pollutant:
    """污染物基础属性模型。

    可以把它理解成 `db_pol` 表在 Python 里的对象版本。
    一个污染物对象只描述“这个污染物是什么”，不描述“本次场地里的浓度是多少”。
    """

    id: int
    name: str
    english_name: str
    henry: Decimal
    da: Decimal
    dw: Decimal
    koc: Decimal
    solubility: Decimal
    sfo: Decimal
    iur: Decimal
    rfdo: Decimal
    rfc: Decimal
    absgi: Decimal
    absd: Decimal
    saf: Decimal
    kp: Decimal


@dataclass
class PollutantConcentration:
    """某条工作区记录对应的浓度信息。

    这里的 workspace_number 很重要：
    同一个污染物现在允许被加入多次，因此不能仅靠 pollutant_id 区分一条记录，
    需要靠工作区序号来唯一标识“本次计算里的这一行”。
    """

    workspace_number: int
    pollutant_id: int
    name: str
    english_name: str
    surface_concentration: Decimal
    lower_soil_concentration: Decimal
    groundwater_concentration: Decimal
    groundwater_protection_concentration: Decimal


@dataclass
class SelectedPollutant:
    """工作区里的完整污染物条目。

    这是前端最常使用的聚合模型：
    - pollutant：污染物本身的理化参数
    - concentration：本次场地评估里填写的浓度
    """

    workspace_number: int
    pollutant: Pollutant
    concentration: PollutantConcentration


@dataclass
class ParameterRow:
    """参数表中的一行。

    unit 是只读展示元数据，四组标准值共享同一单位；保存参数时只更新数值，
    不会把单位写进运行数据库。
    """

    name: str
    label: str
    unit: str
    data_gi: Decimal
    data_gii: Decimal
    data_zi: Decimal
    data_zii: Decimal
    group_id: int


@dataclass
class SiteSelection:
    """用户在界面上选择的场地条件。"""

    standard: str
    area_type: str

    @property
    def db_column(self) -> str:
        # 参数表里四类列名是固定命名模式：
        # data_gi / data_gii / data_zi / data_zii
        # 所以这里直接拼接出当前应该读取哪一列。
        if self.standard not in {"G", "Z"}:
            raise ValueError("适用标准只能选择 G 或 Z")
        if self.area_type not in {"I", "II"}:
            raise ValueError("用地类型只能选择 I 或 II")
        return f"data_{self.standard}{self.area_type}"


class AttributeMap:
    """把参数字典包装成“点号访问”对象。

    原始参数读取出来后是 dict，例如 values["BWa"]。
    在大段公式里如果一直写字典下标，代码会很难读。
    包装成 AttributeMap 后，就可以写成 par.BWa，更接近原始公式符号。
    """

    def __init__(self, values: dict[str, Any]):
        self._values = values

    def __getattr__(self, item: str) -> Any:
        try:
            return self._values[item]
        except KeyError as exc:
            raise AttributeError(item) from exc
