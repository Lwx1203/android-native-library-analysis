# -*- coding: utf-8 -*-
"""
Evaluate BLEU for code summarization outputs in a way that is close to BLEU-CN
commonly used in code summarization papers.

Input:
    groundtruth_final_en.xlsx

Expected columns:
    函数功能_英文   -> reference
    本方法_英文     -> ours
    baseline_英文   -> baseline

Outputs:
    results_summary.csv
    results_per_example.csv
"""

import re
import math
import argparse
import pandas as pd
import numpy as np
from nltk.translate.bleu_score import corpus_bleu, sentence_bleu, SmoothingFunction


# -----------------------------
# 1. Text normalization / tokenization
# -----------------------------
def normalize_text(text: str) -> str:
    if pd.isna(text):
        return ""
    text = str(text).strip().lower()
    # normalize multiple spaces
    text = re.sub(r"\s+", " ", text)
    return text


def tokenize_basic(text: str):
    """
    A practical tokenizer for English summaries:
    split words and punctuation.
    Example:
      "Rounds the values of a tensor, element-wise."
      -> ['rounds', 'the', 'values', 'of', 'a', 'tensor', ',', 'element', '-', 'wise', '.']
    """
    text = normalize_text(text)
    if not text:
        return []
    return re.findall(r"[A-Za-z0-9_]+|[^\w\s]", text)


def tokenize_whitespace(text: str):
    """
    Simpler tokenizer: normalize then split by whitespace.
    """
    text = normalize_text(text)
    if not text:
        return []
    return text.split()


def get_tokenizer(name: str):
    if name == "basic":
        return tokenize_basic
    elif name == "whitespace":
        return tokenize_whitespace
    else:
        raise ValueError(f"Unsupported tokenizer: {name}")


# -----------------------------
# Helper: build BLEU weights for BLEU-N
# -----------------------------
def get_bleu_weights(n: int):
    """
    Return uniform weights tuple for BLEU-N.
    BLEU-1 -> (1.0, 0, 0, 0)
    BLEU-2 -> (0.5, 0.5, 0, 0)
    BLEU-3 -> (0.333, 0.333, 0.333, 0)
    BLEU-4 -> (0.25, 0.25, 0.25, 0.25)
    """
    if n < 1 or n > 4:
        raise ValueError("bleu_n must be 1, 2, 3, or 4")
    w = tuple([1.0 / n] * n + [0.0] * (4 - n))
    return w


# -----------------------------
# 2. BLEU calculation
# -----------------------------
def compute_corpus_bleu(references, hypotheses, weights, smoothing="method4"):
    """
    references: list of list of reference_tokens
        shape expected by corpus_bleu: [[ref1_tokens], [ref2_tokens], ...]
    hypotheses: list of hyp_tokens
    """
    smooth_fn = getattr(SmoothingFunction(), smoothing)
    score = corpus_bleu(
        references,
        hypotheses,
        weights=weights,
        smoothing_function=smooth_fn
    )
    return score * 100.0


def compute_sentence_bleu_scores(ref_texts, hyp_texts, tokenizer, weights, smoothing="method4"):
    """
    Returns list of sentence-level BLEU scores (0-100).
    """
    smooth_fn = getattr(SmoothingFunction(), smoothing)

    scores = []
    for ref, hyp in zip(ref_texts, hyp_texts):
        ref_tokens = tokenizer(ref)
        hyp_tokens = tokenizer(hyp)

        if len(hyp_tokens) == 0:
            scores.append(0.0)
            continue

        score = sentence_bleu(
            [ref_tokens],
            hyp_tokens,
            weights=weights,
            smoothing_function=smooth_fn
        )
        scores.append(score * 100.0)
    return scores


