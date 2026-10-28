# TEMP / INCOMPLETE：恢复后执行链纠错

基线 897f08f7；详见 `candidates/recovered_execution_fixes/README_CN.md`。

## done（仅精确范围）
- 独立源审计确认 Qwen2 七个 Dense 权重 dtype7 与原 public21 dtype5 契约冲突。原转换器修复元数据，非权重 FP32 不变。
- provider 合成输运与负向用例 191+18；真实 source spec/权重未恢复，实际 bytes/hash 不通过继承。
- MoE 普通 Down 单 K 块无需 prefix 工作区，最小 K>splitK 保护候选；5600 控制案例，不是硬件执行。特殊路径和多块别名保护不变。
- 保留旧源/错误夹具；本次只追加文本复现脚本、候选补丁、pin 和摘要，无数据上传。

## ongoing
- 恢复实际输入/权重和 source spec，重新绑定 P0 新 manifest 与 descriptor pin，并重建所有逻辑 hash/后端导出。
- 将最小 Down 改动纳入同一统一硬件源码，补齐缺失 protocol 的可验证来源；不得把重建猜测标为原字节。

## todo
- 编译/elaboration 后，以同一固定 4096 MAC/资源定义推进五块 M128 完整 Chisel 数值；当前五块全 INCOMPLETE，0/5。
- 通过后冻结同源/输入/参考/配置再生成同一 RTL 哈希同刺激回放；最终 RTL 0/5。
- 完整 block 周期分母的有效 MAC 利用率暂无测量，不声称 80%/90%。32-lane 每周期候选和 MoE 同分契约不在本补丁擅自改变。

## 临时数据
- 本轮未清理任何已有仓库/未跟踪证据；复现脚本仅管理自己新建的可重建临时文件。运行中/唯一/引用证据保留。
