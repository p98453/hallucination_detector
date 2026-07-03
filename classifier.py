# -*- coding: utf-8 -*-
"""幻觉分类体系定义 + 严重程度判定 + ground_truth 映射"""

from enum import Enum


class HallucinationType(Enum):
    """幻觉类型枚举"""
    FACT_CONTRADICTION = "事实冲突"       # KB有明确事实，回复矛盾
    CAPABILITY_OVERREACH = "能力越界"     # KB否定能力，回复声称已执行
    UNSUPPORTED_ASSERTION = "无依据断言"  # KB沉默，回复肯定陈述
    SAFETY_MISLEADING = "安全误导"        # KB有安全警告，回复反向建议
    INFORMATION_OMISSION = "信息遗漏"     # 附加维度：回复不完整


class Severity(Enum):
    """严重程度枚举"""
    HIGH = "高危"
    MEDIUM = "中危"
    LOW = "低危"


# 检测工具类型 → ground_truth 类型的映射
TYPE_TO_GT_MAPPING = {
    HallucinationType.FACT_CONTRADICTION.value: [
        "参数编造", "信息编造", "优惠编造", "政策编造", "政策偏差"
    ],
    HallucinationType.CAPABILITY_OVERREACH.value: [
        "能力越界"
    ],
    HallucinationType.UNSUPPORTED_ASSERTION.value: [
        "信息编造"
    ],
    HallucinationType.SAFETY_MISLEADING.value: [
        "安全误导"
    ],
    HallucinationType.INFORMATION_OMISSION.value: [
        "信息遗漏"
    ],
}

# ground_truth 类型 → 检测工具类型的反向映射
GT_TO_TYPE_MAPPING = {}
for tool_type, gt_types in TYPE_TO_GT_MAPPING.items():
    for gt_type in gt_types:
        GT_TO_TYPE_MAPPING[gt_type] = tool_type


# 边界 case 优先级（数值越大优先级越高）
TYPE_PRIORITY = {
    HallucinationType.SAFETY_MISLEADING.value: 4,
    HallucinationType.CAPABILITY_OVERREACH.value: 3,
    HallucinationType.FACT_CONTRADICTION.value: 2,
    HallucinationType.UNSUPPORTED_ASSERTION.value: 1,
    HallucinationType.INFORMATION_OMISSION.value: 0,
}


def resolve_type(types):
    """当一条回复触发多个类型时，按优先级返回最高优先级的类型"""
    if not types:
        return None
    return max(types, key=lambda t: TYPE_PRIORITY.get(t, 0))


def classify_severity(hallucination_type, reply_text="", kb_text=""):
    """
    根据幻觉类型和内容判定严重程度。
    
    高危：安全误导、涉及金钱/退货政策的严重事实冲突
    中危：大部分事实冲突、能力越界、无依据断言
    低危：部分偏差、信息遗漏
    """
    if hallucination_type is None:
        return None

    if hallucination_type == HallucinationType.SAFETY_MISLEADING.value:
        return Severity.HIGH.value

    if hallucination_type == HallucinationType.INFORMATION_OMISSION.value:
        return Severity.LOW.value

    if hallucination_type == HallucinationType.FACT_CONTRADICTION.value:
        # 涉及金钱、退货、保修等关键词 → 高危
        high_risk_keywords = ["退", "钱", "费", "价", "优惠", "券", "保", "发票", "款"]
        combined = reply_text + kb_text
        if any(kw in combined for kw in high_risk_keywords):
            return Severity.HIGH.value
        return Severity.MEDIUM.value

    if hallucination_type == HallucinationType.CAPABILITY_OVERREACH.value:
        return Severity.MEDIUM.value

    if hallucination_type == HallucinationType.UNSUPPORTED_ASSERTION.value:
        return Severity.MEDIUM.value

    return Severity.MEDIUM.value


def map_to_gt_type(tool_type):
    """将检测工具类型映射到 ground_truth 类型列表"""
    return TYPE_TO_GT_MAPPING.get(tool_type, [])


def map_from_gt_type(gt_type):
    """将 ground_truth 类型映射到检测工具类型"""
    return GT_TO_TYPE_MAPPING.get(gt_type)