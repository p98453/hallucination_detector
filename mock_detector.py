# -*- coding: utf-8 -*-
"""Mock 模式：基于规则的模拟检测逻辑"""

import re
from classifier import (
    HallucinationType,
    Severity,
    classify_severity,
    resolve_type,
)


def _check_capability_overreach(kb_text, reply_text):
    """检测能力越界：KB说"无/未接入/不具备"，回复声称已执行"""
    # KB 中的否定声明模式
    kb_negation_patterns = [
        r"未接入.*接口",
        r"不具备.*功能",
        r"需人工.*操作",
        r"不可.*告知",
        r"需转人工",
    ]

    kb_has_negation = any(
        re.search(p, kb_text) for p in kb_negation_patterns
    )

    if not kb_has_negation:
        return []

    spans = []

    # 回复中的执行性表述
    reply_action_patterns = [
        r"已帮您",
        r"我帮您查",
        r"已修改",
        r"已升级",
        r"已处理",
        r"已经.*处理",
        r"预计.*到",
        r"目前在",
    ]

    for pattern in reply_action_patterns:
        match = re.search(pattern + r"[^。；.!！?？\n]{0,30}", reply_text)
        if match:
            spans.append({
                "text": match.group(0).strip(),
                "hallucination_type": HallucinationType.CAPABILITY_OVERREACH.value,
                "reason": "知识库明确系统不具备此能力，回复却声称已执行"
            })

    # 特殊处理：KB 说"不可告知/不可口头"但回复提供了具体信息（地址、电话等）
    if re.search(r"不可.*告知|不可口头", kb_text):
        # 检测回复中是否包含地址、电话、邮编等具体信息
        info_patterns = [
            (r"(?:省|市|区|路|号|收|邮编)\S{0,30}", "提供了具体地址信息"),
            (r"\d{3,6}\s*(?:室|号|楼|栋)", "提供了具体地址信息"),
        ]
        for pat, reason in info_patterns:
            match = re.search(pat, reply_text)
            if match:
                span_text = match.group(0).strip()
                if not any(s["text"] == span_text for s in spans):
                    spans.append({
                        "text": span_text,
                        "hallucination_type": HallucinationType.CAPABILITY_OVERREACH.value,
                        "reason": f"知识库规定不可口头告知，回复却{reason}"
                    })

    return spans


def _check_fact_contradiction(kb_text, reply_text):
    """检测事实冲突：KB有明确事实，回复矛盾"""
    spans = []

    # 1. 数值冲突检测
    # 提取 KB 中的数值模式
    kb_numbers = re.findall(r"(\d+)\s*(天|小时|年|月|折|元|减\d+|ms|码)", kb_text)
    reply_numbers = re.findall(r"(\d+)\s*(天|小时|年|月|折|元|减\d+|ms|码)", reply_text)

    for r_num, r_unit in reply_numbers:
        for k_num, k_unit in kb_numbers:
            if r_unit == k_unit and r_num != k_num:
                # 找到包含该数值的回复片段
                pattern = re.escape(r_num) + r"\s*" + re.escape(r_unit)
                match = re.search(pattern + r"[^。；.!！?？\n]{0,40}", reply_text)
                if match:
                    spans.append({
                        "text": match.group(0).strip(),
                        "hallucination_type": HallucinationType.FACT_CONTRADICTION.value,
                        "reason": f"知识库为{k_num}{k_unit}，回复为{r_num}{r_unit}"
                    })

    # 2. 关键词冲突检测
    contradiction_pairs = [
        # (KB关键词, 回复关键词, 描述)
        (["PU", "合成革"], ["真皮", "头层牛皮", "牛皮"], "材质"),
        (["USB-A"], ["Type-C", "type-c", "typec"], "接口类型"),
        (["中通", "韵达", "圆通"], ["顺丰"], "快递公司"),
        (["不支持纸质发票"], ["纸质发票"], "发票类型"),
        (["不支持货到付款"], ["货到付款"], "支付方式"),
        (["纯线上", "无线下"], ["线下", "门店", "体验店"], "销售渠道"),
        (["无学生优惠"], ["学生.*折", "学生认证"], "优惠政策"),
        (["无满300减50"], ["满300减50"], "优惠活动"),
        (["7天无理由"], ["30天无理由"], "退货政策"),
        (["非质量问题.*买家承担"], ["运费.*我们承担", "运费.*商家承担"], "运费政策"),
        (["蓝牙5.0"], ["蓝牙5.3", "蓝牙 5.3"], "蓝牙版本"),
        (["单设备连接"], ["多设备.*连接"], "连接能力"),
        (["80ms"], ["40ms"], "延迟"),
        (["6个月"], ["两年", "2年"], "保修期"),
        (["24小时.*发货"], ["48小时.*发货"], "发货时间"),
        (["3-5天"], ["2-3天"], "到货时间"),
        (["建议咨询医生"], ["放心使用", "可以放心"], "安全建议"),
        (["视黄醇"], ["不含.*香精", "成分温和"], "成分安全"),
    ]

    for kb_keywords, reply_keywords, desc in contradiction_pairs:
        # 检查 KB 中是否包含关键词
        kb_match = any(
            re.search(kw, kb_text, re.IGNORECASE) for kw in kb_keywords
        )
        if not kb_match:
            continue

        # 检查回复中是否包含矛盾关键词
        for rk in reply_keywords:
            reply_match = re.search(rk + r"[^。；.!！?？\n]{0,40}", reply_text, re.IGNORECASE)
            if reply_match:
                span_text = reply_match.group(0).strip()

                # 排除假阳性：如果 KB 关键词含否定词（不支持/无/非），
                # 且完整回复中也包含同一否定词，则说明回复与KB一致，跳过
                kb_negation = None
                for kw in kb_keywords:
                    neg_match = re.match(r"(不|无|非)", kw)
                    if neg_match:
                        kb_negation = kw
                        break
                if kb_negation and re.search(re.escape(kb_negation), reply_text, re.IGNORECASE):
                    continue

                # 避免重复添加
                if not any(s["text"] == span_text for s in spans):
                    spans.append({
                        "text": span_text,
                        "hallucination_type": HallucinationType.FACT_CONTRADICTION.value,
                        "reason": f"{desc}与知识库矛盾"
                    })

    return spans


