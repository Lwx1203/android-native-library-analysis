# -*- coding: utf-8 -*-
"""
模块 6 —— 语义标注与权重计算模块
职责：语义域划分、权重计算、按 JNI 函数分组输出
"""

import os
import re
import json
import glob
import time
import logging

logger = logging.getLogger("pipeline.module6")


# ──────────────────────────────────────────────
# JNI 函数加载与索引
# ──────────────────────────────────────────────
def _load_jni_funcs(work_dir: str):
    """加载工作目录下所有 *.so.funcs.json，返回 (funcs_list, index_dict, file_names)"""
    pattern = os.path.join(work_dir, "*.so.funcs.json")
    json_files = sorted(glob.glob(pattern))

    all_funcs = []
    loaded_files = []
    for jf in json_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)
            so_name = os.path.basename(jf).replace(".funcs.json", "")
            for symbol, info in data.items():
                all_funcs.append({
                    "symbol": symbol,
                    "className": info["className"],
                    "name": info["name"],
                    "descriptor": info.get("descriptor", ""),
                    "source_so": so_name,
                })
            loaded_files.append(os.path.basename(jf))
        except Exception as e:
            logger.warning(f"    解析 {jf} 失败: {e}")

    # 构建 (className, name) -> info 索引
    index = {}
    for func in all_funcs:
        key = (func["className"], func["name"])
        if key not in index:
            index[key] = func
    return all_funcs, index, loaded_files


# ──────────────────────────────────────────────
# 调用栈文本解析
# ──────────────────────────────────────────────
_NODE_RE = re.compile(
    r"^\s*(\S+)\s+(L[\w/$]+;)\s*::\s*(\w+)\(([^)]*)\)\s*$"
)


def _parse_node(raw: str):
    m = _NODE_RE.match(raw.strip())
    if not m:
        return None
    cn = m.group(2)
    return {
        "return_type": m.group(1),
        "class_name": cn,
        "class_short_name": cn.rstrip(";").split("/")[-1],
        "method_name": m.group(3),
        "params": m.group(4).strip(),
    }


def _parse_stacks(txt_path: str):
    with open(txt_path, "r", encoding="utf-8") as f:
        content = f.read()
    stacks = {}
    blocks = re.findall(
        r"Stack\s*#(\d+)\s*(?:\[Cycle\])?\s*\n(.*?)(?=Stack\s*#|\Z)", content, re.DOTALL
    )
    for num_str, body in blocks:
        raw_nodes = re.split(r"\s*->\s*", body.strip())
        nodes = []
        for raw in raw_nodes:
            raw = raw.strip()
            if not raw:
                continue
            node = _parse_node(raw)
            if node:
                nodes.append(node)
        if nodes:
            stacks[int(num_str)] = nodes
    return stacks


# ──────────────────────────────────────────────
# 核心算法：锚点定位 + 语义域标注 + 权重计算
# ──────────────────────────────────────────────
def _annotate_stack(nodes, jni_index):
    """
    返回 (annotated_lines, annotated_nodes, error, source_so, matched_jni)
    """
    idx_jni = -1
    matched_jni = None
    for i, node in enumerate(nodes):
        key = (node["class_name"], node["method_name"])
        if key in jni_index:
            idx_jni = i
            matched_jni = jni_index[key]
            break

    if idx_jni == -1:
        return [], [], "未找到JNI锚点", None, None

    source_so = matched_jni.get("source_so", "unknown")
    annotated_lines = []
    annotated_nodes = []

    for i, node in enumerate(nodes):
        d = idx_jni - i
        if d > 0:
            label = "Intent Domain"
        elif d == 0:
            label = "Target JNI Anchor"
        else:
            if "NativeSummary" in node["class_name"]:
                label = "Core Execution Domain"
            else:
                label = "Interaction Domain"

        weight = 1.0 / (abs(d) + 1)

        line = (
            f"[{label}] {node['return_type']} {node['class_short_name']} :: "
            f"{node['method_name']}({node['params']}) (W={weight:.2f})"
        )
        annotated_lines.append(line)
        annotated_nodes.append({
            "label": label,
            "return_type": node["return_type"],
            "class_name": node["class_name"],
            "class_short_name": node["class_short_name"],
            "method_name": node["method_name"],
            "params": node["params"],
            "weight": round(weight, 4),
        })

    return annotated_lines, annotated_nodes, None, source_so, matched_jni


