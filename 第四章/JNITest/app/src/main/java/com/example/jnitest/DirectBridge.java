package com.example.jnitest;

/**
 * 场景1：托管层直接调本地层的桥接类。
 *
 * 调用链：MainActivity → DirectBridge → nativeDirectEntry()
 *
 * 场景3 也通过此路径触发：nativeDirectEntry() 内部调用
 * strlen / snprintf / fopen / fwrite / fclose 等 C 标准库函数。
 */
public class DirectBridge {

    static {
        System.loadLibrary("nativesub");
        System.loadLibrary("nativecore");
    }

    /**
     * 由界面事件直接调用，触发 native 方法
     */
    public String callNativeDirect(String input) {
        return nativeDirectEntry(input);
    }

    /**
     * JNI native 方法声明
     * 对应 C 层：Java_com_example_jnitest_DirectBridge_nativeDirectEntry
     */
    public native String nativeDirectEntry(String input);
}