# -----------------------------
# 3. Data loading / cleaning
# -----------------------------
def load_data(file_path):
    df = pd.read_excel(file_path)

    required_cols = ["函数功能_英文", "本方法_英文", "baseline_英文"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    # Keep optional metadata if exists
    meta_cols = []
    for c in ["应用名", "函数名"]:
        if c in df.columns:
            meta_cols.append(c)

    # Fill NaN with empty string for safer evaluation
    for col in required_cols:
        df[col] = df[col].fillna("")

    return df, meta_cols


# -----------------------------
# 4. Evaluation main logic
# -----------------------------
def evaluate(df, tokenizer_name="basic", bleu_n=1, smoothing="method4"):
    tokenizer = get_tokenizer(tokenizer_name)
    weights = get_bleu_weights(bleu_n)

    refs_text = df["函数功能_英文"].tolist()
    ours_text = df["本方法_英文"].tolist()
    base_text = df["baseline_英文"].tolist()

    # corpus BLEU input format
    refs_tokens = [[tokenizer(x)] for x in refs_text]
    ours_tokens = [tokenizer(x) for x in ours_text]
    base_tokens = [tokenizer(x) for x in base_text]

    # corpus-level BLEU
    corpus_bleu_ours = compute_corpus_bleu(refs_tokens, ours_tokens, weights=weights, smoothing=smoothing)
    corpus_bleu_base = compute_corpus_bleu(refs_tokens, base_tokens, weights=weights, smoothing=smoothing)

    # sentence-level BLEU
    sent_bleu_ours = compute_sentence_bleu_scores(refs_text, ours_text, tokenizer, weights=weights, smoothing=smoothing)
    sent_bleu_base = compute_sentence_bleu_scores(refs_text, base_text, tokenizer, weights=weights, smoothing=smoothing)

    avg_sent_bleu_ours = float(np.mean(sent_bleu_ours)) if sent_bleu_ours else 0.0
    avg_sent_bleu_base = float(np.mean(sent_bleu_base)) if sent_bleu_base else 0.0

    return {
        "corpus_bleu_ours": corpus_bleu_ours,
        "corpus_bleu_base": corpus_bleu_base,
        "corpus_bleu_gain": corpus_bleu_ours - corpus_bleu_base,
        "avg_sent_bleu_ours": avg_sent_bleu_ours,
        "avg_sent_bleu_base": avg_sent_bleu_base,
        "avg_sent_bleu_gain": avg_sent_bleu_ours - avg_sent_bleu_base,
        "sent_bleu_ours": sent_bleu_ours,
        "sent_bleu_base": sent_bleu_base,
    }


# -----------------------------
# 5. Save outputs
# -----------------------------
def save_results(df, meta_cols, eval_result, tokenizer_name, bleu_n, smoothing,
                 summary_path="results_summary.csv",
                 per_example_path="results_per_example.csv"):

    # Summary
    summary_df = pd.DataFrame([{
        "num_samples": len(df),
        "tokenizer": tokenizer_name,
        "bleu_n": bleu_n,
        "smoothing": smoothing,
        "corpus_bleu_ours": round(eval_result["corpus_bleu_ours"], 4),
        "corpus_bleu_baseline": round(eval_result["corpus_bleu_base"], 4),
        "corpus_bleu_gain": round(eval_result["corpus_bleu_gain"], 4),
        "avg_sentence_bleu_ours": round(eval_result["avg_sent_bleu_ours"], 4),
        "avg_sentence_bleu_baseline": round(eval_result["avg_sent_bleu_base"], 4),
        "avg_sentence_bleu_gain": round(eval_result["avg_sent_bleu_gain"], 4),
    }])
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

    # Per-example
    out_df = df.copy()
    out_df["sentence_bleu_ours"] = eval_result["sent_bleu_ours"]
    out_df["sentence_bleu_baseline"] = eval_result["sent_bleu_base"]
    out_df["sentence_bleu_gain"] = out_df["sentence_bleu_ours"] - out_df["sentence_bleu_baseline"]

    per_cols = meta_cols + [
        "函数功能_英文",
        "本方法_英文",
        "baseline_英文",
        "sentence_bleu_ours",
        "sentence_bleu_baseline",
        "sentence_bleu_gain",
    ]
    out_df = out_df[per_cols]
    out_df.to_csv(per_example_path, index=False, encoding="utf-8-sig")


# -----------------------------
# 6. Pretty print
# -----------------------------
def print_report(eval_result, num_samples, tokenizer_name, bleu_n, smoothing):
    print("=" * 60)
    print(f"BLEU-{bleu_n} Evaluation Report")
    print("=" * 60)
    print(f"Samples                : {num_samples}")
    print(f"Tokenizer              : {tokenizer_name}")
    print(f"BLEU-N                 : {bleu_n}")
    print(f"Weights                : {get_bleu_weights(bleu_n)}")
    print(f"Smoothing              : {smoothing}")
    print("-" * 60)
    print(f"Ours Corpus BLEU-{bleu_n}     : {eval_result['corpus_bleu_ours']:.2f}")
    print(f"Base Corpus BLEU-{bleu_n}     : {eval_result['corpus_bleu_base']:.2f}")
    print(f"Corpus BLEU Gain       : {eval_result['corpus_bleu_gain']:+.2f}")
    print("-" * 60)
    print(f"Ours Avg Sent BLEU-{bleu_n}   : {eval_result['avg_sent_bleu_ours']:.2f}")
    print(f"Base Avg Sent BLEU-{bleu_n}   : {eval_result['avg_sent_bleu_base']:.2f}")
    print(f"Avg Sent BLEU Gain     : {eval_result['avg_sent_bleu_gain']:+.2f}")
    print("=" * 60)


# -----------------------------
# 7. Main
# -----------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=str, default="/Users/liuwenxuan/Desktop/验证结果/groundtruth_final_en.xlsx",
                        help="Path to input Excel file")
    parser.add_argument("--tokenizer", type=str, default="basic",
                        choices=["basic", "whitespace"],
                        help="Tokenization mode")
    parser.add_argument("--bleu_n", type=int, default=1,
                        choices=[1, 2, 3, 4],
                        help="BLEU-N: 1 for unigram, 4 for standard BLEU-4 (default: 1)")
    parser.add_argument("--smoothing", type=str, default="method4",
                        choices=["method0", "method1", "method2", "method3", "method4", "method5", "method6", "method7"],
                        help="NLTK smoothing method")
    parser.add_argument("--summary_out", type=str, default="results_summary.csv")
    parser.add_argument("--per_example_out", type=str, default="results_per_example.csv")
    args = parser.parse_args()

    df, meta_cols = load_data(args.file)
    eval_result = evaluate(df, tokenizer_name=args.tokenizer, bleu_n=args.bleu_n, smoothing=args.smoothing)

    print_report(eval_result, len(df), args.tokenizer, args.bleu_n, args.smoothing)
    save_results(
        df=df,
        meta_cols=meta_cols,
        eval_result=eval_result,
        tokenizer_name=args.tokenizer,
        bleu_n=args.bleu_n,
        smoothing=args.smoothing,
        summary_path=args.summary_out,
        per_example_path=args.per_example_out,
    )


if __name__ == "__main__":
    main()