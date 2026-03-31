package com.example.jnitest;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.View;
import android.widget.Button;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

/**
 * 主界面，承担场景入口触发、系统框架噪声产生（场景6）的职责。
 *
 * 场景6说明：
 *   Activity.onCreate()、View.OnClickListener.onClick()、Log.d()、
 *   Toast.makeText()、Handler.post() 等系统框架方法会自然进入静态调用图，
 *   用于验证框架函数去噪算法。
 */
public class MainActivity extends AppCompatActivity {

    private static final String TAG = "JNITest";
    private TextView tvResult;
    private ScrollView scrollView;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final StringBuilder logBuilder = new StringBuilder();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        tvResult = findViewById(R.id.tv_result);
        scrollView = findViewById(R.id.scroll_view);

        // ========== 场景1：托管层直接调本地层 ==========
        Button btnDirect = findViewById(R.id.btn_scenario1);
        btnDirect.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                Log.d(TAG, "===== Scenario 1: Direct Call =====");
                DirectBridge bridge = new DirectBridge();
                String result = bridge.callNativeDirect("hello_direct");
                appendResult("[场景1 直接调用] " + result);
            }
        });

        // ========== 场景2：托管层多层间接调本地层（风控路径） ==========
        Button btnIndirect = findViewById(R.id.btn_scenario2);
        btnIndirect.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                Log.d(TAG, "===== Scenario 2: Multi-layer Indirect Call =====");
                BusinessManager manager = new BusinessManager();
                String result = manager.processRiskCheck("order_12345");
                appendResult("[场景2 间接调用-风控] " + result);
            }
        });

        // ========== 场景3&4：本地层调C库+调辅助本地库（由场景1/2内部触发） ==========
        Button btnNativeInternal = findViewById(R.id.btn_scenario34);
        btnNativeInternal.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                Log.d(TAG, "===== Scenario 3&4: Native internal calls =====");
                // 场景3：nativeDirectEntry 内部调用 strlen/snprintf/fopen/fwrite/fclose
                DirectBridge bridge = new DirectBridge();
                String r1 = bridge.callNativeDirect("test_clib");

                // 场景4：nativeSharedEntry 内部调用 libnativesub 的 sub_encrypt_like
                NativeFacade facade = new NativeFacade();
                String r2 = facade.invokeSharedNative("test_sublib", 1);

                appendResult("[场景3 C库调用] " + r1);
                appendResult("[场景4 本地库间调用] " + r2);
            }
        });

        // ========== 场景5：本地层通过JNI回调托管层 ==========
        Button btnCallback = findViewById(R.id.btn_scenario5);
        btnCallback.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                Log.d(TAG, "===== Scenario 5: JNI Callback =====");
                CallbackService service = new CallbackService();
                service.setResultListener(new CallbackService.ResultListener() {
                    @Override
                    public void onResult(String result) {
                        appendResult("[场景5 JNI回调] " + result);
                    }
                });
                service.executeWithCallback("callback_payload");
            }
        });

        // ========== 场景7：多入口共享同一本地函数 ==========
        Button btnShared = findViewById(R.id.btn_scenario7);
        btnShared.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                Log.d(TAG, "===== Scenario 7: Multi-entry Shared Native =====");

                // 路径A：BusinessManager → RiskAnalyzer → NativeFacade → nativeSharedEntry
                BusinessManager manager = new BusinessManager();
                String r1 = manager.processRiskCheck("order_999");

                // 路径B：UploadController → NativeFacade → nativeSharedEntry
                UploadController controller = new UploadController();
                String r2 = controller.preCheckUpload("file_abc.dat");

                appendResult("[场景7 路径A-风控] " + r1);
                appendResult("[场景7 路径B-上传] " + r2);
            }
        });

        // ========== 全部执行 ==========
        Button btnAll = findViewById(R.id.btn_run_all);
        btnAll.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                logBuilder.setLength(0);
                tvResult.setText("");
                runAllScenarios();
            }
        });

        // ========== 清空日志 ==========
        Button btnClear = findViewById(R.id.btn_clear);
        btnClear.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                logBuilder.setLength(0);
                tvResult.setText("已清空");
            }
        });

        // 场景6：系统框架噪声 — Toast / Handler.post 等
        Toast.makeText(this, "JNI跨语言调用测试应用已启动", Toast.LENGTH_SHORT).show();
        handler.post(new Runnable() {
            @Override
            public void run() {
                Log.d(TAG, "Handler.post executed — framework noise");
            }
        });
    }

    /**
     * 一键执行全部场景
     */
    private void runAllScenarios() {
        // 场景1
        DirectBridge bridge = new DirectBridge();
        appendResult("[S1] " + bridge.callNativeDirect("auto_test_1"));

        // 场景2
        BusinessManager manager = new BusinessManager();
        appendResult("[S2] " + manager.processRiskCheck("auto_order"));

        // 场景3&4（包含在S1和S2的native内部）
        NativeFacade facade = new NativeFacade();
        appendResult("[S3&4] " + facade.invokeSharedNative("auto_sub", 1));

        // 场景5
        CallbackService service = new CallbackService();
        service.setResultListener(new CallbackService.ResultListener() {
            @Override
            public void onResult(String result) {
                appendResult("[S5] " + result);
            }
        });
        service.executeWithCallback("auto_callback");

        // 场景7
        UploadController controller = new UploadController();
        appendResult("[S7-upload] " + controller.preCheckUpload("auto_file.dat"));
        appendResult("[S7-risk] " + manager.processRiskCheck("auto_order_2"));

        appendResult("\n===== 全部场景执行完毕 =====");
    }

    private void appendResult(final String text) {
        handler.post(new Runnable() {
            @Override
            public void run() {
                logBuilder.append(text).append("\n");
                tvResult.setText(logBuilder.toString());
                scrollView.fullScroll(View.FOCUS_DOWN);
            }
        });
    }
}