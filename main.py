# -*- coding: utf-8 -*-
"""GUI 主界面：Tkinter 实现"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import load_json, validate_replies, validate_ground_truth, save_json
from mock_detector import detect_all_mock
from detector import detect_all
from evaluator import generate_report


class HallucinationDetectorApp:
    """客服回复幻觉检测工具 GUI"""

    def __init__(self, root):
        self.root = root
        self.root.title("客服回复幻觉检测工具")
        self.root.geometry("800x700")
        self.root.resizable(True, True)

        # 数据状态
        self.replies_data = None
        self.ground_truth_data = None
        self.detection_results = None
        self.evaluation_report = None
        self.is_running = False

        self._build_ui()

    # ==================== UI 构建 ====================

    def _build_ui(self):
        """构建界面"""
        # 主容器
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        title_label = ttk.Label(
            main_frame,
            text="客服回复幻觉检测工具",
            font=("Microsoft YaHei", 16, "bold"),
        )
        title_label.pack(pady=(0, 15))

        # === 文件选择区 ===
        file_frame = ttk.LabelFrame(main_frame, text="文件选择", padding="10")
        file_frame.pack(fill=tk.X, pady=(0, 10))

        # 输入文件
        ttk.Label(file_frame, text="输入文件 (必需):").grid(
            row=0, column=0, sticky=tk.W, pady=5
        )
        self.input_file_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.input_file_var, width=60).grid(
            row=0, column=1, padx=5, pady=5
        )
        ttk.Button(file_frame, text="选择文件", command=self._select_input_file).grid(
            row=0, column=2, pady=5
        )

        # Ground Truth 文件（可选）
        ttk.Label(file_frame, text="GT文件 (可选):").grid(
            row=1, column=0, sticky=tk.W, pady=5
        )
        self.gt_file_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.gt_file_var, width=60).grid(
            row=1, column=1, padx=5, pady=5
        )
        ttk.Button(file_frame, text="选择文件", command=self._select_gt_file).grid(
            row=1, column=2, pady=5
        )

        # === 检测模式区 ===
        mode_frame = ttk.LabelFrame(main_frame, text="检测模式", padding="10")
        mode_frame.pack(fill=tk.X, pady=(0, 10))

        self.mode_var = tk.StringVar(value="mock")
        ttk.Radiobutton(
            mode_frame, text="Mock 模式（演示流程，零成本）",
            variable=self.mode_var, value="mock",
            command=self._on_mode_change,
        ).grid(row=0, column=0, sticky=tk.W, padx=(0, 30))
        ttk.Radiobutton(
            mode_frame, text="真实 API 模式（需填写 API 配置）",
            variable=self.mode_var, value="api",
            command=self._on_mode_change,
        ).grid(row=0, column=1, sticky=tk.W)

        # === API 配置区（默认隐藏） ===
        self.api_frame = ttk.LabelFrame(main_frame, text="API 配置（DeepSeek）", padding="10")

        ttk.Label(
            self.api_frame,
            text="使用 DeepSeek 官方 API，请到 https://platform.deepseek.com 申请 API Key",
            foreground="gray",
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        ttk.Label(self.api_frame, text="API Key:").grid(
            row=1, column=0, sticky=tk.W, pady=3
        )
        self.api_key_var = tk.StringVar()
        ttk.Entry(
            self.api_frame, textvariable=self.api_key_var, width=60, show="*"
        ).grid(row=1, column=1, padx=5, pady=3, sticky=tk.W)

        ttk.Label(self.api_frame, text="模型:").grid(
            row=2, column=0, sticky=tk.W, pady=3
        )
        self.model_var = tk.StringVar(value="deepseek-v4-flash")
        model_combo = ttk.Combobox(
            self.api_frame, textvariable=self.model_var,
            values=["deepseek-v4-flash", "deepseek-v4-pro"],
            state="readonly", width=30,
        )
        model_combo.grid(row=2, column=1, padx=5, pady=3, sticky=tk.W)

        ttk.Label(
            self.api_frame,
            text="API: https://api.deepseek.com/v1/chat/completions",
            foreground="gray",
        ).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))

        # === 操作按钮区 ===
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(5, 10))

        self.start_btn = ttk.Button(
            btn_frame, text="开始检测", command=self._start_detection
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.export_result_btn = ttk.Button(
            btn_frame, text="导出检测结果",
            command=self._export_result, state=tk.DISABLED,
        )
        self.export_result_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.export_report_btn = ttk.Button(
            btn_frame, text="导出评估报告",
            command=self._export_report, state=tk.DISABLED,
        )
        self.export_report_btn.pack(side=tk.LEFT)

        # === 进度条 ===
        self.progress_var = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(
            main_frame, variable=self.progress_var, maximum=100, mode="determinate"
        )
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))

        self.progress_label = ttk.Label(main_frame, text="就绪")
        self.progress_label.pack(anchor=tk.W)

        # === 结果预览区 ===
        result_frame = ttk.LabelFrame(main_frame, text="检测结果预览", padding="5")
        result_frame.pack(fill=tk.BOTH, expand=True)

        self.result_text = scrolledtext.ScrolledText(
            result_frame, height=15, width=80,
            font=("Consolas", 10), wrap=tk.WORD,
        )
        self.result_text.pack(fill=tk.BOTH, expand=True)

    # ==================== 事件处理 ====================

    def _select_input_file(self):
        """选择输入文件"""
        filepath = filedialog.askopenfilename(
            title="选择回复数据文件",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if filepath:
            self.input_file_var.set(filepath)
            data, error = load_json(filepath)
            if error:
                messagebox.showerror("文件加载失败", error)
                return
            valid, error = validate_replies(data)
            if not valid:
                messagebox.showerror("数据格式错误", error)
                return
            self.replies_data = data
            self.progress_label.config(
                text=f"已加载 {len(data)} 条回复数据"
            )

    def _select_gt_file(self):
        """选择 ground_truth 文件"""
        filepath = filedialog.askopenfilename(
            title="选择 Ground Truth 文件（可选）",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if filepath:
            self.gt_file_var.set(filepath)
            data, error = load_json(filepath)
            if error:
                messagebox.showerror("文件加载失败", error)
                return
            valid, error = validate_ground_truth(data)
            if not valid:
                messagebox.showerror("数据格式错误", error)
                return
            self.ground_truth_data = data

    def _on_mode_change(self):
        """模式切换"""
        if self.mode_var.get() == "api":
            self.api_frame.pack(
                fill=tk.X, pady=(0, 10), before=self.start_btn.master
            )
        else:
            self.api_frame.pack_forget()

    def _start_detection(self):
        """开始检测"""
        if self.is_running:
            return

        if not self.replies_data:
            messagebox.showwarning("提示", "请先选择输入文件")
            return

        if self.mode_var.get() == "api":
            if not self.api_key_var.get().strip():
                messagebox.showwarning("提示", "API 模式下请填写 API Key（前往 platform.deepseek.com 申请）")
                return

        self.is_running = True
        self.start_btn.config(state=tk.DISABLED, text="检测中...")
        self.export_result_btn.config(state=tk.DISABLED)
        self.export_report_btn.config(state=tk.DISABLED)
        self.result_text.delete(1.0, tk.END)
        self.progress_var.set(0)

        thread = threading.Thread(target=self._run_detection, daemon=True)
        thread.start()

    def _run_detection(self):
        """后台执行检测"""
        try:
            mode = self.mode_var.get()

            if mode == "mock":
                results = detect_all_mock(
                    self.replies_data,
                    progress_callback=self._update_progress,
                )
            else:
                api_config = {
                    "api_key": self.api_key_var.get().strip(),
                    "api_url": "https://api.deepseek.com/v1/chat/completions",
                    "model": self.model_var.get().strip(),
                }
                results = detect_all(
                    self.replies_data,
                    api_config,
                    progress_callback=self._update_progress,
                )

            self.detection_results = results

            if self.ground_truth_data:
                self.evaluation_report = generate_report(
                    results, self.ground_truth_data, mode
                )
            else:
                self.evaluation_report = None

            self.root.after(0, self._on_detection_done)

        except Exception as e:
            self.root.after(0, lambda: self._on_detection_error(str(e)))

    def _update_progress(self, current, total):
        """更新进度（从后台线程调用）"""
        percent = int(current / total * 100)
        self.root.after(0, lambda: self.progress_var.set(percent))
        self.root.after(
            0,
            lambda: self.progress_label.config(
                text=f"检测中... 第 {current}/{total} 条"
            ),
        )

    def _on_detection_done(self):
        """检测完成"""
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL, text="开始检测")
        self.export_result_btn.config(state=tk.NORMAL)

        if self.evaluation_report:
            self.export_report_btn.config(state=tk.NORMAL)

        self._show_preview()

        mode_name = "Mock" if self.mode_var.get() == "mock" else "API"
        hallucination_count = sum(
            1 for r in self.detection_results
            if r.get("is_hallucination") is True
        )
        error_count = sum(
            1 for r in self.detection_results
            if r.get("api_error")
        )

        msg = f"{mode_name} 模式检测完成！"
        msg += f"\n共 {len(self.detection_results)} 条，检出幻觉 {hallucination_count} 条"
        if error_count > 0:
            msg += f"，API 错误 {error_count} 条"
        if self.evaluation_report:
            s = self.evaluation_report["summary"]
            msg += (
                f"\n准确率: {s['accuracy']:.2%} | "
                f"精确率: {s['precision']:.2%} | "
                f"召回率: {s['recall']:.2%} | "
                f"F1: {s['f1']:.2%}"
            )

        messagebox.showinfo("检测完成", msg)

    def _on_detection_error(self, error_msg):
        """检测出错"""
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL, text="开始检测")
        self.progress_label.config(text=f"检测失败: {error_msg}")
        messagebox.showerror("检测失败", error_msg)

    def _show_preview(self):
        """显示结果预览"""
        self.result_text.delete(1.0, tk.END)

        if not self.detection_results:
            return

        # 模式标签
        mode_name = "Mock 模式（规则检测）" if self.mode_var.get() == "mock" else "API 模式（DeepSeek LLM 检测）"
        header = f"{'='*60}\n  {mode_name}\n{'='*60}\n\n"
        self.result_text.insert(1.0, header)

        lines = []
        for r in self.detection_results:
            rid = r["id"]
            is_h = r.get("is_hallucination")
            h_type = r.get("hallucination_type") or "-"
            severity = r.get("severity") or "-"
            reason = r.get("reason", "")

            if is_h is True:
                status = "!! 幻觉"
            elif is_h is False:
                status = "OK 正常"
            else:
                status = "?? 错误"

            line = f"[{rid}] {status} | 类型: {h_type} | 严重程度: {severity}"
            if reason:
                line += f"\n       原因: {reason}"

            spans = r.get("spans", [])
            if spans:
                for sp in spans[:3]:
                    line += f"\n         L- 片段: [{sp.get('text', '')[:50]}]"
                if len(spans) > 3:
                    line += f"\n         L- ... 共 {len(spans)} 处"

            lines.append(line)

        self.result_text.insert(1.0, "\n\n".join(lines))

        if self.evaluation_report:
            s = self.evaluation_report["summary"]
            summary = (
                f"\n\n{'='*60}\n"
                f"评估报告摘要\n"
                f"{'='*60}\n"
                f"准确率 (Accuracy): {s['accuracy']:.2%}\n"
                f"精确率 (Precision): {s['precision']:.2%}\n"
                f"召回率 (Recall):    {s['recall']:.2%}\n"
                f"F1 分数:           {s['f1']:.2%}\n"
                f"TP: {s['tp']}  FP: {s['fp']}  TN: {s['tn']}  FN: {s['fn']}\n"
            )
            if self.evaluation_report.get("warning"):
                summary += f"\n{self.evaluation_report['warning']}\n"
            self.result_text.insert(tk.END, summary)

    def _export_result(self):
        """导出检测结果"""
        if not self.detection_results:
            return

        filepath = filedialog.asksaveasfilename(
            title="保存检测结果",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json")],
            initialfile="detection_result.json",
        )
        if filepath:
            export_data = []
            for i, result in enumerate(self.detection_results):
                item = {
                    "id": result["id"],
                    "user_question": self.replies_data[i].get("user_question", ""),
                    "system_reply": self.replies_data[i].get("system_reply", ""),
                    "knowledge_base": self.replies_data[i].get("knowledge_base", ""),
                    "is_hallucination": result.get("is_hallucination"),
                    "hallucination_type": result.get("hallucination_type"),
                    "severity": result.get("severity"),
                    "reason": result.get("reason", ""),
                    "spans": result.get("spans", []),
                }
                export_data.append(item)

            save_json(filepath, export_data)
            messagebox.showinfo("导出成功", f"检测结果已保存到:\n{filepath}")

    def _export_report(self):
        """导出评估报告"""
        if not self.evaluation_report:
            return

        filepath = filedialog.asksaveasfilename(
            title="保存评估报告",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json")],
            initialfile="evaluation_report.json",
        )
        if filepath:
            save_json(filepath, self.evaluation_report)
            messagebox.showinfo("导出成功", f"评估报告已保存到:\n{filepath}")


def main():
    """入口函数"""
    root = tk.Tk()
    app = HallucinationDetectorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()