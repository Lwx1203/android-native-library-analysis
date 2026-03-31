# -*- coding: utf-8 -*-
"""全局管线配置"""

import os


class PipelineConfig:

    def __init__(self):
        # ── 输入：单个 APK 文件路径或包含 APK 的目录 ──
        self.input_path = r"H:"

        # ── 输出根目录 ──
        self.output_root = r"H:"

        # ── Docker ──
        self.docker_image = "nativesummary/nativesummary"
        self.docker_timeout = 3600  # 秒

        # ── Android API 文件（Module 5 去噪） ──
        self.api_file = r"ALL_COMBINED_ANDROID_APIS.txt"

        # ── LLM 配置（Module 7） ──
        self.llm_api_key = "sk-"
        self.llm_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.llm_model = "qwen-plus"
        self.llm_temperature = 0.3
        self.llm_max_tokens = 256
        self.llm_delay = 1.0  # 请求间隔(秒)

        # ── 过滤选项 ──
        self.keep_latest_version_only = True  # 同包名只保留最新版本

        # ── 杂项 ──
        self.max_stacks_file_mb = 200
        self.skip_existing = True  # 跳过已有结果

    # ── 便捷路径方法 ──
    def work_dir_for(self, sample_id: str) -> str:
        return os.path.join(self.output_root, sample_id)