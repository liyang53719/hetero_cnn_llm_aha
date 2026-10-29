# 五 profile 复用三个独立 runtime：源码候选，未执行

基线实际 Git `fff882f4694fb9c2eea11b361cf40a33a3577b20`。仅修改原 selected materializer 的 runtime 获取/归属接线，官方 reference_command、程序生成、provider算术、权重、原 BF16/FP32、4096 MAC/128 token、P0观察门均不改。

## 具体入口

1. 根审 `ADOPTION_BINDING_PROPOSAL.json`（原三 INSTALL_ONLY、三 native0/cleanup、原 wrapper/Python、已锁本地 Torch/三框架 archives；尚无新侧车）。外部严格 supervisor 预算准入后，可运行新 `prepare_shared_runtime.py --repo REPO --binding BINDING --binding-sha256 SHA --output OWNER/shared_runtime_identity --execute-reviewed`。
   - 不安装、不下载、不导入 Torch。调用固定原 derive_sidecar 源码，从原 archive产生三份侧车并要求原固定 SHA；核实对应installed module/native，保留原 INSTALL_ONLY receipt不造新算术资格。
   - 完整 snapshot 三个 import_root（含3.5 wrapper的 ROOT/src 与 ROOT，不只 site），目录/文件/内部alias均入账，仅固定host Python文件允许外部alias。这是安装树快照/漂移约束，**不是全传递框架源码从archive逐字证明**。
   - 输出 `owner/SHARED_RUNTIMES.json`；此步骤尚未执行，当前不能提供实际 shared owner SHA。
2. 原 `prepare.py` 新参数 `--shared-runtime-manifest FILE --shared-runtime-sha256 SHA --owning-job-root OWNER` 三者必须齐备。此分支不运行单profile installer，而通过 lease取得原wrapper；映射固定 P0→Qwen2 4.40.1，P1/P2→14e738 dense，P3/P4→42ca970 MoE。三安装不能互换；仍不是所有模型共用同framework。
3. `shared_runtime.lease(manifest, expected_sha, owner_root, profile, profile_out)`：context 返回仅该profile的原 runtime entry。资源worker可将原 provider-only bounded supervisor包在lease内；必须确保所有原进程cleanup完成后离开。不启动新的参考/权重下载，仅接口授权并不构成执行批准。

## 身份与生命周期

- 外部pin owning manifest，不用其自报SHA授权。原 receipt/native0-stage/wrapper/Python、原独立侧车SHA、实际module/native、完整importroot树pre/post验证。原Python3.12/x86_64、P0 AVX512、原8GiBfree门不降。实际host版本是3.12.14；不把lock说明文字3.12.15冒实际版本。
- 稳定 OWNER.lock 的协作shared flock覆盖完整参考/RoPE/provider/emit_tsv；每个selected lease streaming重hash所选树，非仅小元数据。其它framework不重复安装，不把3份树每profile全扫。
- profile OUT不得与任意三个importroot或owner metadata目录重叠，检查在mkdir前。metadata不得自包含进树。没有删除API；全部运行引用和唯一证据保留，不自动cleanup运行时。flock不是OS不可变保障/对恶意外部写者的隔离。
- 原V1物料生成在lease内，**postcheck成功后**才发布共享使用记录并接V3；postcheck失败保留原物料作失败证据，不发布看似成功V3/CONSUMER_ARGV。
- 当原isolated模式被明确选用仍保留旧实现；新shared分支才复用3份，不偷偷改变旧语义。

## 当前未闭合

- 尚未调用adoption：侧车/全树ledger/共享owner实际pin仍缺。实际三个安装成功只是INSTALL_ONLY；没有新reference数值资格。
- 未启动provider/Torch/DUT/EDA，未发布源码。根必须先审外层wall/RSS/磁盘live bytes和精确输入binding；8GiB不足会拒绝，不为复用降低门。
- 单profile20000秒/完整五块350分钟预算、有效MAC数值、完整RTL通过均未由本候选解决。MoE原Torch路由、小ID契约待定不变；P0 gate/up仍 REQUIRED_UNOBSERVED/INCOMPLETE。

本版 adoption 明确限定已保留的原 sample.py SHA57e617…安装路径，交叉核原 native argv、BINDING_R2 的output/源码pins，不接受任意同family的其它job native receipt。未来另一installer的fresh结果需另审身份接线，不由本schema自动放行。
