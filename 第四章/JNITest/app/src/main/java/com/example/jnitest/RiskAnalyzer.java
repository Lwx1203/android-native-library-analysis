package com.example.jnitest;

import android.util.Log;

/**
 * 场景2：风控分析层，位于 BusinessManager 与 NativeFacade 之间。
 *
 * 调用链中的中间节点，用于验证多层间接调用的回溯能力。
 */
public class RiskAnalyzer {

    private static final String TAG = "RiskAnalyzer";

    /**
     * 执行风控分析，最终委托给 NativeFacade 调用本地函数
     */
    public String analyzeRisk(String data) {
        Log.d(TAG, "analyzeRisk: data=" + data);

        // 进一步加工
        String enriched = enrichRiskData(data);

        // 委托给本地层外观类
        NativeFacade facade = new NativeFacade();
        return facade.invokeSharedNative(enriched, 1);  // mode=1 表示风控模式
    }

    private String enrichRiskData(String data) {
        return data + "_enriched";
    }
}