import os
import subprocess
import shutil
import re
import hashlib

# ---------- 配置区域 ----------
apktool_path = "apktool"
apksigner_path = ""
debug_keystore = ""
smali_temp_dir = "smali_out"

# ---------- APK 批量输入输出路径 ----------
input_apk_dir =''
output_apk_dir = ''

def run_cmd(cmd):
    print(f"运行命令: {cmd}")
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(res.stdout)
    return res.returncode

def decompile_apk(apk_path, out_dir):
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    cmd = f"{apktool_path} d -f \"{apk_path}\" -o \"{out_dir}\""
    return run_cmd(cmd)

def recompile_apk(out_dir, apk_out_path):
    cmd = f"{apktool_path} b \"{out_dir}\" -o \"{apk_out_path}\""
    return run_cmd(cmd)

def sign_apk(apk_path):
    cmd = (
        f"{apksigner_path} sign --ks \"{debug_keystore}\" "
        f"--ks-pass pass:android --key-pass pass:android \"{apk_path}\""
    )
    return run_cmd(cmd)

def is_native_method(line):
    stripped = line.strip()
    return (stripped.startswith('.method') and ' native ' in stripped.replace('\t', ' ') and '(' in stripped and ')' in stripped)

def find_smali_dirs(base_dir):
    dirs = []
    for entry in os.listdir(base_dir):
        full_path = os.path.join(base_dir, entry)
        if os.path.isdir(full_path):
            dirs.append(full_path)
    return dirs

def safe_classname_from_sig(native_sig):
    method_name = native_sig.split("->")[-1].split('(')[0]
    sig_hash = hashlib.md5(native_sig.encode()).hexdigest()
    return f"{method_name}_{sig_hash}"

def gen_helper_logger_class(smali_dir, native_sig):
    cls_name = safe_classname_from_sig(native_sig)
    package_path = os.path.join(smali_dir, "com", "example", "logger")
    os.makedirs(package_path, exist_ok=True)
    smali_path = os.path.join(package_path, f"{cls_name}.smali")
    log_msg = f"{native_sig}"
    smali_code = f"""
.class public Lcom/example/logger/{cls_name};
.super Ljava/lang/Object;

.method public constructor <init>()V
    .locals 0
    invoke-direct {{p0}}, Ljava/lang/Object;-><init>()V
    return-void
.end method

.method public static log()V
    .locals 2
    const-string v0, "<LiuWenXuan>"
    const-string v1, "{log_msg}"
    invoke-static {{v0, v1}}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I
    return-void
.end method
""".strip()
    with open(smali_path, 'w', encoding='utf-8') as f:
        f.write(smali_code)

