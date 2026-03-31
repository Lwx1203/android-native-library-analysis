package com.example.jnitest;

import android.util.Log;

/**
 * 场景7：上传预检查控制器。
 *
 * 调用链：MainActivity → UploadController → NativeFacade → nativeSharedEntry()
 *
 * 与 BusinessManager → RiskAnalyzer → NativeFacade → nativeSharedEntry() 共享
 * 同一个本地函数入口，仅通过 mode 参数区分，用于验证多入口共享场景。
 */
public class UploadController {

    private static final String TAG = "UploadController";

    /**
     * 执行上传前的预检查
     */
    public String preCheckUpload(String fileName) {
        Log.d(TAG, "preCheckUpload: fileName=" + fileName);

        String checkData = buildCheckPayload(fileName);

        NativeFacade facade = new NativeFacade();
        return facade.invokeSharedNative(checkData, 2);  // mode=2 表示上传预检查
    }

    private String buildCheckPayload(String fileName) {
        return "upload_" + fileName + "_sz" + fileName.length();
    }
}