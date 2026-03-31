# -*- coding: utf-8 -*-
"""
LLM-as-Judge 盲评脚本（Qwen-Plus）
两种模式：
  1. 独立盲评：每条候选单独打分，不透露方法来源
  2. 成对盲评：两条候选随机标为 A/B，让模型选更好的
依赖：pip install openai pandas openpyxl
"""

import pandas as pd
import numpy as np
import json
import time
import random
from openai import OpenAI

# ============================================================
# 配置
# ============================================================
API_KEY  = "sk-"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL    = "qwen-plus"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# ============================================================
# 模式一：独立盲评 Prompt（不透露任何方法信息）
# ============================================================
INDEPENDENT_PROMPT = """你是一个代码理解专家。请根据参考的函数功能描述（Ground Truth），评估候选描述的质量。

## 评分标准（1-5分）：
- 5分：语义完全一致，覆盖了所有关键信息
- 4分：语义基本一致，遗漏了少量次要信息
- 3分：部分一致，捕捉到了核心功能但有明显遗漏或偏差
- 2分：仅有少量相关性，大部分信息不正确或缺失
- 1分：完全不相关或完全错误

## 输入：
**函数名**：{func_name}
**Ground Truth**：{reference}
**候选描述**：{candidate}

## 输出要求：
请严格按以下 JSON 格式输出，不要输出任何其他内容：
{{"score": <1-5的整数>, "reason": "<简要理由>"}}"""

# ============================================================
# 模式二：成对盲评 Prompt（随机分配 A/B）
# ============================================================
PAIRWISE_PROMPT = """你是一个代码理解专家。现在有一个函数的功能描述（Ground Truth），以及两个不同系统生成的候选描述 A 和 B。
请判断哪个候选描述更准确地反映了函数的实际功能。

## 评判标准：
- 语义与 Ground Truth 的一致程度
- 关键信息的覆盖完整性
- 描述的准确性（是否有错误或误导性信息）

## 输入：
**函数名**：{func_name}
**Ground Truth**：{reference}
**候选 A**：{candidate_a}
**候选 B**：{candidate_b}

## 输出要求：
请严格按以下 JSON 格式输出，不要输出任何其他内容：
{{"winner": "<A或B或Tie>", "score_a": <1-5的整数>, "score_b": <1-5的整数>, "reason": "<简要对比理由>"}}"""


# ============================================================
# 调用大模型
# ============================================================
def call_llm(prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=300,
            )
            content = resp.choices[0].message.content.strip()
            # 处理可能的 markdown 代码块包裹
            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
                content = content.rsplit("```", 1)[0]
                content = content.strip()
            return json.loads(content)
        except Exception as e:
            print(f"  重试 {attempt+1}/{max_retries}: {e}")
            time.sleep(2)
    return None


# ============================================================
# 模式一：独立盲评
# ============================================================
def run_independent_eval(df, col_func, col_ref, col_ours, col_base):
    """
    把所有候选打乱顺序逐条送评，模型完全不知道来源
    """
    print("\n" + "=" * 60)
    print("模式一：独立盲评（每条单独打分，隐藏方法来源）")
    print("=" * 60)

    # 构建评估任务列表，打乱顺序
    tasks = []
    for idx, row in df.iterrows():
        func_name = str(row[col_func])
        ref       = str(row[col_ref])
        tasks.append({
            "idx": idx, "source": "ours",
            "func_name": func_name, "ref": ref,
            "candidate": str(row[col_ours])
        })
        tasks.append({
            "idx": idx, "source": "base",
            "func_name": func_name, "ref": ref,
            "candidate": str(row[col_base])
        })

    # 打乱顺序，模型无法根据出现顺序推断来源
    random.shuffle(tasks)

    results = {}
    for i, task in enumerate(tasks):
        print(f"[{i+1}/{len(tasks)}] 评估: {task['func_name']} ({task['source']}隐藏中)")
        prompt = INDEPENDENT_PROMPT.format(
            func_name=task["func_name"],
            reference=task["ref"],
            candidate=task["candidate"]
        )
        result = call_llm(prompt)
        if result:
            key = (task["idx"], task["source"])
            results[key] = {
                "score": int(result.get("score", 0)),
                "reason": result.get("reason", "")
            }
        time.sleep(0.5)

    # 整理结果
    ours_scores, ours_reasons = [], []
    base_scores, base_reasons = [], []

    for idx in range(len(df)):
        o = results.get((idx, "ours"), {"score": None, "reason": ""})
        b = results.get((idx, "base"), {"score": None, "reason": ""})
        ours_scores.append(o["score"])
        ours_reasons.append(o["reason"])
        base_scores.append(b["score"])
        base_reasons.append(b["reason"])

    return ours_scores, ours_reasons, base_scores, base_reasons


