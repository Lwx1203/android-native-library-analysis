# -*- coding: utf-8 -*-
"""
模块 2 —— 本地库检测模块
职责：检测 APK 中的 .so 文件，提取 ABI 分布信息
"""

import os
import json
import zipfile
import logging
from collections import defaultdict

logger = logging.getLogger("pipeline.module2")


def detect(ctx: dict) -> None:
    """
    检测 ctx["apk_path"] 中的本地库信息，结果写入 ctx。
    """
    import time
    t0 = time.time()

    apk_path = ctx["apk_path"]
    logger.info(f"[Module2] 检测本地库: {ctx['apk_name']}")

    so_files = []        # 所有 .so 条目
    lib_groups = defaultdict(lambda: {"abis": [], "sizes": {}})

    try:
        with zipfile.ZipFile(apk_path, "r") as z:
            for entry in z.namelist():
                if not entry.endswith(".so"):
                    continue
                # 典型路径: lib/armeabi-v7a/libnative.so
                parts = entry.split("/")
                if len(parts) >= 3 and parts[0] == "lib":
                    abi = parts[1]
                    so_name = parts[-1]
                else:
                    abi = "unknown"
                    so_name = os.path.basename(entry)

                info = z.getinfo(entry)
                file_size = info.file_size

                so_files.append({
                    "path": entry,
                    "name": so_name,
                    "abi": abi,
                    "size": file_size,
                })

                grp = lib_groups[so_name]
                if abi not in grp["abis"]:
                    grp["abis"].append(abi)
                grp["sizes"][abi] = file_size

    except Exception as e:
        logger.error(f"[Module2] 读取 APK 失败: {e}")
        ctx["has_native_libs"] = False
        ctx["status"]["module2"] = "error"
        ctx["errors"].append(f"Module2: {e}")
        return

    # 构建逻辑库列表
    native_libs = []
    for name, grp in sorted(lib_groups.items()):
        native_libs.append({
            "name": name,
            "abis": sorted(grp["abis"]),
            "sizes": grp["sizes"],
        })

    unique_count = len(native_libs)

    ctx["so_files"] = so_files
    ctx["native_libs"] = native_libs
    ctx["unique_so_count"] = unique_count
    ctx["has_native_libs"] = unique_count > 0

    # 持久化
    result = {
        "apk_name": ctx["apk_name"],
        "sample_id": ctx["sample_id"],
        "has_native_libs": ctx["has_native_libs"],
        "unique_so_count": unique_count,
        "total_so_entries": len(so_files),
        "native_libs": native_libs,
        "so_files": so_files,
    }
    out_path = os.path.join(ctx["work_dir"], "native_libs.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    elapsed = time.time() - t0
    ctx["timings"]["module2"] = round(elapsed, 3)
    ctx["status"]["module2"] = "success"

    logger.info(
        f"[Module2] {ctx['sample_id']}: "
        f"发现 {unique_count} 个逻辑库 ({len(so_files)} 个 .so 条目)"
    )