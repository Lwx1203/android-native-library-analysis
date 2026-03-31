# -*- coding: utf-8 -*-
"""
模块 4 —— 调用图构建模块
职责：使用 Androguard 对统一化 APK 构建全局调用图
"""

import os
import time
import logging

logger = logging.getLogger("pipeline.module4")


# ──────────────────────────────────────────────
# 描述符解析
# ──────────────────────────────────────────────
_TYPE_MAP = {
    'V': 'void', 'Z': 'boolean', 'B': 'byte', 'C': 'char',
    'S': 'short', 'I': 'int', 'J': 'long', 'F': 'float', 'D': 'double',
}


def _parse_single_type(desc, idx):
    array_depth = 0
    while idx < len(desc) and desc[idx] == '[':
        array_depth += 1
        idx += 1
    if idx >= len(desc):
        return 'unknown', idx
    ch = desc[idx]
    if ch in _TYPE_MAP:
        base_type = _TYPE_MAP[ch]
        idx += 1
    elif ch == 'L':
        end = desc.index(';', idx)
        base_type = desc[idx + 1:end].split('/')[-1]
        idx = end + 1
    else:
        base_type = 'unknown'
        idx += 1
    return base_type + '[]' * array_depth, idx


def _parse_descriptor(descriptor):
    try:
        if '(' not in descriptor or ')' not in descriptor:
            return descriptor, ''
        ps = descriptor.index('(') + 1
        pe = descriptor.index(')')
        ret_desc = descriptor[pe + 1:]

        params = []
        idx = ps
        while idx < pe:
            t, idx = _parse_single_type(descriptor, idx)
            params.append(t)

        ret, _ = _parse_single_type(ret_desc, 0)
        return (', '.join(params) if params else ''), ret
    except Exception:
        return descriptor, ''


def _format_method(cls, name, desc):
    params_str, ret_str = _parse_descriptor(desc)
    return f"{ret_str} {cls} :: {name}({params_str})"


# ──────────────────────────────────────────────
# 公开接口
# ──────────────────────────────────────────────
def build_call_graph(ctx: dict) -> None:
    t0 = time.time()
    sample_id = ctx["sample_id"]

    apk_path = ctx.get("unified_apk_path")
    if not apk_path or not os.path.isfile(apk_path):
        logger.warning(f"[Module4] {sample_id}: 无统一化 APK，跳过")
        ctx["status"]["module4"] = "skipped"
        return

    repacked_dir = os.path.dirname(apk_path)
    output_path = os.path.join(repacked_dir, "call_graph_result.txt")

    # 跳过已有
    if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
        ctx["call_graph_path"] = output_path
        ctx["status"]["module4"] = "skipped_existing"
        logger.info(f"[Module4] {sample_id}: 调用图已存在，跳过")
        return

    logger.info(f"[Module4] 构建调用图: {sample_id}")

    try:
        from androguard.misc import AnalyzeAPK
        a, d, dx = AnalyzeAPK(apk_path)
    except Exception as e:
        logger.error(f"[Module4] Androguard 分析失败: {e}")
        ctx["status"]["module4"] = "error"
        ctx["errors"].append(f"Module4: {e}")
        ctx["timings"]["module4"] = round(time.time() - t0, 3)
        return

    count = 0
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"应用名称: {a.get_app_name()}\n")
            f.write(f"包名: {a.get_package()}\n")
            f.write("=" * 80 + "\n")
            f.write("调用关系图 (Source -> Target)  [含方法签名与返回值]\n")
            f.write("格式: 返回值 类名 :: 方法名(参数列表)\n")
            f.write("=" * 80 + "\n\n")

            for method in dx.get_methods():
                if method.is_external():
                    continue
                m = method.get_method()
                caller_str = _format_method(
                    m.get_class_name(), m.get_name(), m.get_descriptor()
                )
                for _, call, _ in method.get_xref_to():
                    c = call.get_method()
                    callee_str = _format_method(
                        c.get_class_name(), c.get_name(), c.get_descriptor()
                    )
                    f.write(f"{caller_str}\n    --> {callee_str}\n\n")
                    count += 1
    except Exception as e:
        logger.error(f"[Module4] 写入调用图失败: {e}")
        ctx["status"]["module4"] = "error"
        ctx["errors"].append(f"Module4: {e}")
        ctx["timings"]["module4"] = round(time.time() - t0, 3)
        return

    ctx["call_graph_path"] = output_path
    ctx["call_graph_edge_count"] = count
    ctx["status"]["module4"] = "success"
    ctx["timings"]["module4"] = round(time.time() - t0, 3)
    logger.info(f"[Module4] {sample_id}: 提取 {count} 条调用关系")