cmake_minimum_required(VERSION 3.22.1)
project("jnitest")

# ==========================================
# 本地层辅助库：libnativesub.so
# 用于验证场景4（本地库间调用）
# ==========================================
add_library(nativesub SHARED nativesub.c)
target_link_libraries(nativesub log)

# ==========================================
# 本地层主库：libnativecore.so
# 实现所有 JNI 入口函数
# ==========================================
add_library(nativecore SHARED nativecore.c)
target_include_directories(nativecore PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(nativecore
        nativesub   # 链接辅助库，验证场景4
        log         # Android log
)