# -*- coding: utf-8 -*-
"""
模块 1 —— APK 预处理模块
职责：输入校验、元数据提取、工作目录初始化、同包名去重
"""

import os
import time
import json
import logging

logger = logging.getLogger("pipeline.module1")


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────
def _parse_apk_filename(filename: str):
    """
    解析 APK 文件名，返回 (包名, 版本号)
    约定格式: com.example.app_123.apk
    """
    stem = os.path.splitext(filename)[0]
    parts = stem.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0], int(parts[1])
    return stem, -1


def _validate_apk(path: str) -> bool:
    if not os.path.isfile(path):
        return False
    if not path.lower().endswith(".apk"):
        return False
    return True


def _make_context(apk_path: str, sample_id: str, version_code: int,
                  work_dir: str) -> dict:
    """构造一个样本上下文字典"""
    file_size = os.path.getsize(apk_path)
    return {
        # 基本信息
        "apk_path": os.path.abspath(apk_path),
        "apk_name": os.path.basename(apk_path),
        "sample_id": sample_id,
        "version_code": version_code,
        "file_size": file_size,
        "work_dir": work_dir,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        # 后续模块依次填充
        "has_native_libs": None,
        "unique_so_count": 0,
        "native_libs": [],
        "so_files": [],
        "unified_apk_path": None,
        "jni_func_files": [],
        "pre_analysis": None,
        "call_graph_path": None,
        "call_graph_edge_count": 0,
        "stacks_path": None,
        "stacks_full_path": None,
        "annotated_txt_path": None,
        "annotated_json_path": None,
        "functions_json_path": None,
        "llm_results_path": None,
        # 状态跟踪
        "status": {},
        "errors": [],
        "timings": {},
    }


# ──────────────────────────────────────────────
# 公开接口
# ──────────────────────────────────────────────
def preprocess(input_path: str, config) -> list:
    """
    入口函数。
    input_path 可以是单个 APK 路径或目录。
    返回 context 列表。
    """
    contexts = []

    if os.path.isfile(input_path):
        # ── 单个 APK ──
        if not _validate_apk(input_path):
            logger.error(f"输入文件不合法: {input_path}")
            return []
        ctx = _process_single(input_path, config)
        if ctx:
            contexts.append(ctx)
    elif os.path.isdir(input_path):
        # ── 目录批量 ──
        contexts = _process_directory(input_path, config)
    else:
        logger.error(f"输入路径不存在: {input_path}")

    # 持久化元数据
    for ctx in contexts:
        _save_metadata(ctx)
        ctx["status"]["module1"] = "success"

    logger.info(f"[Module1] 预处理完成，共 {len(contexts)} 个有效样本")
    return contexts


def _process_single(apk_path: str, config) -> dict:
    filename = os.path.basename(apk_path)
    sample_id, ver = _parse_apk_filename(filename)
    work_dir = config.work_dir_for(sample_id)
    os.makedirs(work_dir, exist_ok=True)
    return _make_context(apk_path, sample_id, ver, work_dir)


def _process_directory(dir_path: str, config) -> list:
    """扫描目录，可选只保留同包名最新版本"""
    # 收集所有 APK
    apk_map = {}  # sample_id -> (version, full_path)
    for root, _, files in os.walk(dir_path):
        for f in files:
            if not f.lower().endswith(".apk"):
                continue
            full = os.path.join(root, f)
            sid, ver = _parse_apk_filename(f)
            if config.keep_latest_version_only:
                if sid not in apk_map or ver > apk_map[sid][0]:
                    apk_map[sid] = (ver, full)
            else:
                key = f"{sid}_{ver}" if ver >= 0 else sid
                apk_map[key] = (ver, full)

    contexts = []
    for sid, (ver, path) in apk_map.items():
        work_dir = config.work_dir_for(sid)
        os.makedirs(work_dir, exist_ok=True)
        ctx = _make_context(path, sid, ver, work_dir)
        contexts.append(ctx)

    return contexts


def _save_metadata(ctx: dict):
    meta = {
        "apk_path": ctx["apk_path"],
        "apk_name": ctx["apk_name"],
        "sample_id": ctx["sample_id"],
        "version_code": ctx["version_code"],
        "file_size": ctx["file_size"],
        "timestamp": ctx["timestamp"],
    }
    path = os.path.join(ctx["work_dir"], "metadata.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)