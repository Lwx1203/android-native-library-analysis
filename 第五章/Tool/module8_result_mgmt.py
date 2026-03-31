# -*- coding: utf-8 -*-
"""
模块 8 —— 结果管理与展示模块
职责：应用级/函数级结果汇总、日志管理、状态记录、报告生成
"""

import os
import json
import time
import logging

logger = logging.getLogger("pipeline.module8")


# ──────────────────────────────────────────────
# 单个应用报告
# ──────────────────────────────────────────────
def generate_app_report(ctx: dict) -> None:
    """为单个样本生成应用级报告"""
    work_dir = ctx["work_dir"]
    sample_id = ctx["sample_id"]

    # ── 应用级信息 ──
    app_info = {
        "sample_id": sample_id,
        "apk_name": ctx.get("apk_name", ""),
        "apk_path": ctx.get("apk_path", ""),
        "file_size": ctx.get("file_size", 0),
        "version_code": ctx.get("version_code", -1),
        "timestamp": ctx.get("timestamp", ""),
    }

    # ── 本地库信息 ──
    native_info = {
        "has_native_libs": ctx.get("has_native_libs", False),
        "unique_so_count": ctx.get("unique_so_count", 0),
        "native_libs": ctx.get("native_libs", []),
        "abi_distribution": _calc_abi_distribution(ctx.get("native_libs", [])),
    }

    # ── 函数级信息 ──
    func_info = _load_function_summary(ctx)

    # ── 分析过程信息 ──
    process_info = {
        "module_status": dict(ctx.get("status", {})),
        "timings": dict(ctx.get("timings", {})),
        "total_elapsed": sum(ctx.get("timings", {}).values()),
        "errors": list(ctx.get("errors", [])),
        "jni_func_files": ctx.get("jni_func_files", []),
        "call_graph_edge_count": ctx.get("call_graph_edge_count", 0),
    }

    report = {
        "report_version": "1.0",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "app_info": app_info,
        "native_lib_info": native_info,
        "function_info": func_info,
        "process_info": process_info,
    }

    out_path = os.path.join(work_dir, "report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    ctx["status"]["module8"] = "success"
    logger.info(f"[Module8] 应用报告已生成: {sample_id}")


def _calc_abi_distribution(native_libs: list) -> dict:
    dist = {}
    for lib in native_libs:
        for abi in lib.get("abis", []):
            dist[abi] = dist.get(abi, 0) + 1
    return dist


def _load_function_summary(ctx: dict) -> dict:
    """从 functions.json 和 llm_results.json 提取函数级汇总"""
    summary = {
        "jni_function_count": 0,
        "stacks_collected": 0,
        "llm_success": 0,
        "llm_error": 0,
        "function_results": [],
    }

    # 从 functions.json 统计
    func_path = ctx.get("functions_json_path")
    if func_path and os.path.isfile(func_path):
        try:
            with open(func_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            summary["jni_function_count"] = len(data.get("functions", []))
            summary["stacks_collected"] = data.get("total_stacks_collected", 0)
        except Exception:
            pass

    # 从 llm_results.json 提取推断结果
    llm_path = ctx.get("llm_results_path")
    if llm_path and os.path.isfile(llm_path):
        try:
            with open(llm_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            summary["llm_success"] = data.get("success_count", 0)
            summary["llm_error"] = data.get("error_count", 0)
            for r in data.get("results", []):
                summary["function_results"].append({
                    "function_name": r.get("function_name", ""),
                    "source_so": r.get("source_so", ""),
                    "result": r.get("result", ""),
                    "status": r.get("status", ""),
                })
        except Exception:
            pass

    return summary


# ──────────────────────────────────────────────
# 全局批量报告
# ──────────────────────────────────────────────
def generate_global_report(all_contexts: list, config) -> None:
    """生成全局汇总报告"""
    output_root = config.output_root

    total = len(all_contexts)
    status_counts = {}
    total_timings = {}
    total_funcs = 0
    total_stacks = 0
    llm_success = 0
    llm_error = 0
    app_summaries = []

    for ctx in all_contexts:
        # 模块状态汇总
        for mod, st in ctx.get("status", {}).items():
            key = f"{mod}_{st}"
            status_counts[key] = status_counts.get(key, 0) + 1

        # 耗时汇总
        for mod, t in ctx.get("timings", {}).items():
            total_timings[mod] = total_timings.get(mod, 0) + t

        # 读取应用报告
        report_path = os.path.join(ctx["work_dir"], "report.json")
        if os.path.isfile(report_path):
            try:
                with open(report_path, "r", encoding="utf-8") as f:
                    rpt = json.load(f)
                fi = rpt.get("function_info", {})
                total_funcs += fi.get("jni_function_count", 0)
                total_stacks += fi.get("stacks_collected", 0)
                llm_success += fi.get("llm_success", 0)
                llm_error += fi.get("llm_error", 0)

                app_summaries.append({
                    "sample_id": ctx["sample_id"],
                    "status": ctx.get("status", {}),
                    "jni_functions": fi.get("jni_function_count", 0),
                    "stacks": fi.get("stacks_collected", 0),
                    "llm_success": fi.get("llm_success", 0),
                    "errors": ctx.get("errors", []),
                })
            except Exception:
                app_summaries.append({
                    "sample_id": ctx["sample_id"],
                    "status": ctx.get("status", {}),
                    "errors": ctx.get("errors", []),
                })
        else:
            app_summaries.append({
                "sample_id": ctx["sample_id"],
                "status": ctx.get("status", {}),
                "errors": ctx.get("errors", []),
            })

    global_report = {
        "report_version": "1.0",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "total_samples": total,
            "total_jni_functions": total_funcs,
            "total_stacks_collected": total_stacks,
            "llm_success": llm_success,
            "llm_error": llm_error,
        },
        "module_status_distribution": status_counts,
        "total_timings_sec": {k: round(v, 2) for k, v in total_timings.items()},
        "app_summaries": app_summaries,
    }

    out_path = os.path.join(output_root, "_pipeline_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(global_report, f, indent=2, ensure_ascii=False)

    # ── 同时输出可读文本报告 ──
    txt_path = os.path.join(output_root, "_pipeline_report.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("  管线执行报告\n")
        f.write(f"  生成时间: {global_report['generated_at']}\n")
        f.write("=" * 70 + "\n\n")

        s = global_report["summary"]
        f.write(f"总样本数:           {s['total_samples']}\n")
        f.write(f"JNI 函数总数:       {s['total_jni_functions']}\n")
        f.write(f"调用栈总数:         {s['total_stacks_collected']}\n")
        f.write(f"LLM 推断成功:       {s['llm_success']}\n")
        f.write(f"LLM 推断失败:       {s['llm_error']}\n\n")

        f.write("─" * 70 + "\n")
        f.write("各模块状态分布:\n")
        for k, v in sorted(status_counts.items()):
            f.write(f"  {k}: {v}\n")

        f.write("\n各模块累计耗时(秒):\n")
        for k, v in sorted(total_timings.items()):
            f.write(f"  {k}: {v:.2f}\n")

        f.write("\n" + "─" * 70 + "\n")
        f.write("各应用明细:\n\n")
        for app in app_summaries:
            f.write(f"  [{app['sample_id']}]\n")
            f.write(f"    状态: {app.get('status', {})}\n")
            if app.get("jni_functions"):
                f.write(f"    JNI函数: {app.get('jni_functions', 0)}, "
                        f"调用栈: {app.get('stacks', 0)}, "
                        f"LLM成功: {app.get('llm_success', 0)}\n")
            if app.get("errors"):
                f.write(f"    错误: {app['errors']}\n")
            f.write("\n")

    logger.info(f"[Module8] 全局报告已生成: {out_path}")
    logger.info(f"[Module8] 文本报告已生成: {txt_path}")

    # 控制台输出汇总
    print("\n" + "=" * 70)
    print("  管线执行完毕")
    print("=" * 70)
    print(f"  总样本数:        {s['total_samples']}")
    print(f"  JNI 函数总数:    {s['total_jni_functions']}")
    print(f"  调用栈总数:      {s['total_stacks_collected']}")
    print(f"  LLM 推断成功:    {s['llm_success']}")
    print(f"  LLM 推断失败:    {s['llm_error']}")
    print(f"  报告路径:        {out_path}")
    print("=" * 70)