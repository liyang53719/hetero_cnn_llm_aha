# 既有四段 FMA 组件 RTL 发射与接口核验

实际单次 v2 通过：93 源，原 550 类逐字节复用，独立 App 三类；8.617 秒，四份 SystemVerilog 合计 8 个模块定义。SAFE_EVIDENCE 是脱敏投影而非原 receipt 字节，保留原 receipt/plan/SV/source/class hashes 和相对 cleanup 时序。SV 留在本地，可按固定源码与工具再建；此包无 SV、IR、classes、JAR、原日志或宿主身份。

端口与原 seed-enabled matrix lane 的四段绑定及位宽匹配。此结果不含算术测试、完整 Host 链接、动态债务或性能验收。iDMA/其余 Matrix provider 闭包需另外核准。PLAN_CN 与 V2_DELTA 是执行前的历史方案，实际终态以 SAFE_EVIDENCE 为准。原 v1 checker 未执行，缩进/同一行 module 和额外目录漏检由 v2 词法/精确库存冷反例关闭。

## 公共源码重建

R 为已发布 candidates/qwen2_resident_matrix/production_qk16_rebase。按其 classcompile/README_PORTABLE_CN.md 从明确生产源码 PROD、QK donor 源 QK、固定 HardFloat HF 重建，UPSTREAM_REBUILD_PINS 固定该公开链；不依赖私有类缓存。

    python -B "$R/classcompile/reproduce_sources.py" --production-source "$PROD" --qk16-source "$QK" --hardfloat-scala "$HF" --output "$SOURCE92"
    python -B "$R/classcompile/compile_only.py" --preflight-only --source-root "$SOURCE92" --dependency-cache "$CACHE87" --java "$JAVA" --output "$BASE_OUTPUT"

取得执行批准后将 --preflight-only 改成 --execute-approved-once。BASE550=$BASE_OUTPUT/classes。这个独立全源编译是上游 120s 门，不与四组件 90s 混同。87 JAR 与 JDK 必须匹配固定 pins，不自动解析更新依赖。

firtool 官方固定 URL 与 archive/binary SHA 见 TOOL_PINS.json。显式下载到独立 archive 后以 prepare_firtool.py 静态提取，不运行内容；不使用系统包安装。wrapper 使用 /usr/bin/python3，解释器字节必须与 TOOL_PINS 匹配；这是一项明确环境前提，不声称任意平台均可复现。

    python -B "$F/prepare_firtool.py" --archive "$FIRTOOL_ARCHIVE" --out "$FIRTOOL"

MATRIX_LANE 指固定生产补丁 source/rtl/matrix/candidates/rev8b_b/bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv，hash 见 TOOL_PINS。F 为本包目录。真正发射需要明确执行授权，fresh out；不自动重试：

    python -B "$F/run_components.py" --source-root "$SOURCE92" --base-classes "$BASE550" --cache "$CACHE87" --java "$JAVA" --firtool "$FIRTOOL" --matrix-lane "$MATRIX_LANE" --out "$FRESH_OUTPUT" --execute

原 90s 总/20s compile/四组件合计 60s emit；Java heap 1GiB，单 CPU，native 单进程 AS 2GiB，文件 8MiB、日志 2MiB、输出树 64MiB 采样软限。未设整树内存硬限。absence barrier 后 reap，stdout 保持工具原语义。

    python -B "$F/test_cold.py"
    python -O -B "$F/test_cold.py"
    python -B "$F/test_portable.py"
    python -O -B "$F/test_portable.py"

打包时本任务尚未 push；INSTALL_MAP 为 add-only 待审交付。
