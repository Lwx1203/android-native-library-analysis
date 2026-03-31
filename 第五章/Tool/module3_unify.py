# -*- coding: utf-8 -*-
"""
模块 3 —— 代码统一化模块（NativeSummary Docker）
职责：预分析 + 深度分析，生成统一化 APK 和 JNI 映射
"""

import os
import json
import glob
import shutil
import subprocess
import logging
import time

logger = logging.getLogger("pipeline.module3")


# ──────────────────────────────────────────────
# Docker 调用
# ──────────────────────────────────────────────
def _check_docker():
    try:
        r = subprocess.run(["docker", "ps"], capture_output=True, text=True)
        return r.returncode == 0
    except FileNotFoundError:
        return False


def _run_docker(apk_path: str, output_dir: str, config, mode="all") -> bool:
    container_input = "/apk/target.apk"
    container_output = "/out"

    host_apk = apk_path.replace("\\", "/")
    host_out = output_dir.replace("\\", "/")

    if mode == "pre":
        docker_args = [mode, container_input, container_output]
    else:
        docker_args = [mode, "--apk", container_input, "--out", container_output]

    cmd = [
        "docker", "run", "--rm",
        "-v", f"{host_apk}:{container_input}",
        "-v", f"{host_out}:{container_output}",
        config.docker_image,
    ] + docker_args

    log_file = os.path.join(output_dir, "docker_run.log")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=config.docker_timeout
        )
    except subprocess.TimeoutExpired:
        logger.warning(f"Docker 任务超时 (mode={mode})")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n=== Mode: {mode} === TIMEOUT ===\n")
        return False

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n\n=== Mode: {mode} ===\n")
        f.write(f"CMD: {' '.join(cmd)}\n")
        f.write("=== STDOUT ===\n")
        f.write(result.stdout)
        f.write("\n=== STDERR ===\n")
        f.write(result.stderr)

    return result.returncode == 0


def _check_pre_analysis(output_dir: str) -> bool:
    for name in ("apk_pre_analysis.json", "analysis_result.json"):
        path = os.path.join(output_dir, name)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                pct = data.get("resolve_percentage", 0.0)
                if pct > 0.0:
                    logger.info(f"    预分析通过，匹配率: {pct}%")
                    return True
                else:
                    logger.info(f"    预分析匹配率 0%，跳过深度分析")
                    return False
            except Exception as e:
                logger.warning(f"    解析预分析 JSON 失败: {e}")
    return False


# ──────────────────────────────────────────────
# 公开接口
# ──────────────────────────────────────────────
def unify(ctx: dict, config) -> None:
    """对单个样本执行代码统一化"""
    t0 = time.time()
    sample_id = ctx["sample_id"]
    work_dir = ctx["work_dir"]

    logger.info(f"[Module3] 统一化: {sample_id}")

    if not ctx.get("has_native_libs"):
        logger.info(f"    无本地库，跳过")
        ctx["status"]["module3"] = "skipped"
        return

    # 检查 Docker
    if not _check_docker():
        logger.error("Docker 未运行")
        ctx["status"]["module3"] = "error"
        ctx["errors"].append("Module3: Docker 未运行")
        return

    # 跳过已处理
    unified_apk = os.path.join(work_dir, "repacked_apks", "target.apk")
    if config.skip_existing and os.path.isfile(unified_apk):
        logger.info(f"    已存在统一化 APK，跳过")
        ctx["unified_apk_path"] = unified_apk
        ctx["jni_func_files"] = [
            os.path.basename(p)
            for p in glob.glob(os.path.join(work_dir, "*.so.funcs.json"))
        ]
        ctx["status"]["module3"] = "skipped_existing"
        return

    apk_path = ctx["apk_path"]

    # 1) 预分析
    logger.info(f"    运行预分析 (pre)...")
    _run_docker(apk_path, work_dir, config, mode="pre")

    # 2) 检查是否值得深度分析
    if not _check_pre_analysis(work_dir):
        ctx["status"]["module3"] = "skipped_no_value"
        ctx["timings"]["module3"] = round(time.time() - t0, 3)
        return

    # 3) 深度分析
    logger.info(f"    运行深度分析 (all)...")
    success = _run_docker(apk_path, work_dir, config, mode="all")

    if not success:
        ctx["status"]["module3"] = "error"
        ctx["errors"].append("Module3: Docker all 模式执行失败")
        ctx["timings"]["module3"] = round(time.time() - t0, 3)
        return

    # 收集输出
    if os.path.isfile(unified_apk):
        ctx["unified_apk_path"] = unified_apk
    else:
        ctx["unified_apk_path"] = None
        ctx["status"]["module3"] = "error"
        ctx["errors"].append("Module3: 未生成统一化 APK")
        ctx["timings"]["module3"] = round(time.time() - t0, 3)
        return

    ctx["jni_func_files"] = [
        os.path.basename(p)
        for p in glob.glob(os.path.join(work_dir, "*.so.funcs.json"))
    ]

    # 加载预分析信息
    for name in ("apk_pre_analysis.json", "analysis_result.json"):
        pa = os.path.join(work_dir, name)
        if os.path.isfile(pa):
            try:
                with open(pa, "r", encoding="utf-8") as f:
                    ctx["pre_analysis"] = json.load(f)
            except Exception:
                pass
            break

    ctx["status"]["module3"] = "success"
    ctx["timings"]["module3"] = round(time.time() - t0, 3)
    logger.info(f"    统一化完成，JNI 映射文件: {ctx['jni_func_files']}")