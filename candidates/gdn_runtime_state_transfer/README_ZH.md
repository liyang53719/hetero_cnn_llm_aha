# 固定 max32、运行时 16/32 的共享 GDN 状态搬运

**这是同一个固定接口/同一 RTL 的私有状态搬运叶子，不是完整4096MAC硬件或五block验收。** 不含、也不缩减MAC阵列。旧 heads=16/32 两次elaboration候选只留作历史，不作为共享硬件方案。

## 固定物理接口

`GdnChunkStateTransferOwner` 无模型/head 构造参数。receipt head固定5bit；job.activeHeads固定6bit且硬件只接受16或32；未来staging计数固定7bit才能容纳32×2。`activeHeads := latchedUnifiedProfile.gdnValueHeads`，与统一profile作者确认。keyHeads仍为16：Q/K的repeat_interleave2是生产者工作，不能以valueHeads替换keyHeads。

activeHeads只在job.fire读取；源/目的地址、head、tag和generation随后锁存。忙时无效job的config/head输入变化不改变在途事务。真实阶段receipt仍需统一dispatcher按不可复用tag及profile快照绑定；本叶子不证明上游producer来源，不能拿测试receipt发布root。

同一固定控制器拥有原16个寄存器，包括唯一512bit payload，无新增SRAM bank/浮点单元。完整input/state/output/scratch span按运行时配置校验；每head均128×128 FP32，1024个64B beat。legacy immutable AddressPlan仍只用于per-head shape/offset及16头对照，其全plan不冒称支持32头算术。

## 实测

六源 direct scalac：15.858s，峰RSS约285MiB。4/4实际Chisel/Treadle测试：28.714s，峰约181MiB，无skip。一个DUT实例**不reset、不重新elaborate**连续运行16/32的cold、warm、export共六笔M128请求，覆盖head15/head31，含忙时config/head扰动。另10个pre-memory拒绝分支覆盖非法heads0/17/33、head超界、2MiB state及53.74MB scratch后半alias、56bit完整跨度、receipt head错配；末ACK错误不宣告完成并锁定。

原16-head cold M16/head0测试仅新增activeHeads=16输入，原1024beat/65536B ACK/6399active cycles/6412explicit steps全部不变。

4次测试elaboration的low FIRRTL**完全相同SHA**：`7b6d967bb4f411d52626821f98bba755a5d35ff646410a87d276ef2c15af5064`，每份95515B。随后只对这一IR发射一次SystemVerilog，123114B，SHA `e93e19158a46dc76db9588310a8e3f462c6162ae7fd218e098f040820d7fec94`。没有用两种模型配置生成不同RTL。没有SV仿真、综合/PPA、真实权重或完整block PASS。

## 复现

先验证SOURCE_PINS.json的六源；CP指定Java21/Scala2.13.16/Chisel6.7.0/chiseltest6.0.0/ScalaTest3.2.19及其已安装传递依赖，PLUGIN指定Chisel6.7.0 for Scala2.13.16编译插件。OUT须新目录；不加载历史model class，不把旧protocol/owner重复编译。

```bash
mkdir -p "$OUT/classes"
P=candidates/gdn_runtime_state_transfer
java -Xmx512m -XX:ActiveProcessorCount=1 -cp "$CP" scala.tools.nsc.Main \
 -classpath "$CP" -Xplugin:"$PLUGIN" -language:reflectiveCalls -d "$OUT/classes" \
 chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Protocol.scala \
 candidates/qwen35_chunk_contract/source/GdnChunkAddressPlan.scala \
 "$P/source/GdnChunkProtocol.scala" "$P/source/GdnChunkStateTransferOwner.scala" \
 "$P/tests/GdnChunkStateTransferRuntimeSpec.scala" "$P/tests/GdnChunkStateTransferColdSpec.scala"
java -Xmx512m -XX:ActiveProcessorCount=1 -cp "$OUT/classes:$CP" \
 org.scalatest.tools.Runner -R "$OUT/classes" -oD \
 -s heteronpu.continuous.GdnChunkStateTransferRuntimeSpec \
 -s heteronpu.continuous.GdnChunkStateTransferColdSpec
"$FIRTOOL" -format=fir "$UNMODIFIED_LOW_FIR" -o "$NEW_SV" \
 -warn-on-unprocessed-annotations -output-annotation-file "$NEW_ANNO" \
 --preserve-values=all -disable-all-randomization --verbose-pass-executions --mlir-disable-threading
```

JVM各阶段限单核/heap512MiB/RSS1GiB/CPU120s/wall180s/输出10MiB；firtool1.62.1限单核/RSS1GiB/AS4GiB/CPU60s/wall90s。实际SV发射0.044s/约16MiB/EXIT0，无warning/error诊断；annotation文件未输出。路径注释使跨checkout复现字节hash可能变化，不能编辑IR省略语义强求旧hash。

INTEGRATION.patch给统一共享实现差异。候选独立路径只为保留历史已固定source pins，最终必须合入唯一共享版本化接口；不能长期以候选副本充当五模型统一顶层。完整32头chunk算术、grouped prep、MoE、L3 Attention、上层config/receipt fence及同一完整4096顶层仍open。
