# 有序 QK16 真实软件调度观察器单元片

状态：TEMP。仅软件观察器和已发布 owner 定义 AST 的有界测试；Matrix 为原 RoutedScriptedService，Scalar 为原 ScalarControlAdapter，不能作为 Attention 数值、native、完整 block 或硬件 PASS。

绑定父提交 `039bef44e37062e317af705ac8569db9809d7e3c`。不修改已有 core、work、owner、旧 observer 或任何历史 pin；新增 monitor/capture 使用既有 `attention_packed_tiled_observation/capture.py` 的十字段 buffer。SOURCE_PINS 固定七方法角色及原 buffer SHA，实际 code object 与同源编译结果逐个相等才可启动。AST fixture 显式 `ast_definition_test=True`，报告只能为 `AST_DEFINITION_SOFTWARE_TEST_ONLY`；正常加载源码另要求真实 co_filename 对应文件，此模式本批未执行。

## 真实观测接缝

- ProductionQk16Schedule.run → OrderedFoldAdapter.tick：scan 实际逐 cell 有限检查时读取 live FIFO 被选 cell，不复制结果 tile；尾部无效 lane 不采样。
- scale 仅保存投机 `(unrounded_dot_sum, dot_bf16, score_bf16)`，不先写已提交 score。OrderedFoldWork.consume 实际成功，随后原 schedule 的 scores.append 已执行、maximum 赋值之前，才按 key 顺序提交这三个字段。后 key fault 不伪造 prefix。
- 原 softmax exp 的实际返回、normalizer 的实际 max/sum/inverse、原 PV `_op('mul')` 返回和 `_matrix_step` 已物化 BF16 包构成 softmax_fp32/prob_bf16。每个 key 在 8 个 PV column 真实执行各一次，重复必须逐字相同，频率严格为 8，不用复制一份填频率。
- PV raw 是最终 legacy Matrix 返回的 16 lanes；PV BF16 是原 store 前的 16 output words。不是参考计算值。
- PackedClient.tick 入口前态 + 返回 service_result_fire/service_done_fire，逐 work 验证最后提交后 ACK、随后 done。真实 owner response_fire、无错误、无剩余 Matrix/Scalar/内存/租借债务、共享服务身份不变，且 monitoring 已停止，才能 seal。
- 缺字段、shape/extent 漂移、缺值、重复、乱序、未来 causal 单元被写、少一次 PV 复用、早 done/abort/未 terminal ACK 都拒绝 seal。捕获异常停用观察器并保留 error，不替换 DUT 值或 ready。对照测试验证有/无 observer 的 writes、clock、Scalar/Matrix counters、service events、fold events 相同。

## 观测边界

十字段是既有数值 schema，不等于全部内部状态：unrounded_dot_sum 只是历史字段名，实际是顺序 FP32 Add 后的舍入结果，并非数学上未舍入精确和。没有记录逐 stripe 的 16 次 FP32 acc 中间状态、未物化 Mul FP32 返回、每 lane NV/DZ/OF/UF bit、每个 PV key 的中间累加器、所有队列占用或每拍资源状态。观察异常路径只能拒绝完整 seal，不提供完整 fault trace。done 后删除 work/tag 的强引用及投机 scale 暂存，不令审计元数据延长整 tile 驻留；仅留下终态计数/坐标。Python monitoring、数组和元数据均是 host 审计开销，非新增硬件 cache/寄存器；host clock/model step 不是 RTL cycle，不能计算 80/90% 利用率。

本片未接 fullgraph suffix、未改 full M16 admission、未执行新的 native/参考对比。R2 已有真实 Attention M1/M2 数值证据独立保留，本片不继承为新 observer 的数值证明。QK2/PV0 legacy PV 仍有约 63.57% 理想 MAC slot 上界，完整 block 固定 4096 MAC 周期分母、存储/仲裁/填排空/FFN/频率证据仍缺失。

## 复现

干净公开 main（含本候选）的 checkout 已有全部测试依赖，不需私有 tensor、ELF 或 compiler。Python 必须为 CPython 3.12。

```sh
python3 -B candidates/qwen2_ordered_observer/run_bounded.py \
  --source-root . \
  --owner-root candidates/qwen2_ordered_owner \
  --buffer-source candidates/qwen2_resident_matrix/attention_packed_tiled_observation/capture.py \
  --output NEW_EMPTY_RESULT_DIRECTORY
```

每模式独立 1 CPU、256 MiB AS、20 CPU 秒、25 wall 秒，normal / -O / -I / -I -O，各 26 项。run_bounded 只运行纯软件测试，不编译、不生成 RTL、不执行 native。RESULTS.json 记录执行文件 hash、日志 hash 和输入源码不变检查；任何失败或超时停止后续模式。不要用此命令运行 M16/M128。

正常 runtime 集成仍须在独立 manifest 中提供对应实际已加载方法和七个固定角色文件，建立十字段输出保存/独立参考比较、新 fullgraph pc12 dispatch、完整输入/工具/参考准入后，才可申请下一次有界真实数值资格。本片不放宽旧 observer 源码守卫。
