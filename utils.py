# -*- coding: utf-8 -*-
"""工具函数：文件读写、JSON校验"""

import json
import os
import re


REQUIRED_FIELDS = ["id", "user_question", "system_reply", "knowledge_base"]


def load_json(filepath):
    """加载 JSON 文件，返回 (data, error_msg)"""
    if not os.path.exists(filepath):
        return None, f"文件不存在: {filepath}"
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data, None
    except json.JSONDecodeError as e:
        return None, f"JSON 解析失败: {e}"
    except Exception as e:
        return None, f"读取文件失败: {e}"


def validate_replies(data):
    """校验 replies 数据格式，返回 (valid, error_msg)"""
    if not isinstance(data, list):
        return False, "数据格式错误：顶层应为数组"
    if len(data) == 0:
        return False, "数据为空数组"

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            return False, f"第 {i+1} 条数据格式错误：应为对象"
        for field in REQUIRED_FIELDS:
            if field not in item:
                return False, f"第 {i+1} 条数据缺少必需字段: {field}"
            if not isinstance(item[field], str):
                return False, f"第 {i+1} 条数据字段 {field} 应为字符串"

    return True, None


def validate_ground_truth(data):
    """校验 ground_truth 数据格式，返回 (valid, error_msg)"""
    if not isinstance(data, list):
        return False, "ground_truth 格式错误：顶层应为数组"
    if len(data) == 0:
        return False, "ground_truth 为空数组"

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            return False, f"ground_truth 第 {i+1} 条格式错误：应为对象"
        if "id" not in item:
            return False, f"ground_truth 第 {i+1} 条缺少 id 字段"
        if "is_hallucination" not in item:
            return False, f"ground_truth 第 {i+1} 条缺少 is_hallucination 字段"

    return True, None


def save_json(filepath, data):
    """保存 JSON 文件"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def extract_json_from_text(text):
    """从 LLM 返回文本中提取 JSON 对象（多层 fallback 的第2层）"""
    # 去除 markdown 代码块标记
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = text.strip()

    # 尝试找到第一个完整的 JSON 对象
    brace_start = text.find("{")
    if brace_start == -1:
        return None

    # 从第一个 { 开始，匹配到对应的 }
    depth = 0
    for i in range(brace_start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[brace_start : i + 1]

    return None


def get_exe_dir():
    """获取 exe 所在目录（兼容开发环境和打包后环境）"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


# 需要 sys 模块的延迟导入
import sys