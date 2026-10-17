# 原iDMA wrapper限定lint资格历史

v1：FAIL，4 UNOPTFLAT；v2：FAIL，top public输出拆分被SPLITVAR拒绝，剩2 UNOPTFLAT；v3：PASS_ORIGINAL_IDMA_WRAPPER_LINT_ONLY。三个独立单次root授权尝试，原失败不改写，没有自动重跑或关掉UNOPTFLAT。

v3精确top idma_backend_rw_axi_flat_wrap，原参数512-bit数据/64-bit地址/BufferDepth3/HardwareLegalizer1/RejectZeroTransfers1/EnableCompute0，293输入保守subset（官方294只排除两个cut/multicut库候选再加原wrapper）。1039输入/工具pins前后通过；源码/ABI未改。

23 WIDTH在原固定参数/有效非零事务条件下经值域独审，形成21个精确file/rule/line/hash规则；pagewidth实际10且该配置最大14，合法AXI len0..15。无效周期不保证该范围。其余warning保持fatal，无PINMISSING/UNOPTFLAT豁免。

6个官方结构提示隔离FIFO valid/ready、write first/last、coupler aw_sent，以及拆分内部write_req_o。顶层public split不再使用。配置源码目标唯一匹配，官方支持split早于inline；工具没有单独hint-hit telemetry，成功仅以实际完整lint零warning和exit0确认，不能泛化任意top/宏/参数或动态证明。

v3工具stage1.210810088s，总1.553870136s；CPU1/AS4GiB/FSIZE16MiB、2MiB日志限、210/180秒预算未提高。日志305B，leader采样maxRSS136032256B，非全进程树真实峰。实际目录无.cpp/.o/.so/.a，未执行C++build/仿真/数值；工具内部汇总提到C++数量不表示有构建。

完整原cleanup identity proof/绝对argv/日志只留本机。本包仅安全结果和原receipt/log哈希，记录cleanup范围原group+observed identities；不能由摘要重新认证完整proof，也不声称全局absence。

这项PASS只解除原iDMA wrapper的独立工具lint/elaboration门，wholeBench/Host dynamic仍需另门。固定iDMA源artifact来自run39030773068，其30天保留期及重建pins见IDMA_SOURCE_EXPORT_SUCCESS_39030773068。这里不把33MB源树、工具二进制或主机日志推入仓库。

## 可复现source入口

同包 scripts/idma_wrapper_lint_v3_20261017 保留实际已审runner全部原字节及其ARTIFACT_HASHES，包含1039 INPUT_PINS和293顺序清单、helper及冷测试。没有自动工作流；安装本包不执行lint。

在隔离workspace按源包重建说明恢复固定iDMA导出目录、原flat wrapper路径、既有官方Verilator工具及share树；必须与INPUT_PINS全量一致。将该scripts目录复制为workspace根下 idma_wrapper_lint_runner_v3_20261017 后，先核manifest，再运行test_cold.py及python3 -O同测试。冷测还引用先前静态composition作subset独立对比；同包 ORIGINAL_PROVIDER_COMPOSITION.json 原字节恢复为 workspace 下 production_qk16_provider_composition_v1_20261017/COMPOSITION.json；该冷测试只比较其中的iDMA subset记录，不执行或要求其他Matrix/FMA文件，不能删除该冷测。

新的真实lint不是持久授权：获得一次root GO并检查资源/无重作业后，用run_lint.py --workspace指向该workspace、--out指定全新目录、--execute；不得覆盖三个原attempt，不自动放宽规则或重试。源artifact过期按固定pins重新物化，不升级依赖。工具路径和版本变动需要新资格，不能将本次PASS嫁接给新工具。
