package com.example.jnitest;

import android.util.Log;

/**
 * 场景5：JNI 回调场景。
 *
 * 调用链：MainActivity → CallbackService → nativeWithCallback()
 *         → (native层通过 CallVoidMethod) → onNativeResult()
 *
 * 用于验证本地层通过 JNI 环境接口主动回调托管层方法的双向调用路径恢复能力。
 */
public class CallbackService {

    private static final String TAG = "CallbackService";
    private ResultListener listener;

    static {
        System.loadLibrary("nativesub");
        System.loadLibrary("nativecore");
    }

    /**
     * 回调结果监听接口
     */
    public interface ResultListener {
        void onResult(String result);
    }

    public void setResultListener(ResultListener listener) {
        this.listener = listener;
    }

    /**
     * 触发 native 调用，native 层会回调 onNativeResult
     */
    public void executeWithCallback(String data) {
        Log.d(TAG, "executeWithCallback: data=" + data);
        nativeWithCallback(data);
    }

    /**
     * 由 native 层通过 JNI CallVoidMethod 回调此方法。
     * 这是跨语言反向调用路径的关键节点。
     */
    public void onNativeResult(String result) {
        Log.d(TAG, "onNativeResult (called from native): " + result);
        if (listener != null) {
            listener.onResult(result);
        }
    }

    /**
     * JNI native 方法声明
     * 对应 C 层：Java_com_example_jnitest_CallbackService_nativeWithCallback
     */
    public native void nativeWithCallback(String data);
}