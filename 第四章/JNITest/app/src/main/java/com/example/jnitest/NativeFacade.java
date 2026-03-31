package com.example.jnitest;

import android.util.Log;

/**
 * 本地层外观类，封装对 nativeSharedEntry() 的调用。
 *
 * 场景2 路径：BusinessManager → RiskAnalyzer → NativeFacade → nativeSharedEntry()
 * 场景7 路径：UploadController → NativeFacade → nativeSharedEntry()
 *
 * 两条不同业务路径共享同一个 JNI 入口函数。
 *
 * 在 native 层：
 *   场景4：nativeSharedEntry() → sub_encrypt_like()（调用辅助本地库）
 *   场景3：sub_encrypt_like() → strlen()（调用 C 标准库）
 */
public class NativeFacade {

    private static final String TAG = "NativeFacade";

    static {
        System.loadLibrary("nativesub");
        System.loadLibrary("nativecore");
    }

    /**
     * 统一的本地层调用入口
     * @param data 业务数据
     * @param mode 模式标识（1=风控，2=上传预检查）
     */
    public String invokeSharedNative(String data, int mode) {
        Log.d(TAG, "invokeSharedNative: data=" + data + ", mode=" + mode);
        return nativeSharedEntry(data, mode);
    }

    /**
     * JNI native 方法声明
     * 对应 C 层：Java_com_example_jnitest_NativeFacade_nativeSharedEntry
     */
    public native String nativeSharedEntry(String data, int mode);
}