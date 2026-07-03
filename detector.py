# -*- coding: utf-8 -*-
"""真实 API 检测模式：LLM 调用 + JSON 解析 fallback + 重试"""

import json
import re
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from prompts.detection_prompt import SYSTEM_PROMPT, build_user_message
from utils import extract_json_from_text


MAX_RETRIES = 3
MAX_CONCURRENT = 8  # 最大并发数


def call_llm_api(api_key, api_url, model, system_prompt, user_message, timeout=60):
    """
    调用 LLM API（兼容 OpenAI 格式）。
    
    Args:
        api_key: API 密钥
        api_url: API 地址（如 https://api.openai.com/v1/chat/completions）
        model: 模型名称
        system_prompt: 系统提示词
        user_message: 用户消息
        timeout: 超时时间（秒）
    
    Returns:
        (success, content_or_error)
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.0,  # 关闭随机性，保证输出稳定
    }

    # DeepSeek 模型：通过 extra_body 关闭思考模式
    if "deepseek" in model.lower():
        payload["extra_body"] = {"thinking": {"type": "disabled"}}

    try:
        resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return True, content
    except requests.exceptions.Timeout:
        return False, "API 调用超时"
    except requests.exceptions.ConnectionError:
        return False, "无法连接到 API 服务器，请检查 API URL"
    except requests.exceptions.HTTPError as e:
        try:
            error_detail = resp.json()
            return False, f"API 返回错误 ({resp.status_code}): {error_detail}\n请求URL: {api_url}"
        except Exception:
            return False, f"API 返回错误 ({resp.status_code}): {resp.text[:300]}\n请求URL: {api_url}"
    except Exception as e:
        return False, f"API 调用异常: {str(e)}"


def parse_llm_response(raw_response):
    """
    解析 LLM 返回的 JSON，三层 fallback。
    
    Returns:
        (success, result_dict_or_error)
    """
    # 第1层：直接解析
    try:
        result = json.loads(raw_response.strip())
        return True, result
    except json.JSONDecodeError:
        pass

    # 第2层：正则提取 JSON 对象
    json_str = extract_json_from_text(raw_response)
    if json_str:
        try:
            result = json.loads(json_str)
            return True, result
        except json.JSONDecodeError:
            pass

    # 第3层：返回原始文本作为错误信息
    return False, f"JSON 解析失败，原始返回: {raw_response[:300]}"


def validate_result(result, reply_id):
    """
    校验解析后的结果是否包含必需字段，缺失则补默认值。
    """
    defaults = {
        "id": reply_id,
        "is_hallucination": False,
        "hallucination_type": None,
        "severity": None,
        "reason": "",
        "spans": [],
    }

    for key, default in defaults.items():
        if key not in result:
            result[key] = default

    # 确保 spans 是列表
    if not isinstance(result.get("spans"), list):
        result["spans"] = []

    return result


def detect_single(reply_item, api_config):
    """
    对单条回复执行 LLM 检测（含重试机制）。
    
    Args:
        reply_item: 单条回复数据
        api_config: {"api_key": str, "api_url": str, "model": str}
    
    Returns:
        检测结果 dict
    """
    user_message = build_user_message(reply_item)

    for attempt in range(1, MAX_RETRIES + 1):
        success, content = call_llm_api(
            api_key=api_config["api_key"],
            api_url=api_config["api_url"],
            model=api_config["model"],
            system_prompt=SYSTEM_PROMPT,
            user_message=user_message,
        )

        if not success:
            # API 调用失败，不重试（网络错误重试无意义）
            return {
                "id": reply_item["id"],
                "is_hallucination": None,
                "hallucination_type": None,
                "severity": None,
                "reason": f"API 调用失败 (尝试 {attempt}/{MAX_RETRIES}): {content}",
                "spans": [],
                "api_error": True,
            }

        parse_success, result = parse_llm_response(content)

        if parse_success:
            return validate_result(result, reply_item["id"])

        # JSON 解析失败，重试
        if attempt < MAX_RETRIES:
            continue

    # 所有重试都失败
    return {
        "id": reply_item["id"],
        "is_hallucination": None,
        "hallucination_type": None,
        "severity": None,
        "reason": f"JSON 解析失败，已重试 {MAX_RETRIES} 次",
        "spans": [],
        "api_error": True,
    }


def detect_all(replies, api_config, progress_callback=None):
    """
    对所有回复执行 LLM 检测（并发调用，大幅提速）。
    
    Args:
        replies: 回复数据列表
        api_config: API 配置
        progress_callback: 进度回调函数，签名为 callback(current, total)
    
    Returns:
        检测结果列表（保持原始顺序）
    """
    total = len(replies)
    results = [None] * total
    lock = threading.Lock()
    completed_count = [0]  # 用列表包装以便在闭包中修改

    def process_one(index, item):
        result = detect_single(item, api_config)
        with lock:
            results[index] = result
            completed_count[0] += 1
            if progress_callback:
                progress_callback(completed_count[0], total)

    # 并发数不超过数据总量
    workers = min(MAX_CONCURRENT, total)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(process_one, i, item): i
            for i, item in enumerate(replies)
        }
        for future in as_completed(futures):
            future.result()  # 捕获可能的异常

    return results