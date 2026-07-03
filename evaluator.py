# -*- coding: utf-8 -*-
"""评估模块：混淆矩阵、指标计算、误判明细"""

from classifier import map_from_gt_type


def calculate_metrics(predictions, ground_truth):
    """
    计算检出率指标。
    
    Args:
        predictions: 检测结果列表，每项含 id, is_hallucination
        ground_truth: 人工标注列表，每项含 id, is_hallucination
    
    Returns:
        metrics dict
    """
    # 建立 ground_truth 索引
    gt_map = {item["id"]: item for item in ground_truth}

    tp = 0  # 预测幻觉，实际幻觉
    fp = 0  # 预测幻觉，实际无幻觉
    tn = 0  # 预测无幻觉，实际无幻觉
    fn = 0  # 预测无幻觉，实际幻觉

    false_positives = []
    false_negatives = []

    # 按类型统计
    type_stats = {}  # {gt_type: {"total": n, "detected": n}}

    for pred in predictions:
        pid = pred["id"]
        gt = gt_map.get(pid)

        if gt is None:
            continue

        pred_h = pred.get("is_hallucination")
        gt_h = gt.get("is_hallucination")

        # 跳过 API 错误导致的 None
        if pred_h is None:
            continue

        if pred_h and gt_h:
            tp += 1
        elif pred_h and not gt_h:
            fp += 1
            false_positives.append({
                "id": pid,
                "predicted": pred.get("hallucination_type", "未知"),
                "actual": "无幻觉",
                "reason": pred.get("reason", ""),
            })
        elif not pred_h and not gt_h:
            tn += 1
        elif not pred_h and gt_h:
            fn += 1
            false_negatives.append({
                "id": pid,
                "predicted": "无幻觉",
                "actual": gt.get("hallucination_type", "未知"),
                "reason": pred.get("reason", ""),
            })

        # 按类型统计
        if gt_h:
            gt_type = gt.get("hallucination_type", "未知")
            if gt_type not in type_stats:
                type_stats[gt_type] = {"total": 0, "detected": 0}
            type_stats[gt_type]["total"] += 1
            if pred_h:
                type_stats[gt_type]["detected"] += 1

    total = tp + fp + tn + fn
    accuracy = (tp + tn) / total if total > 0 else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    # 计算各类型召回率
    by_type = {}
    for gt_type, stats in type_stats.items():
        by_type[gt_type] = {
            "total": stats["total"],
            "detected": stats["detected"],
            "recall": stats["detected"] / stats["total"] if stats["total"] > 0 else 0,
        }

    return {
        "summary": {
            "total": total,
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        },
        "by_type": by_type,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
    }


def generate_report(predictions, ground_truth, mode="mock"):
    """
    生成完整的评估报告。
    
    Args:
        predictions: 检测结果列表
        ground_truth: 人工标注列表
        mode: 检测模式 ("mock" 或 "api")
    
    Returns:
        评估报告 dict
    """
    metrics = calculate_metrics(predictions, ground_truth)

    report = {
        "mode": mode,
        "summary": metrics["summary"],
        "by_type": metrics["by_type"],
        "false_positives": metrics["false_positives"],
        "false_negatives": metrics["false_negatives"],
    }

    if mode == "mock":
        report["warning"] = "⚠ 本结果由 Mock 模式生成，检出率不代表真实检测能力，仅供流程演示。"

    return report