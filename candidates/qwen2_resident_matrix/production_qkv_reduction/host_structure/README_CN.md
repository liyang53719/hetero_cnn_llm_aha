# 原 HostBlockTop CHIRRTL 结构门

v5 实际结构 PASS，独立审查通过。39,580,497B CHIRRTL、689定义/689连通实例、17外部模块、68memory声明；原Host使用92固定源与545+3类。结果详见 RESULT_CN.md。STRUCTURE_PASS_PROJECTION 是安全投影，不是原receipt字节。原IR、完整日志、classes、JAR均不发布。v3/v4 的32MiB拒写失败保留在 FAILURE_HISTORY_PROJECTION；v4实测后只升48MiB/768定义，未缩资源。

4096来自八个16×32 retained端点接口配置，不是综合资源实测。实际SFU bank有16scalar，整个top含原scalar共17。五债务仅通过真实emitted结构检查，未运行作业、AXI错误或数值；完整29阶段/M128/90%目标仍未完成。5条索引width warning已保留。本包不生成新SV，不启动完整RTL或长数值。

## 可重建输入

本目录记为 H；父production_qkv_reduction目录记为 P；同级 compiled_control 为 C。CHECKOUT为用户指定、满足源pin的已发布仓库。先按 P/README_CN.md 使用 P/replay.py 重放生产补丁到 WORK/source。

使用 C/download_pinned.py --kind jars 和 --kind hardfloat 的固定官方下载流程（均需显式 --download），再按 C/README_CN.md 提取HardFloat并运行：

    python -B "$P/compile/prepare_sources.py" --source-root "$WORK/source" --hardfloat-root "$HARDFLOAT_SCALA" --out "$SOURCE91"
    python -B "$P/compile/compile_only.py" --preflight-only --source-root "$SOURCE91" --cache "$JAR_CACHE" --java "$JAVA" --output "$BASE_OUTPUT"

批准后去掉 --preflight-only 重建545类；此独立classcompile有原88秒预算，不计入结构门90秒。JDK java及release必须匹配JDK_PINS；无私人cache作为唯一复现依据，不接受任意旧classes。虽然官方下载cache可含106运行依赖及原87的并集，本门classpath严格只有 BASELINE_DEPENDENCY_PINS 的87项。无需Verilator/firtool/native工具。

## 结构重放

    python -B "$H/test_cold.py"
    python -O -B "$H/test_cold.py"
    python -B "$H/test_portable.py"
    python -O -B "$H/test_portable.py"

以下会执行classcompile和CHIRRTL elaboration，需明确执行批准；不会运行数值或SV仿真：

    python -B "$H/run_structure.py" --source-root "$SOURCE91" --base-classes "$BASE_OUTPUT/classes" --cache "$JAR_CACHE" --java "$JAVA" --out "$FRESH_OUTPUT" --execute

完整92源hash固定；原545类复制到唯一新classes，仅编1 emitter得到3类，全部SourceFile核验，依赖jar不能shadow原类或emitter。90秒同一绝对截止，compile20/emit60，cleanup保留5秒；Java heap1GiB、实际CPU affinity1，非整树内存硬限。每文件48MiB硬限/CHIRRTL48MiB后验、log2MiB父侧检查；输出树64MiB为采样软限。定义768、展开20000保护门；未知布尔表达式保守拒绝。失败保留证据，不自动放宽检查或重跑。

本包仅执行便携冷测试；实际PASS来自固定v5，操作源码与v5逐字节一致。打包时未由本任务push，发布由上级统一安排。

外部实现闭包尚未完成审核：17 extmodule 包含8个带seed接口的matrix endpoint、8个tc_clk_gating和1个iDMA wrapper。冻结6SV是增量集合，不等于全部provider；本次结构PASS不保证外部provider闭包或可综合链接。真实AXI动态门须等原外部RTL锁及patch链核准。
