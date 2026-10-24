# 既有生产组合与 retained-QK 控制交接小门

本片执行已有 source recipe 和已有 accepted-event 控制模型，**不重写生产
架构，不执行数值模型、Scala、RTL 或 native 算术**。最终仍为
`INCOMPLETE / exit 2`。未发现此安装/退休切口需要修复的生产差异，因此没有
为了产生代码变更而改动 Qwen2Block、owner、Matrix 或既有模型。

## 本次推进

1. 实际调用 `production_qkv_reduction/replay.py`，得到并验证 77 个源文件。
2. 实际调用 `attention_qk16_owner_route.prepare.compose`，沿原 recipe 得到
   并验证 13 个 donor 文件。没有用后续 partial BF16 donor 替换它。
3. 实际调用 `production_qk16_rebase/build_source.py`，五个 postimage 与原
   POSTIMAGE_PINS 全部一致。按原 PLANNED_SOURCE_PINS 从 overlay 或 production
   选择的 **72 个仓库 Scala 文件全部匹配**。另外 **20 个外部 HardFloat
   源文件正文未校验**，不宣称完成 92-source 编译闭包，不下载或启动编译。
4. 执行原 `attention_qk16_owner_route.model.GatherOwner` 与
   `attention_packed_stream.model.Client`，不是新写一个类似硬件的通用契约。
   在 16 种尾块长度及 token=127/base=112 的最后一块上，验证选中标签顺序、
   scalar ACK 阻塞、held result 身份、每项 score 一次提交，以及 result、done、
   completion 各恰好一次。done 尚未到达时不释放 ownership；completion 释放后，
   下一模型步才完成 group handoff。
5. 将上述事件与真实组合源码的 packedCommitted→result.ready、
   completion.fire→packedOwned 清除、attNextKey 的 !packedBusy 门对应。
   原 `attExpRead` 至 `attPVStart` 及后续逐头 softmax/PV 正文逐字保留。
   这里后半段是源码绑定，不是 Scala 行为执行或 softmax/PV 算术测试。

上述 17 例只是带标签的控制输入。token=127 的尾块检查**不是完整 M128 prefill**，
也不使用真实权重、mask 或激活值，不产生新的数值 PASS。

## 裸主线不同是预期组合，不是架构缺失

参考提交：`cacc259d8893754b8cae968b5355ccf37e5b79cf`。
Qwen2Block 的准确源码链为：

- 裸仓库：`9572763a636e77362f82d9fb6d8d9bc823be2ef1beda88929e227abd78a4b2d4`
- production preimage：`2118e101b61510adb3d57129a07fe6064dd3160aea341e495cd2bd1e6ab7a558`
- QK16 donor：`4375ccf715cf408975c3e45ae595955767b824404ef8337bb260ed807527dc1e`
- production QK16 postimage：`31b618680b4c750398a0dcf21fa34185dd9fc9b1732e370cfce502915814bd68`

原 `production_qk16_rebase/classcompile/README_PORTABLE_CN.md` 已明确这条组合
路线。不能把裸主线与 postimage 的区别解释为 production QK16 或 softmax/PV
不存在。原 sequential softmax/PV 已存在；本片没有新增或替换该架构。

## 模型入口的真实范围

完整 M128 继续复用 `portable_same_host_m128_launch/worker.py` →
`attention_packed_m128_same_host/entry.py` → `dense_block_reduce/check_public_numeric.py`。
其 profile 安装 Python PackedSchedule 和已校验的 combined ELF。
本片只读取这些入口源码，**没有 import 或调用其数值执行入口**。

`portable_same_host_m128_launch/input-contract.json` 在 inputs 和 composed_sources
里确实钉了 Scala 来源，但 Qwen2Block 是裸仓库 `9572763a…`，不是 production
postimage `31b61868…`。这属于源码 provenance，不能说完全没有 Scala binding；
也不能反过来当作该 production Scala 的运行或操作语义对应证明。
原 terminal_validator 明确要求 Python 模型执行为真、Scala/RTL 执行为假。

历史 cold M128 assigned27/observed28 PASS 不撤销、不重跑、不继承。六头 packed
Python schedule 与本 production 逐头 continuation 的操作对应关系仍待证明；
shared-bank ACK/release、384B panel、PV6 retention、最终资源债务、Scalar policy
以及 full29 仍未被本片关闭。不臆造新的 row-softmax service 或大改方案。

## 冷复现与边界

在含精确固定来源的 checkout 根目录：

```sh
timeout -k 2 30s python -I -B candidates/qwen2_composed_handoff/test_handoff.py --source-root .
timeout -k 2 30s python -I -B -O candidates/qwen2_composed_handoff/test_handoff.py --source-root .
timeout -k 2 30s python -I -B candidates/qwen2_composed_handoff/replay_handoff.py --source-root . --output /path/to/new/output
```

最后一条须输出 `INCOMPLETE` 并返回 2，已有 output 一律拒绝。需要 Linux Python
标准库和已有系统 `patch`，无安装、网络或编译。进程限制 20 CPU 秒、256 MiB
地址空间、一个允许 CPU；外层 wall 限制 30 秒。

120 个固定输入前后校验。选择的 namespace package initializer、旧 bytecode
及错误缓存模块来源被拒绝；不宣称这是执行任意不可信仓库的安全沙箱。
既有 recipe 复制/应用既有 Scala/SV 源码 patch，不调用 RTL generator。

最终 **24/24 normal，24/24 -O**，其中 9 项复用原 Control 测试，15 项是本片
组合/交接/来源反例。原测试 helper 的一些 assert 在 -O 下消失；本片 need()
与 unittest 检查仍生效，因此不宣称两种模式的旧 assert 覆盖完全相同。
没有 CI、完整 block、native 算术、Scala/RTL 或旧长任务的启动/重启。
