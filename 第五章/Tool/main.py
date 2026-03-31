# -*- coding: utf-8 -*-
"""
主程序入口 —— APK 跨语言函数功能识别管线
用法:
    python main.py                                  # 使用 config.py 默认配置
    python main.py --input /path/to/apk_or_dir      # 指定输入
    python main.py --input app.apk --output ./out    # 指定输入输出
    python main.py --skip-llm                        # 跳过 LLM 推断
"""

import os
import sys
import time
import json
import logging
import argparse


from config import PipelineConfig
import module1_preprocess as m1
import module2_native_detect as m2
import module3_unify as m3
import module4_callgraph as m4
import module5_stack_extract as m5
import module6_annotation as m6
import module7_llm_infer as m7
import module8_result_mgmt as m8


def setup_logging(output_root: str):
    os.makedirs(output_root, exist_ok=True)
    log_path = os.path.join(output_root, "_pipeline.log")

    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_path, encoding="utf-8"),
    ]
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


def parse_args():
    parser = argparse.ArgumentParser(description="APK 跨语言函数功能识别管线")
    parser.add_argument("--input", type=str, default=None,
                        help="输入路径（APK 文件或目录）")
    parser.add_argument("--output", type=str, default=None,
                        help="输出根目录")
    parser.add_argument("--api-file", type=str, default=None,
                        help="Android API 文件路径")
    parser.add_argument("--llm-model", type=str, default=None,
                        help="LLM 模型名称")
    parser.add_argument("--llm-api-key", type=str, default=None,
                        help="LLM API Key")
    parser.add_argument("--skip-llm", action="store_true", default=False,
                        help="跳过 LLM 推断（模块 7）")
    parser.add_argument("--skip-docker", action="store_true", default=False,
                        help="跳过 Docker 统一化（模块 3），适用于已有统一化结果")
    parser.add_argument("--no-skip-existing", action="store_true", default=False,
                        help="不跳过已有结果，全部重新处理")
    return parser.parse_args()


def apply_args_to_config(args, config: PipelineConfig):
    if args.input:
        config.input_path = args.input
    if args.output:
        config.output_root = args.output
    if args.api_file:
        config.api_file = args.api_file
    if args.llm_model:
        config.llm_model = args.llm_model
    if args.llm_api_key:
        config.llm_api_key = args.llm_api_key
    if args.no_skip_existing:
        config.skip_existing = False


