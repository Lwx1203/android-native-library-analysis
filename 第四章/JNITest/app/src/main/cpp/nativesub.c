#include "nativesub.h"
#include <string.h>
#include <stdio.h>
#include <android/log.h>

#define TAG "NativeSub"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, TAG, __VA_ARGS__)
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO,  TAG, __VA_ARGS__)

/**
 * 场景4 + 场景3 的核心函数。
 *
 * 执行路径：nativeSharedEntry() → sub_encrypt_like() → strlen()
 *
 * 模拟对输入数据进行简单的异或变换（模拟加密行为），
 * 内部调用 strlen()（C 标准库函数），验证 NativeSummary
 * 统一化后是否保留了底层行为语义。
 */
void sub_encrypt_like(const char *input, char *output, size_t output_size) {
    /* 场景3：调用 C 标准库函数 strlen */
    size_t len = strlen(input);

    LOGD("sub_encrypt_like: input_len=%zu", len);

    /* 模拟简单的 XOR 加密变换 */
    char temp[256];
    size_t i;
    size_t process_len = (len < sizeof(temp) - 1) ? len : (sizeof(temp) - 1);
    for (i = 0; i < process_len; i++) {
        temp[i] = (char)(input[i] ^ 0x5A);
    }
    temp[i] = '\0';

    /* 场景3：调用 C 标准库函数 snprintf */
    snprintf(output, output_size, "enc_%zu_bytes_hash%d", len, sub_compute_hash(input, len));

    LOGI("sub_encrypt_like: output=%s", output);
}

/**
 * 辅助哈希计算函数
 */
int sub_compute_hash(const char *data, size_t len) {
    int hash = 0;
    for (size_t i = 0; i < len; i++) {
        hash = hash * 31 + data[i];
    }
    LOGD("sub_compute_hash: len=%zu, hash=%d", len, hash);
    return hash;
}