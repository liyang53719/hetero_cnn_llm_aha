# 原生产QK16 Host：生成失败与同IR离线通过

两个不同层级必须保留：原v3实际运行driver exit1，receipt NOT_COMPLETED；编译/CHIRRTL子阶段exit0且strict cleanup完成，旧parser误拒绝两条既有memory读地址默认invalidate。原receipt没有改成PASS。随后v4只读同一IR，完整93源/550+3类/SourceFile/87jar/JDK postflight与4407条连接通过，独立审核通过；没有重跑Java。

实际IR42,095,784B，SHA80aca2cd2cab5758a755fc1b3434b73f0c3887d15395a9f01b0713eaec9d5af9，690定义/实例（17ext）、68memory声明，5条原位宽warning。93固定Scala源，原550类+独立emitter3类。4096是8×16×32原端点接口配置依据，不是综合资源验收。16lane SFU、全top17scalar、唯一Dense/Matrix/iDMA及五债务结构通过；没有动态债务/数值/性能验收。QK-only不含完整packedPV/scratch/panel；90%目标不变。

SAFE_EVIDENCE是安全投影，保留原receipt/IR/源/类身份，实际4407条连接完整清单以canonical hash绑定；不含原IR、classes、JAR、日志、PID/boot/宿主时刻。SOURCE_PINS/BASELINE_CLASS_PINS/ACTUAL_CLASS_PINS提供可复验库存。新parser完整检查result4099叶、done2叶、step277叶及guard/最终覆盖；两地址WIRE只在各自read-enable条件下先key覆盖再read mport，不是全module无条件覆盖。19 normal+19 -O原源码冷测与独立实际离线复核通过；本包另6项便携冷测，合计25+25通过。

## 输入重建

main 23f9a44 已发布 candidates/qwen2_resident_matrix/production_qk16_rebase 的便携92-source/550-class重建链。该目录记为R；按其 classcompile/README_PORTABLE_CN.md 重建生产根PROD与QK donor根QK，HardFloat目录HF由已固定官方下载链提供，原87jar缓存CACHE87与固定JDK JAVA由消费者明确指定。

    python -B "$R/classcompile/reproduce_sources.py" --production-source "$PROD" --qk16-source "$QK" --hardfloat-scala "$HF" --output "$SOURCE92"
    python -B "$R/classcompile/compile_only.py" --preflight-only --source-root "$SOURCE92" --dependency-cache "$CACHE87" --java "$JAVA" --output "$BASE_OUTPUT"

得到明确编译批准后，将 --preflight-only 换成 --execute-approved-once，BASE550 指 BASE_OUTPUT/classes。该独立全92-source classcompile有120秒总预算，不能与本Host90秒混为一次预算。它从源码重建，不能仅复用私人550缓存；不接受旧545生产类、不完整overlay或静默更新pins。UPSTREAM_REBUILD_PINS固定同批公开recipe/runner身份。本Host包没有为测试便携性再次编译Java。

本目录为H。prepare_generation只复制原v3操作源码并选历史parser，不执行工具：

    python -B "$H/prepare_generation.py" --out "$GEN_SOURCE"

以下历史生成重放需要明确批准，会生成CHIRRTL，不调用SV/动态仿真；由于保留旧parser，预期结构总门仍FAIL，不能把它隐藏：

    python -B "$GEN_SOURCE/run_structure.py" --source-root "$SOURCE92" --base-classes "$BASE550" --cache "$CACHE87" --java "$JAVA" --out "$FRESH_ATTEMPT" --execute

原90秒/compile20/emit60/heap1GiB/CPU1/48MiB文件与IR/2MiBlog/64MiB输出树采样软限/768定义保护不变。此次发布没有执行这条重放，也不自动重试。

对已存在的固定IR作便携离线复核，无child进程，要求IR/source/classes/JAR/JDK精确hash，不要求复现含宿主身份的历史receipt原字节：

    python -B "$H/verify_existing.py" --attempt "$EXISTING_ATTEMPT" --source-root "$SOURCE92" --base-classes "$BASE550" --cache "$CACHE87" --java "$JAVA" --output "$FRESH_OFFLINE_JSON"

这一入口不读取或改写生成receipt，也不声明新生成过程通过；只验证已存在文件的固定身份与结构。实际历史v4离线通过由SAFE_EVIDENCE另行记录。原IR留本地，不随包上传。

冷测试：test_cold.py、test_packed.py、test_budget.py、test_portable.py，分别用python -B和python -O -B运行。预算测试mock Popen，不执行Java。外部provider闭包尚不能由本结构门代替，暂不运行实际AXI/QK控制或完整RTL数值。打包时未由本任务push。