# ============================================================
# 模式二：成对盲评
# ============================================================
def run_pairwise_eval(df, col_func, col_ref, col_ours, col_base):
    """
    每条数据把两个候选随机分配为 A/B，模型不知道哪个是哪个方法
    """
    print("\n" + "=" * 60)
    print("模式二：成对盲评（随机分配 A/B，隐藏方法来源）")
    print("=" * 60)

    ours_scores, base_scores = [], []
    ours_reasons, base_reasons = [], []
    win_counts = {"ours": 0, "base": 0, "tie": 0}
    order_records = []  # 记录每条的 A/B 分配

    for idx, row in df.iterrows():
        func_name = str(row[col_func])
        ref       = str(row[col_ref])
        ours_text = str(row[col_ours])
        base_text = str(row[col_base])

        # 随机决定 A/B 顺序
        if random.random() < 0.5:
            candidate_a, candidate_b = ours_text, base_text
            a_is = "ours"
        else:
            candidate_a, candidate_b = base_text, ours_text
            a_is = "base"

        order_records.append(a_is)
        print(f"[{idx+1}/{len(df)}] 评估: {func_name}  (A={'本方法' if a_is=='ours' else 'Baseline'}, 模型不可见)")

        prompt = PAIRWISE_PROMPT.format(
            func_name=func_name,
            reference=ref,
            candidate_a=candidate_a,
            candidate_b=candidate_b
        )
        result = call_llm(prompt)

        if result:
            score_a = int(result.get("score_a", 0))
            score_b = int(result.get("score_b", 0))
            winner  = result.get("winner", "Tie")
            reason  = result.get("reason", "")

            # 还原真实身份
            if a_is == "ours":
                ours_scores.append(score_a)
                base_scores.append(score_b)
                ours_reasons.append(reason)
                base_reasons.append(reason)
                if winner == "A":
                    win_counts["ours"] += 1
                elif winner == "B":
                    win_counts["base"] += 1
                else:
                    win_counts["tie"] += 1
            else:
                ours_scores.append(score_b)
                base_scores.append(score_a)
                ours_reasons.append(reason)
                base_reasons.append(reason)
                if winner == "A":
                    win_counts["base"] += 1
                elif winner == "B":
                    win_counts["ours"] += 1
                else:
                    win_counts["tie"] += 1
        else:
            ours_scores.append(None)
            base_scores.append(None)
            ours_reasons.append("")
            base_reasons.append("")

        time.sleep(0.5)

    return ours_scores, ours_reasons, base_scores, base_reasons, win_counts, order_records


# ============================================================
# 输出统计
# ============================================================
def print_stats(ours_scores, base_scores, mode_name, win_counts=None):
    ours_valid = [s for s in ours_scores if s is not None]
    base_valid = [s for s in base_scores if s is not None]

    print("\n" + "=" * 60)
    print(f"{mode_name} — 统计结果")
    print("=" * 60)
    print(f"{'':20} {'本文方法':>10} {'Baseline':>10}")
    print("-" * 60)
    print(f"{'平均分':20} {np.mean(ours_valid):>10.2f} {np.mean(base_valid):>10.2f}")
    print(f"{'中位数':20} {np.median(ours_valid):>10.1f} {np.median(base_valid):>10.1f}")
    print(f"{'标准差':20} {np.std(ours_valid):>10.2f} {np.std(base_valid):>10.2f}")
    print(f"{'≥4分占比':20} "
          f"{sum(1 for s in ours_valid if s >= 4)/len(ours_valid):>10.1%} "
          f"{sum(1 for s in base_valid if s >= 4)/len(base_valid):>10.1%}")
    print("-" * 60)

    print("\n分数分布：")
    for sv in [5, 4, 3, 2, 1]:
        oc = sum(1 for s in ours_valid if s == sv)
        bc = sum(1 for s in base_valid if s == sv)
        print(f"  {sv}分:  本文方法 {oc:>3} 条 ({oc/len(ours_valid):>6.1%})  |  "
              f"Baseline {bc:>3} 条 ({bc/len(base_valid):>6.1%})")

    if win_counts:
        total = sum(win_counts.values())
        print(f"\n成对对比胜负：")
        print(f"  本文方法胜: {win_counts['ours']:>3} 次 ({win_counts['ours']/total:.1%})")
        print(f"  Baseline胜: {win_counts['base']:>3} 次 ({win_counts['base']/total:.1%})")
        print(f"  平局:       {win_counts['tie']:>3} 次 ({win_counts['tie']/total:.1%})")
    print("=" * 60)


# ============================================================
# 主流程
# ============================================================
if __name__ == "__main__":
    random.seed(42)  # 固定随机种子，保证可复现

    df = pd.read_excel("/Users/liuwenxuan/Desktop/groundtruth_final.xlsx", sheet_name="Sheet1")
    df.columns = df.columns.str.strip()

    col_func = "函数名"
    col_ref  = "函数功能"
    col_ours = "本方法大模型分析结果"
    col_base = "baseline结果"

    # ---- 选择评估模式（两种都运行，或只运行一种）----
    MODE = "both"  # 可选: "independent", "pairwise", "both"

    if MODE in ("independent", "both"):
        o_sc, o_re, b_sc, b_re = run_independent_eval(
            df, col_func, col_ref, col_ours, col_base
        )
        print_stats(o_sc, b_sc, "独立盲评")

        df["Ours_IndScore"]  = o_sc
        df["Ours_IndReason"] = o_re
        df["Base_IndScore"]  = b_sc
        df["Base_IndReason"] = b_re

    if MODE in ("pairwise", "both"):
        o_sc2, o_re2, b_sc2, b_re2, wins, orders = run_pairwise_eval(
            df, col_func, col_ref, col_ours, col_base
        )
        print_stats(o_sc2, b_sc2, "成对盲评", win_counts=wins)

        df["Ours_PairScore"]  = o_sc2
        df["Ours_PairReason"] = o_re2
        df["Base_PairScore"]  = b_sc2
        df["Base_PairReason"] = b_re2
        df["PairOrder_A_is"]  = orders

    # ---- 保存结果 ----
    output_path = "llm_judge_blind_results.xlsx"
    df.to_excel(output_path, index=False)
    print(f"\n所有结果已保存到: {output_path}")