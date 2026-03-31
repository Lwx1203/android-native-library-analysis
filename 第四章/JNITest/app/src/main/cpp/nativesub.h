#ifndef JNITEST_NATIVESUB_H
#define JNITEST_NATIVESUB_H

#include <stddef.h>

/**
 * 辅助本地库 libnativesub.so 对外接口声明
 *
 * 场景4：主本地库 libnativecore.so 中的 nativeSharedEntry()
 *        调用这些函数，验证本地库间调用关系建模能力。
 */

/**
 * 模拟加密处理函数
 * 内部会调用 strlen()（场景3：C标准库调用）
 *
 * @param input       输入字符串
 * @param output      输出缓冲区
 * @param output_size 输出缓冲区大小
 */
void sub_encrypt_like(const char *input, char *output, size_t output_size);

/**
 * 模拟哈希计算函数
 *
 * @param data 数据指针
 * @param len  数据长度
 * @return     计算得到的哈希值
 */
int sub_compute_hash(const char *data, size_t len);

#endif // JNITEST_NATIVESUB_H