# M128 完整终态取值与 oracle 隔离：源码准备包

状态：NOT_READY / default-off。这里没有可执行 worker、运行授权、DUT 数值结果、事件实录或性能通过声明。八个 Python 运行后像保留已审原字节；本包只发布源码、逻辑身份和脱敏证据。

## 已闭合的范围

私有 launcher r3 的联合源码/纯 mock 独审已通过，原审查 SHA256 为 `7bb4b3194eaf1b64e0169edff21ba383310e7c260f8ee96664f28eafcb88cc9d`。它覆盖原 47 个源码/路径检查、11 个全 synthetic 接线检查及 12 组独立组合负例，均 normal/-O 通过。公开投影不是原审查字节，原 SHA 不能直接校验公开 JSON；本包 PUBLIC_MANIFEST.json 另行绑定公开文件。

- 新 runner 要求一个完整 rows=128 profile，不是八次 M16 拼接。原单次 prefix、pc12、O/FFN suffix 和完整 live terminal 保留；wall_budget <=1800 上限未提高，预算批准尚不由本包提供。
- 完整终态后透传原 readonly x allocation 的快照、原单次 SiLU seal 返回 bytes，以及被动观察到的真实 cos/sin `[128,64]` half-domain words。不得重算、扩展成128维或补造物理上不存在的中间值。
- 精确 oracle root 门要求完整 regular-file 集合、canonical path、inode 与初始 fd/maps 清查。绝对别名、软/硬链接、fd/proc-fd/mmap 及所有相对 open 拒绝都会 sticky 记录。DUT 即使捕获拒绝继续，完整终态后也不能 seal/compare 或报告 inventory complete。
- 原 `_live_terminal` 在单次 comparator 开门前再次检查，随后关闭 oracle 门。普通监测安装/清理故障保留 sticky FAIL 并允许原 driver 继续；监测 cleanup 不覆盖正在传播的原 driver 异常。真正的 SystemExit/KeyboardInterrupt 取消不承诺继续计算，也不产生成功 seal。
- fd 清单目前仍需未来真实 worker 现场落盘和审查。直接 read/pread/readv、native syscall、fd 传递及并发路径竞态不是 Python audit 的内核隔离范围。它不是通用或恶意同进程 sandbox。

## 源码与跨片依赖

`postimage/` 内八个 Python 文件逐字等于私有 r3 对应后像。`SOURCE_ONLY.patch` 与 `compose_source_only.py` 只重建这些源码，不生成运行环境。基线是旧 ordered-fullgraph 的 composed candidate 后像，不是 raw main；尤其先前 `matrix_service.py`、`matrix_numeric.cpp` 的 composed pins 不能拿 raw main 文件冒充。它们不因名字相同而合格。

Trace r2 的公开候选已位于 `candidates/qwen2_ordered_event_stream`，发布 commit `98d73a892d93c5f3b7b0b190b5255a6b82d2b781`。本包 bridge/service_trace/stream 原字节与其精确 r2 一致，联合 runner 是另一个新 M128 后像。Trace 自己的 M16 runner、旧 source pins 或局部审查都不能代替新组合准入。COMPOSITION_PINS.json 分别记录旧基线、公开源码 patch、后像及两个私有原件身份。

重要：RoPE 原运行配置含私有绝对路径，因此没有交付 `postimage/.../rope_operand_capture/SOURCE_PINS.json`。未改的 rope_capture.py 顶层会读取该文件，所以此未绑定公开包不能正常 import RoPE，更不是可直接运行的 normal binding。ROPE_SOURCE_PINS_UNBOUND.json 只是明确禁止 runtime 的逻辑模板。未来必须从精确 source root 生成真实本地路径配置，取得新 hash 和独审；私有原配置 SHA 不授权这个新配置。当前 composer 不生成它，也不提供 AST alias 或 source-rewrite 作为运行资格。

## 复现与缺少的闭包

从仓库根只运行新增的轻量 stdlib smoke：

```sh
python -I -S -B candidates/qwen2_m128_terminal_capture_prepare/portable_smoke.py
python -I -S -B -O candidates/qwen2_m128_terminal_capture_prepare/portable_smoke.py
```

这只是新增 6 项 public smoke，非原 58 项重跑。它检查源码身份/解析、patch 元数据和 synthetic hunk、错误基线拒绝、synthetic sticky 门、default-off、RoPE 明确未绑定。没有 target import、ML/native/service 或张量运算。原 58 项测试源码原字节留在 historical_tests/，原日志在 evidence/；由于原目录布局、外部 composed source、完整私有 closure 和准备脚本未公开，不能声称 fresh checkout 全复现原 suite。TEST_EVIDENCE.json 列出具体依赖缺口与各自日志身份。

有精确旧 composed candidate source root 时，仅重建八个文本后像到一个不存在的新目录：

```sh
python -I -S -B candidates/qwen2_m128_terminal_capture_prepare/compose_source_only.py --source-root "$EXACT_OLD_COMPOSED_CANDIDATE_ROOT" --output-root "$NEW_SOURCE_ONLY_DIRECTORY"
```

Composer 先核基线 SHA、逐 hunk 应用、核后像字节，全部成功才写新目录；不会修改旧源，也不会 import 目标或生成运行配置。它不是完整源码树组装器。仅有 raw main 或 trace 候选不满足基线检查。

外部依赖包括原 316-file composed source、normal722 与唯一新增 combined ELF 所成的723-file闭包、完整原 provider14/raw13、真实现场 modules/maps/fd、精确本地 source pin 配置、fresh 官方 M128 reference 的最终身份、受审 comparator、预算与一次运行授权。这里公开15 roles/9 methods、20 ELF节点/53边/6 roots 的身份摘要及输入 hash/shape/dtype，不附全部723-file路径清单或任何 payload。Git/libpcre2 已在 normal722 内，所以合并是723，不是725。先前750个文件的 opaque hash 检查不是未来 pre/postflight，也不授权执行。

## 不可升级的结论

官方配置保持32768、rope_theta=1e6；项目256差异单列，未改阈值或声明等价。repeat_k/repeat_v/logits/mask 没有独立物理 tensor，scores/prob/softmax 仅因果位置部分覆盖，不声称 full29 PASS。这里没有真实 RoPE capture、数值无干扰、DUT PASS、RTL 或性能验收。固定4096 MAC 与历史 legacy PV 63.57% 不是性能通过。

REVISION_HISTORY.json 保留 r1 的 RoPE/非 sticky 门失败、r2 的 trace cleanup 异常覆盖失败，以及最初725计数断言错误。旧冻结件未改；本包不将它们改写成首轮成功。