def insert_logs_in_smali_dir(smali_dir):
    native_methods = set()
    native_sig_to_class = {}
    called_native_methods = set()

    for root, _, files in os.walk(smali_dir):
        for f in files:
            if f.endswith('.smali'):
                smali_path = os.path.join(root, f)
                current_class = None
                with open(smali_path, 'r', encoding='utf-8', errors='ignore') as file:
                    for line in file:
                        line_strip = line.strip()
                        if line_strip.startswith('.class'):
                            class_match = re.search(r'L([^;]+);', line_strip)
                            if class_match:
                                current_class = class_match.group(1)
                        if is_native_method(line):
                            m = re.match(r'\.method\s+(.*?native.*?)\s+(\w+)\(([^)]*)\)([^ ]*)', line_strip)
                            if m and current_class:
                                method_name = m.group(2)
                                params = m.group(3)
                                return_type = m.group(4)
                                full_sig = f"{current_class}->{method_name}({params}){return_type}"
                                native_methods.add(full_sig)

    if not native_methods:
        return set(), {}

    for sig in native_methods:
        gen_helper_logger_class(smali_dir, sig)
        native_sig_to_class[sig] = safe_classname_from_sig(sig)

    def process_smali_file(smali_path):
        nonlocal called_native_methods
        with open(smali_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        new_lines = []
        method_stack = []
        inserted = False

        for line in lines:
            stripped = line.strip()

            if stripped.startswith('.method'):
                method_stack.append({
                    'start': len(new_lines),
                    'locals_line': -1,
                    'locals_count': 0,
                    'name': stripped,
                    'is_static': 'static' in stripped
                })

            elif stripped.startswith('.locals') and method_stack:
                method_stack[-1]['locals_line'] = len(new_lines)
                try:
                    method_stack[-1]['locals_count'] = int(stripped.split()[1])
                except:
                    method_stack[-1]['locals_count'] = 0

            elif stripped.startswith('.end method') and method_stack:
                method_stack.pop()

            elif method_stack and stripped.startswith('invoke-'):
                if re.search(r'Lcom/example/logger/[^;]+;->log\(\)V', stripped):
                    new_lines.append(line)
                    continue

                m = re.search(r'invoke-\w+\s*\{[^}]*}\s*,\s*(L[^;]+;->\w+\([^)]*\)[^\s]*)', stripped)
                if m:
                    invoke_sig_raw = m.group(1)
                    invoke_sig = invoke_sig_raw[1:].replace(';->', '->')
                    if invoke_sig in native_methods:
                        called_native_methods.add(invoke_sig)

                        method = method_stack[-1]
                        if method['locals_line'] != -1:
                            old_locals = method['locals_count']
                            new_locals = max(1, old_locals)
                            new_lines[method['locals_line']] = f"    .locals {new_locals}\n"
                        else:
                            new_lines.insert(method['start'] + 1, f"    .locals 1\n")
                            method['locals_line'] = method['start'] + 1

                        helper_cls = native_sig_to_class[invoke_sig]
                        log_line = f"    invoke-static {{}}, Lcom/example/logger/{helper_cls};->log()V\n"
                        new_lines.append(log_line)
                        new_lines.append(line)
                        inserted = True
                        continue
            new_lines.append(line)

        if inserted:
            with open(smali_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)

    for root, _, files in os.walk(smali_dir):
        for f in files:
            if f.endswith('.smali'):
                process_smali_file(os.path.join(root, f))

    # 不再写文件，返回数据
    return called_native_methods, native_sig_to_class

def process_apk_file(apk_path, output_apk_dir):
    apk_filename = os.path.basename(apk_path)
    apk_name = os.path.splitext(apk_filename)[0]
    print("=" * 80)
    print(f"正在处理 APK: {apk_filename}")
    print("=" * 80)

    if os.path.exists(smali_temp_dir):
        shutil.rmtree(smali_temp_dir)

    out_dir = smali_temp_dir
    signed_apk_path = os.path.join(output_apk_dir, f"{apk_name}_signed.apk")
    native_log_txt_path = os.path.join(output_apk_dir, f"{apk_name}_native_calls.txt")

    if decompile_apk(apk_path, out_dir) != 0:
        print("反编译失败，跳过此APK")
        return

    smali_dirs = find_smali_dirs(out_dir)
    if not smali_dirs:
        print("未找到smali目录，跳过此APK")
        return

    all_called_methods = set()
    all_native_sig_to_class = {}

    for smali_dir in smali_dirs:
        called_methods, native_sig_to_class = insert_logs_in_smali_dir(smali_dir)
        all_called_methods.update(called_methods)
        all_native_sig_to_class.update(native_sig_to_class)

    if not all_called_methods:
        print("无native调用需要插桩，跳过")
        return

    unsigned_apk_path = os.path.join(output_apk_dir, f"{apk_name}_unsigned.apk")
    if recompile_apk(out_dir, unsigned_apk_path) != 0:
        print("打包失败，跳过此APK")
        return

    if sign_apk(unsigned_apk_path) != 0:
        print("签名失败，跳过此APK")
        return

    shutil.move(unsigned_apk_path, signed_apk_path)

    # 统一写入调用日志文件（覆盖写）
    with open(native_log_txt_path, 'w', encoding='utf-8') as log_file:
        for sig in sorted(all_called_methods):
            log_file.write(sig + "\n")

    print(f"成功输出: {signed_apk_path}")
    print(f"插桩调用日志: {native_log_txt_path}\n")

def main_batch():
    if not os.path.exists(output_apk_dir):
        os.makedirs(output_apk_dir)

    apk_files = [f for f in os.listdir(input_apk_dir) if f.endswith('.apk') and not f.startswith('.')]
    if not apk_files:
        print("输入目录下没有找到 APK 文件！")
        return

    print(f"共找到 {len(apk_files)} 个 APK 文件，开始批量处理...\n")
    for apk_file in apk_files:
        apk_path = os.path.join(input_apk_dir, apk_file)
        process_apk_file(apk_path, output_apk_dir)

    print("\n所有 APK 处理完成！输出目录:", output_apk_dir)

if __name__ == '__main__':
    main_batch()