# ──────────────────────────────────────────────
# 公开接口
# ──────────────────────────────────────────────
def annotate(ctx: dict) -> None:
    t0 = time.time()
    sample_id = ctx["sample_id"]
    work_dir = ctx["work_dir"]

    stacks_file = ctx.get("stacks_path")
    if not stacks_file or not os.path.isfile(stacks_file):
        logger.warning(f"[Module6] {sample_id}: 无调用栈文件，跳过")
        ctx["status"]["module6"] = "skipped"
        return

    # 文件大小检查
    size_mb = os.path.getsize(stacks_file) / (1024 * 1024)
    if size_mb > 200:
        logger.warning(f"[Module6] {sample_id}: 调用栈文件 {size_mb:.0f}MB 过大，跳过")
        ctx["status"]["module6"] = "skipped"
        return

    logger.info(f"[Module6] 语义标注: {sample_id}")

    all_funcs, jni_index, loaded_files = _load_jni_funcs(work_dir)
    if not jni_index:
        ctx["status"]["module6"] = "skipped"
        return

    try:
        stacks = _parse_stacks(stacks_file)
    except Exception as e:
        logger.error(f"[Module6] 调用栈解析失败: {e}")
        ctx["status"]["module6"] = "error"
        ctx["errors"].append(f"Module6: {e}")
        return

    # ── 阶段一：标注所有调用栈 ──
    annotated_json_data = {
        "project_name": sample_id,
        "loaded_so_files": loaded_files,
        "jni_func_count": len(all_funcs),
        "total_stacks": len(stacks),
        "stacks": [],
    }

    out_txt = os.path.join(work_dir, "annotated.txt")
    stats = {"total": len(stacks), "matched": 0, "unmatched": 0}

    with open(out_txt, "w", encoding="utf-8") as f:
        f.write(f"{'═' * 60}\n 项目: {sample_id}\n{'═' * 60}\n")
        f.write(f"已加载 .so 库: {', '.join(loaded_files)} (共 {len(all_funcs)} 个 JNI 函数)\n")
        f.write(f"调用栈数量: {len(stacks)}  (文件大小: {size_mb:.1f} MB)\n\n")

        for stack_num in sorted(stacks.keys()):
            nodes = stacks[stack_num]
            a_lines, a_nodes, error, source_so, matched_jni = _annotate_stack(nodes, jni_index)

            if error:
                f.write(f"--- Stack #{stack_num} ---\n  [Skip] {error}\n\n")
                stats["unmatched"] += 1
                annotated_json_data["stacks"].append({
                    "stack_id": stack_num, "matched": False, "error": error,
                })
            else:
                f.write(f"--- Stack #{stack_num} ---\n  [匹配库: {source_so}]\n")
                f.write(("\n    -> ").join(a_lines) + "\n\n")
                stats["matched"] += 1
                annotated_json_data["stacks"].append({
                    "stack_id": stack_num, "matched": True,
                    "source_so": source_so,
                    "jni_anchor": {
                        "symbol": matched_jni["symbol"],
                        "className": matched_jni["className"],
                        "name": matched_jni["name"],
                        "descriptor": matched_jni.get("descriptor", ""),
                    },
                    "annotated_nodes": a_nodes,
                })

        f.write(
            f"\n[统计] 总计 {stats['total']} 条, "
            f"匹配 {stats['matched']} 条, 未匹配 {stats['unmatched']} 条\n"
        )

    annotated_json_data["matched_count"] = stats["matched"]
    annotated_json_data["unmatched_count"] = stats["unmatched"]

    out_json = os.path.join(work_dir, "annotated.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(annotated_json_data, f, indent=2, ensure_ascii=False)

    ctx["annotated_txt_path"] = out_txt
    ctx["annotated_json_path"] = out_json

    # ── 阶段二：按 JNI 函数分组 ──
    func_stacks = {}
    for entry in annotated_json_data["stacks"]:
        if not entry.get("matched"):
            continue
        symbol = entry["jni_anchor"]["symbol"]
        if symbol not in func_stacks:
            func_stacks[symbol] = []
        func_stacks[symbol].append({
            "stack_id": entry["stack_id"],
            "source_so": entry.get("source_so", ""),
            "annotated_nodes": entry.get("annotated_nodes", []),
        })

    # 构建 symbol -> jni_info 映射
    symbol_to_info = {func["symbol"]: func for func in all_funcs}

    functions = []
    for symbol in sorted(func_stacks.keys()):
        info = symbol_to_info.get(symbol, {})
        functions.append({
            "function_name": symbol,
            "class_name": info.get("className", ""),
            "method_name": info.get("name", ""),
            "descriptor": info.get("descriptor", ""),
            "source_so": info.get("source_so", ""),
            "call_stacks_count": len(func_stacks[symbol]),
            "call_stacks": func_stacks[symbol],
        })

    functions_output = {
        "app": sample_id,
        "total_jni_functions": len(functions),
        "total_stacks_collected": sum(fn["call_stacks_count"] for fn in functions),
        "functions": functions,
    }

    out_func = os.path.join(work_dir, "functions.json")
    with open(out_func, "w", encoding="utf-8") as f:
        json.dump(functions_output, f, indent=2, ensure_ascii=False)
    ctx["functions_json_path"] = out_func

    ctx["status"]["module6"] = "success"
    ctx["timings"]["module6"] = round(time.time() - t0, 3)
    logger.info(
        f"[Module6] {sample_id}: 匹配 {stats['matched']}/{stats['total']}, "
        f"分组 {len(functions)} 个 JNI 函数"
    )