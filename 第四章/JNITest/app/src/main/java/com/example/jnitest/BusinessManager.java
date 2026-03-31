package com.example.jnitest;

import android.util.Log;

/**
 * 场景2 & 7：业务管理层。
 *
 * 场景2 调用链：MainActivity → BusinessManager → RiskAnalyzer → NativeFacade → nativeSharedEntry()
 * 场景7：与 UploadController 共享同一个 nativeSharedEntry()，通过 mode 参数区分。
 */
public class BusinessManager {

    private static final String TAG = "BusinessManager";

    /**
     * 模拟订单风控流程：对订单ID进行预处理后，交给 RiskAnalyzer 分析
     */
    public String processRiskCheck(String orderId) {
        Log.d(TAG, "processRiskCheck: orderId=" + orderId);

        // 业务层预处理
        String preprocessed = preprocessOrder(orderId);

        // 委托给风控分析器
        RiskAnalyzer analyzer = new RiskAnalyzer();
        return analyzer.analyzeRisk(preprocessed);
    }

    /**
     * 模拟业务层的数据预处理逻辑
     */
    private String preprocessOrder(String orderId) {
        return "risk_" + orderId + "_ts" + System.currentTimeMillis();
    }
}