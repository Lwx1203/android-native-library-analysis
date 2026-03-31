#include <jni.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <android/log.h>
#include "nativesub.h"

#define TAG "NativeCore"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, TAG, __VA_ARGS__)
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO,  TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, TAG, __VA_ARGS__)

/* ================================================================
 * 场景1 + 场景3：托管层直接调本地层 + 本地层调 C 标准库函数
 *
 * 调用链：
 *   Java: MainActivity → DirectBridge.callNativeDirect()
 *                       → DirectBridge.nativeDirectEntry()
 *   JNI:  → Java_com_example_jnitest_DirectBridge_nativeDirectEntry()
 *   C库:    → strlen() → snprintf() → fopen() → fwrite() → fclose()
 *
 * 验证目标：
 *   - JNI 入口函数识别
 *   - NativeSummary 统一化后保留 C 库函数调用信息
 * ================================================================ */
JNIEXPORT jstring JNICALL
Java_com_example_jnitest_DirectBridge_nativeDirectEntry(
        JNIEnv *env, jobject thiz, jstring input) {

    const char *inputStr = (*env)->GetStringUTFChars(env, input, NULL);
    if (inputStr == NULL) {
        return (*env)->NewStringUTF(env, "ERROR: GetStringUTFChars failed");
    }

    LOGD("nativeDirectEntry: received input='%s'", inputStr);

    /* 场景3：调用 C 标准库 strlen */
    size_t len = strlen(inputStr);

    /* 场景3：调用 C 标准库 snprintf */
    char buffer[256];
    snprintf(buffer, sizeof(buffer),
             "direct_processed(input=%s, len=%zu)", inputStr, len);

    /* 场景3：调用 C 标准库 fopen / fwrite / fclose（文件操作） */
    FILE *f = fopen("/dev/null", "w");
    if (f != NULL) {
        fwrite(buffer, 1, strlen(buffer), f);
        fclose(f);
        LOGD("nativeDirectEntry: file write completed");
    }

    LOGI("nativeDirectEntry: result='%s'", buffer);

    (*env)->ReleaseStringUTFChars(env, input, inputStr);
    return (*env)->NewStringUTF(env, buffer);
}


/* ================================================================
 * 场景2 + 场景4 + 场景7：
 *   多层间接调用 / 本地库间调用 / 多入口共享
 *
 * 调用链（场景2 - 风控路径）：
 *   Java: MainActivity → BusinessManager → RiskAnalyzer
 *         → NativeFacade.invokeSharedNative()
 *         → NativeFacade.nativeSharedEntry()
 *   JNI:  → Java_com_example_jnitest_NativeFacade_nativeSharedEntry()
 *   本地库间(场景4): → sub_encrypt_like()  [libnativesub.so]
 *   C库(场景3):        → strlen()
 *
 * 调用链（场景7 - 上传路径，共享同一 native 函数）：
 *   Java: MainActivity → UploadController
 *         → NativeFacade.invokeSharedNative()
 *         → NativeFacade.nativeSharedEntry()
 *   JNI:  → 同上
 *
 * 通过 mode 参数区分不同业务：
 *   mode=1: 风控分析
 *   mode=2: 上传预检查
 *
 * 验证目标：
 *   - 多层间接调用的回溯能力
 *   - 本地库间调用关系建模
 *   - 多入口共享同一 JNI 锚点的识别
 * ================================================================ */
JNIEXPORT jstring JNICALL
Java_com_example_jnitest_NativeFacade_nativeSharedEntry(
        JNIEnv *env, jobject thiz, jstring data, jint mode) {

    const char *dataStr = (*env)->GetStringUTFChars(env, data, NULL);
    if (dataStr == NULL) {
        return (*env)->NewStringUTF(env, "ERROR: GetStringUTFChars failed");
    }

    LOGD("nativeSharedEntry: data='%s', mode=%d", dataStr, mode);

    /* 场景4：调用辅助本地库 libnativesub.so 中的函数 */
    char encrypted[256];
    sub_encrypt_like(dataStr, encrypted, sizeof(encrypted));

    /* 还可以调用辅助库的另一个函数 */
    int hash = sub_compute_hash(dataStr, strlen(dataStr));

    /* 根据 mode 参数生成不同的处理结果（场景7：同一函数，不同语义） */
    char result[512];
    if (mode == 1) {
        /* 风控模式 */
        snprintf(result, sizeof(result),
                 "risk_result(data=%s, enc=%s, hash=%d)", dataStr, encrypted, hash);
    } else if (mode == 2) {
        /* 上传预检查模式 */
        snprintf(result, sizeof(result),
                 "upload_check(data=%s, enc=%s, hash=%d)", dataStr, encrypted, hash);
    } else {
        snprintf(result, sizeof(result),
                 "unknown_mode_%d(data=%s)", mode, dataStr);
    }

    LOGI("nativeSharedEntry: result='%s'", result);

    (*env)->ReleaseStringUTFChars(env, data, dataStr);
    return (*env)->NewStringUTF(env, result);
}


/* ================================================================
 * 场景5：本地层通过 JNI 回调托管层
 *
 * 调用链：
 *   Java: MainActivity → CallbackService.executeWithCallback()
 *         → CallbackService.nativeWithCallback()
 *   JNI:  → Java_com_example_jnitest_CallbackService_nativeWithCallback()
 *   回调: → CallVoidMethod → CallbackService.onNativeResult()
 *
 * 验证目标：
 *   - 跨 JNI 边界的反向调用路径恢复
 *   - 双向交互行为刻画
 * ================================================================ */
JNIEXPORT void JNICALL
Java_com_example_jnitest_CallbackService_nativeWithCallback(
        JNIEnv *env, jobject thiz, jstring data) {

const char *dataStr = (*env)->GetStringUTFChars(env, data, NULL);
if (dataStr == NULL) {
LOGE("nativeWithCallback: GetStringUTFChars failed");
return;
}

LOGD("nativeWithCallback: received data='%s'", dataStr);

/* 在 native 层进行一些处理 */
char resultBuf[256];
size_t len = strlen(dataStr);
snprintf(resultBuf, sizeof(resultBuf),
"native_cb_result(data=%s, len=%zu, processed=true)", dataStr, len);

/* ===== 关键：通过 JNI 回调托管层方法 ===== */
jclass cls = (*env)->GetObjectClass(env, thiz);
if (cls == NULL) {
LOGE("nativeWithCallback: GetObjectClass failed");
(*env)->ReleaseStringUTFChars(env, data, dataStr);
return;
}

/* 查找 CallbackService.onNativeResult(String) 方法 */
jmethodID mid = (*env)->GetMethodID(env, cls, "onNativeResult",
                                    "(Ljava/lang/String;)V");
if (mid == NULL) {
LOGE("nativeWithCallback: GetMethodID 'onNativeResult' failed");
(*env)->ReleaseStringUTFChars(env, data, dataStr);
return;
}

/* 构造回调参数并执行 CallVoidMethod */
jstring jResult = (*env)->NewStringUTF(env, resultBuf);
(*env)->CallVoidMethod(env, thiz, mid, jResult);

LOGI("nativeWithCallback: callback invoked with '%s'", resultBuf);

(*env)->ReleaseStringUTFChars(env, data, dataStr);
}