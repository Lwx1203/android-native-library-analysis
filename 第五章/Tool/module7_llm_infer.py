# -*- coding: utf-8 -*-
"""
模块 7 —— 大语言模型推断模块
职责：将语义标注调用栈转化为模板化提示词，调用 LLM 推断函数功能
"""

import os
import json
import time
import logging

logger = logging.getLogger("pipeline.module7")

SYSTEM_PROMPT = (
    "你是一位精通安卓逆向工程、JNI机制和程序分析的专家，"
    "擅长根据跨语言调用上下文推断目标函数的功能。"
)


def _build_stack_text(call_stacks: list) -> str:
    all_parts = []
    for idx, stack in enumerate(call_stacks):
        nodes = stack.get("annotated_nodes", [])
        if not nodes:
            continue
        lines = []
        for node in nodes:
            line = (
                f"[{node.get('label', 'Unknown')}] "
                f"{node.get('return_type', 'void')} "
                f"{node.get('class_short_name', 'Unknown')} :: "
                f"{node.get('method_name', 'unknown')}"
                f"({node.get('params', '')}) "
                f"(W={node.get('weight', 0.0):.2f})"
            )
            lines.append(line)
        text = "\n    -> ".join(lines)
        if len(call_stacks) > 1:
            text = f"调用栈 {idx + 1}:\n{text}"
        all_parts.append(text)
    return "\n\n".join(all_parts)


def _build_prompt(func_info: dict) -> str:
    library_name = func_info.get("source_so", "unknown")
    class_name = func_info.get("class_name", "")
    method_name = func_info.get("method_name", "")
    descriptor = func_info.get("descriptor", "")
    function_name = func_info.get("function_name", "")

    target_sig = f"{class_name} -> {method_name} {descriptor}"
    stack_text = _build_stack_text(func_info.get("call_stacks", []))

    parts = [
        (
            f"[Analysis Target]\n"
            f"目标本地库：{library_name}\n"
            f"目标函数：{target_sig}\n"
            f"JNI入口函数名：{function_name}"
        ),
        (
            "[Context]\n"
            "下面给出的是围绕目标函数构造的语义标注调用栈。"
            "每个节点包含语义域标签、函数签名及权重信息：\n"
            "  Intent Domain：表示业务触发背景\n"
            "  Target JNI Anchor：表示目标函数本身\n"
            "  Core Execution Domain：表示本地层核心执行行为\n"
            "  Interaction Domain：表示与托管层或系统环境的交互行为\n\n"
            f"语义标注调用栈：\n{stack_text}"
        ),
        (
            "[Task Instruction]\n"
            "请仅输出一句话，概括目标函数的主要功能，"
            "不要解释过程，不要分点，不要输出额外内容。"
        ),
    ]
    return "\n\n".join(parts)


def _call_llm(client, model: str, user_prompt: str, config) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=config.llm_temperature,
        max_tokens=config.llm_max_tokens,
    )
    return response.choices[0].message.content.strip()


# ──────────────────────────────────────────────
# 公开接口
# ──────────────────────────────────────────────
def infer(ctx: dict, client, config) -> None:
    """
    client: openai.OpenAI 实例（已配置 base_url 和 api_key）
    """
    t0 = time.time()
    sample_id = ctx["sample_id"]
    work_dir = ctx["work_dir"]

    func_json = ctx.get("functions_json_path")
    if not func_json or not os.path.isfile(func_json):
        logger.warning(f"[Module7] {sample_id}: 无 functions.json，跳过")
        ctx["status"]["module7"] = "skipped"
        return

    logger.info(f"[Module7] LLM 推断: {sample_id}")

    with open(func_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    functions = data.get("functions", [])
    results = []

    for func in functions:
        func_name = func.get("function_name", "unknown")
        prompt = _build_prompt(func)

        try:
            answer = _call_llm(client, config.llm_model, prompt, config)
            status = "success"
            logger.info(f"    {func_name} -> {answer[:80]}")
        except Exception as e:
            answer = ""
            status = f"error: {e}"
            logger.error(f"    {func_name} 调用失败: {e}")

        results.append({
            "function_name": func_name,
            "class_name": func.get("class_name", ""),
            "method_name": func.get("method_name", ""),
            "descriptor": func.get("descriptor", ""),
            "source_so": func.get("source_so", ""),
            "call_stacks_count": func.get("call_stacks_count", 0),
            "prompt": prompt,
            "result": answer,
            "status": status,
        })

        time.sleep(config.llm_delay)

    output = {
        "app": sample_id,
        "model": config.llm_model,
        "total_functions": len(results),
        "success_count": sum(1 for r in results if r["status"] == "success"),
        "error_count": sum(1 for r in results if r["status"] != "success"),
        "results": results,
    }

    out_path = os.path.join(work_dir, "llm_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    ctx["llm_results_path"] = out_path
    ctx["status"]["module7"] = "success"
    ctx["timings"]["module7"] = round(time.time() - t0, 3)
    logger.info(
        f"[Module7] {sample_id}: 成功 {output['success_count']}/{output['total_functions']}"
    )