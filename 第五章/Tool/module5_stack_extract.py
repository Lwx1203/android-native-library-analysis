# -*- coding: utf-8 -*-
"""
模块 5 —— 调用栈提取与去噪模块
职责：从调用图中提取目标 JNI 函数调用栈，剔除系统 API 噪声
"""

import os
import re
import json
import glob
import time
import logging

logger = logging.getLogger("pipeline.module5")


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────
def _extract_class_and_method(node_str):
    try:
        parts = node_str.split(' :: ')
        if len(parts) != 2:
            return None, None
        left = parts[0].strip()
        right = parts[1].strip()
        tokens = left.split()
        class_name = None
        for t in tokens:
            if t.startswith('L') and t.endswith(';'):
                class_name = t
                break
        if not class_name and len(tokens) >= 2:
            class_name = tokens[-1]
        method_name = right[:right.index('(')] if '(' in right else right
        return class_name, method_name
    except Exception:
        return None, None


def _extract_class_name(node_str):
    c, _ = _extract_class_and_method(node_str)
    return c


# ──────────────────────────────────────────────
# APIManager
# ──────────────────────────────────────────────
class APIManager:
    def __init__(self, api_file_path: str):
        self.system_classes = set()
        self.safe_prefixes = ("Ljava/", "Ljavax/", "Lsun/")
        self._load(api_file_path)

    def _load(self, path):
        if not os.path.exists(path):
            logger.error(f"API 文件不存在: {path}")
            return
        pkg_pat = re.compile(r'^\s*package\s+([\w.]+)\s*\{')
        cls_pat = re.compile(r'^\s*.*(?:class|interface)\s+([\w.]+)')
        cur_pkg = ""
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line.startswith('//') or line.startswith('=') or line.startswith('SOURCE:'):
                    continue
                m = pkg_pat.match(line)
                if m:
                    cur_pkg = m.group(1)
                    continue
                m = cls_pat.match(line)
                if m and cur_pkg:
                    raw = m.group(1).replace('.', '$')
                    smali = f"L{cur_pkg.replace('.', '/')}/{raw};"
                    self.system_classes.add(smali)
        logger.info(f"[Module5] 加载 {len(self.system_classes)} 个系统类")

    def is_system_class(self, class_name):
        if class_name in self.system_classes:
            return True
        if class_name and class_name.startswith(self.safe_prefixes):
            return True
        return False