def main():
    args = parse_args()
    config = PipelineConfig()
    apply_args_to_config(args, config)

    setup_logging(config.output_root)
    logger = logging.getLogger("pipeline.main")

    logger.info("=" * 70)
    logger.info("  APK 跨语言函数功能识别管线启动")
    logger.info("=" * 70)
    logger.info(f"  输入路径:   {config.input_path}")
    logger.info(f"  输出目录:   {config.output_root}")
    logger.info(f"  LLM 模型:   {config.llm_model}")
    logger.info(f"  跳过 LLM:   {args.skip_llm}")
    logger.info(f"  跳过 Docker: {args.skip_docker}")
    logger.info("")

    pipeline_start = time.time()

    # ════════════════════════════════════════
    # 模块 1: APK 预处理
    # ════════════════════════════════════════
    logger.info("[阶段 1/8] APK 预处理...")
    t = time.time()
    contexts = m1.preprocess(config.input_path, config)
    logger.info(f"  完成: {len(contexts)} 个样本 ({time.time()-t:.1f}s)")

    if not contexts:
        logger.error("无有效输入样本，退出。")
        return

    # ════════════════════════════════════════
    # 模块 2: 本地库检测
    # ════════════════════════════════════════
    logger.info(f"\n[阶段 2/8] 本地库检测...")
    t = time.time()
    for ctx in contexts:
        m2.detect(ctx)

    # 过滤无本地库的样本
    before = len(contexts)
    active_contexts = [ctx for ctx in contexts if ctx.get("has_native_libs")]
    skipped = before - len(active_contexts)
    if skipped > 0:
        logger.info(f"  跳过 {skipped} 个无本地库的样本")
    logger.info(f"  完成: {len(active_contexts)}/{before} 个样本含本地库 ({time.time()-t:.1f}s)")

    if not active_contexts:
        logger.warning("所有样本均无本地库，生成报告后退出。")
        for ctx in contexts:
            m8.generate_app_report(ctx)
        m8.generate_global_report(contexts, config)
        return

    # ════════════════════════════════════════
    # 模块 3: 代码统一化
    # ════════════════════════════════════════
    if not args.skip_docker:
        logger.info(f"\n[阶段 3/8] 代码统一化 (NativeSummary Docker)...")
        t = time.time()
        for i, ctx in enumerate(active_contexts):
            logger.info(f"  [{i+1}/{len(active_contexts)}] {ctx['sample_id']}")
            m3.unify(ctx, config)
        logger.info(f"  完成 ({time.time()-t:.1f}s)")
    else:
        logger.info(f"\n[阶段 3/8] 跳过 Docker 统一化 (--skip-docker)")
        import glob as _glob
        for ctx in active_contexts:
            wd = ctx["work_dir"]
            ua = os.path.join(wd, "repacked_apks", "target.apk")
            if os.path.isfile(ua):
                ctx["unified_apk_path"] = ua
                ctx["jni_func_files"] = [
                    os.path.basename(p)
                    for p in _glob.glob(os.path.join(wd, "*.so.funcs.json"))
                ]
                ctx["status"]["module3"] = "skipped_by_flag"
            else:
                ctx["status"]["module3"] = "skipped_no_file"

    # 过滤无统一化 APK 的样本
    active = [ctx for ctx in active_contexts if ctx.get("unified_apk_path")]
    logger.info(f"  有统一化 APK 的样本: {len(active)}/{len(active_contexts)}")

    if not active:
        logger.warning("无样本生成统一化 APK，生成报告后退出。")
        for ctx in contexts:
            m8.generate_app_report(ctx)
        m8.generate_global_report(contexts, config)
        return

    # ════════════════════════════════════════
    # 模块 4: 调用图构建
    # ════════════════════════════════════════
    logger.info(f"\n[阶段 4/8] 调用图构建 (Androguard)...")
    t = time.time()
    for i, ctx in enumerate(active):
        logger.info(f"  [{i+1}/{len(active)}] {ctx['sample_id']}")
        m4.build_call_graph(ctx)
    logger.info(f"  完成 ({time.time()-t:.1f}s)")

    # ════════════════════════════════════════
    # 模块 5: 调用栈提取与去噪
    # ════════════════════════════════════════
    logger.info(f"\n[阶段 5/8] 调用栈提取与去噪...")
    t = time.time()
    api_manager = m5.APIManager(config.api_file)
    for i, ctx in enumerate(active):
        logger.info(f"  [{i+1}/{len(active)}] {ctx['sample_id']}")
        m5.extract_stacks(ctx, api_manager)
    logger.info(f"  完成 ({time.time()-t:.1f}s)")

    # ════════════════════════════════════════
    # 模块 6: 语义标注与权重计算
    # ════════════════════════════════════════
    logger.info(f"\n[阶段 6/8] 语义标注与权重计算...")
    t = time.time()
    for i, ctx in enumerate(active):
        logger.info(f"  [{i+1}/{len(active)}] {ctx['sample_id']}")
        m6.annotate(ctx)
    logger.info(f"  完成 ({time.time()-t:.1f}s)")

    # ════════════════════════════════════════
    # 模块 7: 大语言模型推断
    # ════════════════════════════════════════
    if not args.skip_llm:
        logger.info(f"\n[阶段 7/8] 大语言模型推断...")
        t = time.time()
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=config.llm_api_key,
                base_url=config.llm_base_url,
            )
        except ImportError:
            logger.error("openai 库未安装，跳过 LLM 推断。请执行: pip install openai")
            client = None

        if client:
            for i, ctx in enumerate(active):
                if ctx.get("functions_json_path"):
                    logger.info(f"  [{i+1}/{len(active)}] {ctx['sample_id']}")
                    m7.infer(ctx, client, config)
        logger.info(f"  完成 ({time.time()-t:.1f}s)")
    else:
        logger.info(f"\n[阶段 7/8] 跳过 LLM 推断 (--skip-llm)")
        for ctx in active:
            ctx["status"]["module7"] = "skipped_by_flag"

    # ════════════════════════════════════════
    # 模块 8: 结果管理与展示
    # ════════════════════════════════════════
    logger.info(f"\n[阶段 8/8] 生成报告...")
    t = time.time()

    # 为所有样本（包括被过滤的无本地库样本）生成报告
    for ctx in contexts:
        m8.generate_app_report(ctx)

    m8.generate_global_report(contexts, config)
    logger.info(f"  完成 ({time.time()-t:.1f}s)")

    total_elapsed = time.time() - pipeline_start
    logger.info(f"\n管线总耗时: {total_elapsed:.1f} 秒 ({total_elapsed/60:.1f} 分钟)")


if __name__ == "__main__":
    main()