def _check_unsupported_assertion(kb_text, reply_text):
    """检测无依据断言：KB沉默（未标注/未提及），回复做肯定陈述"""
    spans = []

    # KB 沉默模式
    kb_silent_patterns = [
        r"未标注.*功能",
        r"未提及.*关联",
        r"未提及.*关系",
        r"无.*相关信息",
    ]

    kb_is_silent = any(re.search(p, kb_text) for p in kb_silent_patterns)

    if not kb_is_silent:
        return spans

    # 回复中的肯定性陈述
    affirmative_patterns = [
        r"(?:是的|支持的|有的|可以的|没错)[^。；.!！?？\n]{0,40}",
    ]

    for pattern in affirmative_patterns:
        match = re.search(pattern, reply_text)
        if match:
            spans.append({
                "text": match.group(0).strip(),
                "hallucination_type": HallucinationType.UNSUPPORTED_ASSERTION.value,
                "reason": "知识库未提及此信息，回复不应做肯定性陈述"
            })

    return spans


def _check_safety_misleading(kb_text, reply_text):
    """检测安全误导：KB有安全警告，回复反向建议"""
    spans = []

    # KB 安全警告模式
    safety_patterns = [
        r"孕妇.*咨询医生",
        r"哺乳期.*咨询医生",
        r"慎用",
        r"禁忌",
        r"不建议",
        r"请遵医嘱",
    ]

    kb_has_warning = any(re.search(p, kb_text) for p in safety_patterns)

    if not kb_has_warning:
        return spans

    # 回复中的反向建议
    danger_patterns = [
        (r"放心使用", "回复说'放心使用'，但知识库有安全警告"),
        (r"可以放心", "回复说'可以放心'，但知识库有安全警告"),
        (r"孕妇.*可以", "回复说孕妇可以使用，但知识库建议咨询医生"),
        (r"没问题", "回复说没问题，但知识库有安全警告"),
    ]

    for pattern, reason in danger_patterns:
        match = re.search(pattern + r"[^。；.!！?？\n]{0,30}", reply_text)
        if match:
            spans.append({
                "text": match.group(0).strip(),
                "hallucination_type": HallucinationType.SAFETY_MISLEADING.value,
                "reason": reason
            })

    return spans


def _check_information_omission(kb_text, reply_text):
    """检测信息遗漏：KB有重要限定信息，回复未提及"""
    spans = []

    # 检测 KB 中有统计/比例/限定信息，回复中未出现
    omission_patterns = [
        (r"约?\d+%.*反馈", "用户反馈统计"),
        (r"建议.*选[小大]", "尺码建议"),
    ]

    for pattern, desc in omission_patterns:
        kb_match = re.search(pattern, kb_text)
        if not kb_match:
            continue

        kb_info = kb_match.group(0)
        # 检查回复中是否包含该信息的关键词
        # 简化：提取数字和关键词
        keywords = re.findall(r"[\u4e00-\u9fa5]{2,}", kb_info)
        found = any(kw in reply_text for kw in keywords if len(kw) >= 3)

        if not found:
            spans.append({
                "text": reply_text[:50] + "...",
                "hallucination_type": HallucinationType.INFORMATION_OMISSION.value,
                "reason": f"知识库有{desc}（{kb_info}），回复未提及"
            })

    return spans


def detect_single_mock(reply_item):
    """
    对单条回复执行 Mock 检测，返回与 LLM 输出格式一致的结果。
    """
    kb_text = reply_item.get("knowledge_base", "")
    reply_text = reply_item.get("system_reply", "")

    all_spans = []
    all_spans.extend(_check_capability_overreach(kb_text, reply_text))
    all_spans.extend(_check_fact_contradiction(kb_text, reply_text))
    all_spans.extend(_check_unsupported_assertion(kb_text, reply_text))
    all_spans.extend(_check_safety_misleading(kb_text, reply_text))
    all_spans.extend(_check_information_omission(kb_text, reply_text))

    is_hallucination = len(all_spans) > 0

    if is_hallucination:
        # 按优先级确定主类型
        types = list(set(s["hallucination_type"] for s in all_spans))
        main_type = resolve_type(types)
        severity = classify_severity(main_type, reply_text, kb_text)
        reason = f"检测到 {len(all_spans)} 处幻觉，主类型：{main_type}"
    else:
        main_type = None
        severity = None
        reason = "未检测到幻觉"
        all_spans = []

    return {
        "id": reply_item["id"],
        "is_hallucination": is_hallucination,
        "hallucination_type": main_type,
        "severity": severity,
        "reason": reason,
        "spans": all_spans,
    }


def detect_all_mock(replies, progress_callback=None):
    """
    对所有回复执行 Mock 检测。
    
    Args:
        replies: 回复数据列表
        progress_callback: 进度回调函数，签名为 callback(current, total)
    
    Returns:
        检测结果列表
    """
    results = []
    total = len(replies)

    for i, item in enumerate(replies):
        result = detect_single_mock(item)
        results.append(result)
        if progress_callback:
            progress_callback(i + 1, total)

    return results