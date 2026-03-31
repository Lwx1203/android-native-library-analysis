import os
import subprocess
import time

# --- 核心配置 ---
# 你的 F-Droid 数据目录
BASE_PATH = r"H:\fdroid"
SOURCE_LIST_FILE = os.path.join(BASE_PATH, "source_links.txt")
SOURCE_SAVE_DIR = os.path.join(BASE_PATH, "source_code")

# 自动创建源码目录
if not os.path.exists(SOURCE_SAVE_DIR):
    os.makedirs(SOURCE_SAVE_DIR, exist_ok=True)


def clone_repo(app_id, repo_url):
    """
    调用系统 git 命令进行克隆
    使用 --depth 1 参数只下载最新版，极大节省空间
    """
    target_dir = os.path.join(SOURCE_SAVE_DIR, app_id)

    # 简单的断点续传：如果文件夹已存在且不为空，跳过
    if os.path.exists(target_dir) and os.listdir(target_dir):
        print(f"[跳过] {app_id} 目录已存在")
        return

    print(f"正在克隆: {app_id}")
    print(f"   地址: {repo_url}")

    try:
        # timeout=600: 单个仓库限制10分钟，防止大仓库卡死
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, target_dir],
            check=True,
            timeout=600
        )
        print(f"   [成功] {app_id}")
    except subprocess.TimeoutExpired:
        print(f"   [超时] {app_id} 下载超时，已跳过")
    except subprocess.CalledProcessError:
        print(f"   [失败] {app_id} 克隆失败 (仓库可能已删除、私有或非GitHub源网络不通)")
    except FileNotFoundError:
        print(f"   [致命错误] 未找到 git 命令！请安装 Git 并添加到环境变量。")
        raise  # 没装git就直接停止程序
    except Exception as e:
        print(f"   [异常] {e}")


def main():
    if not os.path.exists(SOURCE_LIST_FILE):
        print(f"错误: 找不到链接文件 {SOURCE_LIST_FILE}")
        print("请先运行 APK 下载脚本生成该文件。")
        return

    print(f"正在读取源码链接: {SOURCE_LIST_FILE}")
    with open(SOURCE_LIST_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    total_lines = len(lines)
    print(f"共找到 {total_lines} 条记录，准备开始全量下载源码...")
    print("提示: 已启用 gitclone.com 镜像加速 GitHub 下载。\n")

    processed_count = 0

    for line in lines:
        line = line.strip()
        if not line: continue

        # 解析格式: "ID: com.xxx | SRC: https://..."
        try:
            parts = line.split("| SRC: ")
            if len(parts) < 2: continue

            app_id = parts[0].replace("ID: ", "").strip()
            url = parts[1].strip()

            # 过滤无效链接
            if url == "无源码链接" or not url.startswith("http"):
                continue

            # --- 【核心修改】GitHub 加速逻辑 ---
            # 如果是 github 链接，自动替换为加速镜像
            if "github.com" in url:
                original_url = url
                url = url.replace("github.com", "gitclone.com/github.com")
                # 打印一下提示，让你知道加速生效了
                # print(f"   (已开启加速: {original_url} -> {url})")
            # -------------------------------

            processed_count += 1

            # 执行克隆
            clone_repo(app_id, url)

        except Exception as e:
            print(f"解析行出错: {line}")

    print("\n--- 所有源码下载任务完成 ---")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序已暂停。再次运行脚本可从断点处继续。")