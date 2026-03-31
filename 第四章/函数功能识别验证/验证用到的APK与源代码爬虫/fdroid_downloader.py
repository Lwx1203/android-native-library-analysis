import requests
import os
import time
from tqdm import tqdm

# --- 核心配置 ---
BASE_PATH = r"F:\fdroid"
BASE_URL = "https://mirrors.tuna.tsinghua.edu.cn/fdroid/repo/"
INDEX_URL = BASE_URL + "index-v1.json"

# 保存路径
APK_SAVE_DIR = os.path.join(BASE_PATH, "apks")
SOURCE_LOG = os.path.join(BASE_PATH, "source_links.txt")

# 自动创建目录
if not os.path.exists(APK_SAVE_DIR):
    os.makedirs(APK_SAVE_DIR, exist_ok=True)


def download_with_progress(url, filename):
    """
    下载文件并显示进度条
    包含断点续传逻辑：如果文件存在且不为空，则跳过
    """
    if os.path.exists(filename) and os.path.getsize(filename) > 0:
        # 文件已存在，跳过
        return

    try:
        # 设置30秒超时，防止网络卡死
        response = requests.get(url, stream=True, timeout=30)
        total_size = int(response.headers.get('content-length', 0))

        # 使用 tqdm 显示下载进度
        with open(filename, 'wb') as f, tqdm(
                desc=os.path.basename(filename)[:20],
                total=total_size,
                unit='iB',
                unit_scale=True,
                unit_divisor=1024,
                leave=False  # 下载完一个清除进度条，保持界面整洁
        ) as bar:
            for data in response.iter_content(chunk_size=1024):
                size = f.write(data)
                bar.update(size)
    except Exception as e:
        print(f"\n[Error] 下载失败: {os.path.basename(filename)} | 原因: {e}")


def main():
    print(f"1. 正在从清华源获取索引数据 (请耐心等待)...")
    try:
        resp = requests.get(INDEX_URL, timeout=120)
        data = resp.json()
    except Exception as e:
        print(f"获取索引失败，请检查网络: {e}")
        return

    # --- 解析数据结构 ---
    apps = data.get('apps', [])
    packages_dict = data.get('packages', {})

    # 1. 提取所有 APK 对象 (展平列表)
    all_apk_objects = []
    for package_versions_list in packages_dict.values():
        if isinstance(package_versions_list, list):
            for version in package_versions_list:
                all_apk_objects.append(version)

    print(f"   => 索引解析完毕，共发现 {len(all_apk_objects)} 个 APK 文件。")

    # 2. 提取源码链接并保存到 txt
    print(f"2. 正在更新源码链接列表...")
    source_map = {}
    for app in apps:
        app_id = app.get('id') or app.get('packageName')
        if app_id:
            source_map[app_id] = app.get('sourceCode', '无源码链接')

    with open(SOURCE_LOG, "w", encoding="utf-8") as f:
        for app_id, src in source_map.items():
            f.write(f"ID: {app_id} | SRC: {src}\n")
    print(f"   => 源码链接已保存至: {SOURCE_LOG}")

    # 3. 开始全量下载
    print(f"\n3. 开始全量下载 ({len(all_apk_objects)} 个文件)...")
    print("   提示: 已开启断点续传，已下载的文件会自动跳过。")
    print("   按 Ctrl+C 可随时停止脚本。\n")

    success_count = 0

    for i, pkg in enumerate(all_apk_objects):
        apk_name = pkg.get('apkName')
        if not apk_name:
            continue

        apk_url = BASE_URL + apk_name
        save_path = os.path.join(APK_SAVE_DIR, apk_name)

        # 打印进度概览 (每100个打印一次，或者正在下载时显示)
        # 这里为了直观，我们只在开始下载时打印
        if not os.path.exists(save_path):
            print(f"[{i + 1}/{len(all_apk_objects)}] 下载: {apk_name}")
            download_with_progress(apk_url, save_path)
        else:
            # 如果想看跳过的信息，取消下面这行的注释
            print(f"[{i+1}/{len(all_apk_objects)}] 跳过: {apk_name}")
            pass

    print("\n--- 所有 APK 下载任务完成 ---")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户手动停止了程序。")