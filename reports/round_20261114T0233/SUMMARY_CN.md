# 2026-11-14 02:33 hetero：INCOMPLETE

五块128 token完整原Chisel数值仍0/5。统一4096 Matrix MAC、候选硬件/接口/资源未改变；没有完整RTL数值或完整block有效MAC利用率实测。

## 实质工程
- 当前候选真实Host从上轮已保存cycle9266完整包续跑，不reset/relaunch、不重算前缀。session50686 exit0，新增1000周期/8.76秒至10266，真实ACK2432B后另存完整20块非空checkpoint。fresh-process再120周期至10386，ACK2688B即672个FP32字，均与独立首RMS参考相同；两条继续轨迹及20块终态hash全等、既有写回保留。小于首RMS一行6144B，不是完整首RMS/完整block。
- 新完整包SHA c042a6bf7ca6f2a61d50b02c899d4b64720319c5d9effd579ebeb4d8e5777aff；仅checkpoint10266可用于后续恢复，10386仅比较终态，不冒已保存状态。
- L0：沿已验候选Conv和实际16-head ascending Q/K，补实际gate0的AB偏置、Softplus、A_log、g、beta、格式化及prepared布局。2048 token/head gates独立参考完成，仅0/NX；prepared [128,6400] FP32 SHA9154b036019d5e897f29078c9bf8143d5d5c435ed1f506875cc924dd0fd51c2b。Q/K复用已核独立产物，未向DUT预装中间参考。
- 本轮不是历史strict head4失败重现；当前逐步下溢候选算术参考可完成不等于原strict通过。没有执行Chunk/后续block或Host L0，历史FAIL保留。

## 阻塞和边界
原29364原身份仍Unknown，未重复启动。35B真实权重仍缺；现有MoE router P7 exp、同分cutoff行为尚无冻结原框架完整比较，未放宽安装门或改变基线。旧Qwen2/L3完整独立参考复用，不重复计算。

基线main bbcafa46000190943f9f8f9200cc6444fbe98c35，CI43541719050 success仅payload守卫。临时清单已核、工作树clean、清理0；保留唯一证据和被引用运行文件。远端仅允许摘要/中文计划，不上传源码、权重、NPZ、生成数据或原日志。

## MoE边界新增证据（仅独立诊断）
已复核冻结Transformers源commit42ca97014c85d71a88ad60d55f08cb9fb4d26e2c和router class SHA b2ac8438aa26449aeafbb7a80b1af9f2b4fa85a6b96aec3229377976c2d73be1，不用可变main替代。历史Torch2.10.0+cpu、CPU DEFAULT/单线程及binary pins有记录，但当前torch/libtorch缺，无法声称冻结kernel重跑。
新增独立精确FP32/Decimal边界诊断8项通过：含5种概率边界及非finite/溢出检查。BF16可表示的0与2^-30在减去max=1时就可能合并，故不能仅以原logits是否相等判断softmax后的第8/9名cutoff；极端有限BF16差还可能溢出至-Inf。高精度exp诊断不是原P7或Torch实现，不把诊断stable ID注入参考/硬件。官方topk不保证同分索引稳定也不授权改变冻结契约。准入门仍未放开。