# ──────────────────────────────────────────────
# JNI 目标管理
# ──────────────────────────────────────────────
class _JniTargetManager:
    def __init__(self):
        self.targets = set()

    def add_from_file(self, path):
        if not os.path.exists(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for val in data.values():
                c = val.get('className')
                n = val.get('name')
                if c and n:
                    self.targets.add(f"{c}::{n}".replace(" ", ""))
        except Exception as e:
            logger.warning(f"    解析 JSON 出错: {e}")

    def is_target(self, node_str):
        cn, mn = _extract_class_and_method(node_str)
        if cn and mn:
            return f"{cn}::{mn}".replace(" ", "") in self.targets
        return False


# ──────────────────────────────────────────────
# 调用图处理
# ──────────────────────────────────────────────
class _CallGraphProcessor:
    def __init__(self, api_mgr: APIManager, target_mgr: _JniTargetManager):
        self.api_mgr = api_mgr
        self.target_mgr = target_mgr
        self.raw_graph = {}
        self.simplified_graph = {}
        self.relevant_nodes = set()

    def load_graph(self, graph_file):
        if not os.path.exists(graph_file):
            return
        with open(graph_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        current_caller = None
        for line in lines:
            s = line.strip()
            if not s:
                current_caller = None
                continue
            if s.startswith('=') or s.startswith('应用') or s.startswith('包名') \
                    or s.startswith('格式') or s.startswith('调用') or s.startswith('以下'):
                continue
            if s.startswith('-->'):
                if current_caller:
                    callee = s[3:].strip()
                    self.raw_graph.setdefault(current_caller, set()).add(callee)
            elif ' :: ' in s:
                current_caller = s

    def _is_system_node(self, node_str):
        if self.target_mgr.is_target(node_str):
            return False
        cn = _extract_class_name(node_str)
        return self.api_mgr.is_system_class(cn) if cn else False

    def simplify_graph(self):
        memo = {}

        def dfs_sys(node, visited):
            if node in memo:
                return memo[node]
            if node in visited:
                return set()
            visited.add(node)
            result = set()
            for child in self.raw_graph.get(node, set()):
                if not self._is_system_node(child):
                    result.add(child)
                else:
                    result.update(dfs_sys(child, visited))
            visited.remove(node)
            memo[node] = result
            return result

        new_graph = {}
        for caller in self.raw_graph:
            if self._is_system_node(caller):
                continue
            targets = set()
            for callee in self.raw_graph.get(caller, set()):
                if not self._is_system_node(callee):
                    targets.add(callee)
                else:
                    targets.update(dfs_sys(callee, set()))
            if targets:
                new_graph[caller] = targets
        self.simplified_graph = new_graph

    def prune_relevant_paths(self):
        active = set()
        for u in self.simplified_graph:
            if self.target_mgr.is_target(u):
                active.add(u)
            for v in self.simplified_graph[u]:
                if self.target_mgr.is_target(v):
                    active.add(v)
        if not active:
            self.relevant_nodes = set()
            return

        reverse = {}
        for u, vs in self.simplified_graph.items():
            for v in vs:
                reverse.setdefault(v, set()).add(u)

        # 上游
        up = set(active)
        q = list(active)
        vis = set(active)
        while q:
            cur = q.pop(0)
            for p in reverse.get(cur, []):
                if p not in vis:
                    vis.add(p); up.add(p); q.append(p)

        # 下游
        down = set(active)
        q = list(active)
        vis = set(active)
        while q:
            cur = q.pop(0)
            for c in self.simplified_graph.get(cur, []):
                if c not in vis:
                    vis.add(c); down.add(c); q.append(c)

        self.relevant_nodes = up | down

    def write_stacks(self, output_path):
        indeg = {n: 0 for n in self.relevant_nodes}
        for u in self.relevant_nodes:
            for v in self.simplified_graph.get(u, []):
                if v in indeg:
                    indeg[v] += 1
        starts = [n for n, d in indeg.items() if d == 0] or list(self.relevant_nodes)

        count = 0
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("=== Targeted Call Stacks ===\n\n")

            def dfs(node, stack, visited, seen_target):
                nonlocal count
                if node in visited:
                    if seen_target:
                        count += 1
                        f.write(f"Stack #{count} [Cycle]\n")
                        f.write("    " + " ->\n    ".join(stack + [node]) + "\n\n")
                    return
                stack.append(node)
                visited.add(node)
                seen = seen_target or self.target_mgr.is_target(node)
                children = [c for c in self.simplified_graph.get(node, []) if c in self.relevant_nodes]
                if not children:
                    if seen:
                        count += 1
                        f.write(f"Stack #{count}\n")
                        f.write("    " + " ->\n    ".join(stack) + "\n\n")
                else:
                    for c in children:
                        dfs(c, stack, visited, seen)
                stack.pop()
                visited.remove(node)

            for s in starts:
                dfs(s, [], set(), False)
        return count


# ──────────────────────────────────────────────
# 公开接口
# ──────────────────────────────────────────────
def extract_stacks(ctx: dict, api_manager: APIManager) -> None:
    t0 = time.time()
    sample_id = ctx["sample_id"]
    work_dir = ctx["work_dir"]

    graph_path = ctx.get("call_graph_path")
    if not graph_path or not os.path.isfile(graph_path):
        logger.warning(f"[Module5] {sample_id}: 无调用图，跳过")
        ctx["status"]["module5"] = "skipped"
        return

    # JNI 函数文件
    json_files = glob.glob(os.path.join(work_dir, "*.so.funcs.json"))
    if not json_files:
        logger.warning(f"[Module5] {sample_id}: 无 JNI 映射文件，跳过")
        ctx["status"]["module5"] = "skipped"
        return

    logger.info(f"[Module5] 提取调用栈: {sample_id}")

    target_mgr = _JniTargetManager()
    for jf in json_files:
        target_mgr.add_from_file(jf)
    if not target_mgr.targets:
        ctx["status"]["module5"] = "skipped"
        return

    repacked_dir = os.path.dirname(graph_path)

    # ── 去噪版本 ──
    proc = _CallGraphProcessor(api_manager, target_mgr)
    proc.load_graph(graph_path)
    proc.simplify_graph()
    proc.prune_relevant_paths()
    out1 = os.path.join(repacked_dir, "targeted_jni_stacks.txt")
    c1 = proc.write_stacks(out1)
    ctx["stacks_path"] = out1

    # ── 完整版本 ──
    proc_full = _CallGraphProcessor(api_manager, target_mgr)
    proc_full.load_graph(graph_path)
    proc_full.simplified_graph = proc_full.raw_graph
    proc_full.prune_relevant_paths()
    out2 = os.path.join(repacked_dir, "targeted_jni_stacks_full.txt")
    c2 = proc_full.write_stacks(out2)
    ctx["stacks_full_path"] = out2

    ctx["status"]["module5"] = "success"
    ctx["timings"]["module5"] = round(time.time() - t0, 3)
    logger.info(f"[Module5] {sample_id}: 去噪 {c1} 条, 完整 {c2} 条")