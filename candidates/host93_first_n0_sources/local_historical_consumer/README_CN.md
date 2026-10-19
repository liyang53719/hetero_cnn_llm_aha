# Local historical N0 consumer v2：SOURCE / pure mock only

## 最小生产变化

本片独立保留原CI pipeline。`pipeline_historical.py` 只把 COMPARISON 常量从原 `comparison/` 改为已发表的 `historical_comparison/`；31296 B / SHA `c3885d039b97861b17a29d74e6bf58448873d1ae476dbffa806a22a199b581cd`。完整逆投影恢复原31285-byte源，27个函数/类AST一致，`run_numeric`逐字不变。

原生产CI pipeline第13行仍选旧比较目录，第129–132行获取/安装新runtime，第141行重跑ci31214 reference；原stage_entry第6–7/37行仍绑定CI runtime acquisition。这些原件未改，本片不调用它们的frontdoor。

consumer v2与v1的唯一适配变化是将具体机器路径移出公共生产。caller必须显式提供三个受限路径；没有路径搜索、自动环境回退或新泛化配置parser。私有实路径binding在公共payload之外，绝不能一起发布。

## API与私有绑定

`prepare(repo, inputs, caller_pins, original_shared_stop, *, runtime_root, reference_file, reference_receipt)` 返回 `(run_numeric, front, preflight_observation)`。

- runtime_root：绝对路径，最终目录名必须是 `runtime`。
- reference_file：绝对路径，文件名必须是 `n0.f32le`，父目录名必须是 `reference`。
- reference_receipt：绝对路径，文件名必须是 `RECEIPT.json`，必须与reference_file同父目录。
- 上述路径及inputs/repo拒绝 `..`、symlink组件及非canonical路径。没有默认路径；caller从已批准的私有launch binding传入。
- 当前Python由 `sys.executable.resolve()` 取得，必须是CPython3.12且最终文件名 `python3.12`。固定historical profile仍要求30894944 B / SHA `fa67443527ed9647f760d807e2a38f26340757123e643c4639cf273ed15d5ea7`，由原helper.runtime_before真实读验。caller必须用该原Python启动总入口并带 `-I -S -B`；consumer不会换解释器。

返回front恰有 `inputs/runtime/reference` 三键，不含work。原run_numeric只消费这三键，numeric_work仍是caller单独提供的新私有目录。inputs目录身份最终由原run_numeric的canonical16（16项、94920448 B）前后门检查，preflight不虚称已经通过输入资格。

caller必须固定本片consumer及pipeline源码size/SHA，并用同buffer loader加载。`caller_pins`须包含SOURCE_PINS.json的13份固定来源；把同一个未改变的pins快照传给run_numeric。直接启动的是 `historical_comparison/n0_compare.py`，不是launch.py。

## 只读前置检查与原门

prepare在实际获准调用时，会固定读验13来源和派生pipeline，校验逐字逆投影后编译同一已验buffer。随后原helper.runtime_before仅流式核对historical Python、迁移runtime五个native文件和四个源码身份，不import数值runtime。

原reference私有receipt必须完整4466 B / SHA `b2ebccff3ad995a40e79a73974c332e22c5e042cae4cac8dc6a5ec55ed4fc046`。其原historical、source/raw2/runtime、BF16+FP32双SHA资格按固定内容消费；再重读完整786432-byte FP32 reference，强制原SHA `3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f`。不重写旧receipt、不重跑forward、不复制或伪填旧frontdoor阶段。

preflight observation独立标明existing reference reuse和静态runtime文件身份。当前AVX512、Torch/NumPy版本/build、4/1线程和deterministic仍由原historical comparator实际import及postflight重新验证；此处不能用旧receipt代替当前dispatch资格。

原run_numeric、historical comparator、reference helper和PINS均未再改。B退休/ACK0、完整196608值、shape/finite、原0.03125/0.005容差、bit_exact/hash_exact分列、源/输入/ELF前后身份、native exit/cleanup/RSS和30秒比较预算全部保留。

## 原6600秒与完整N0窗口

prepare的deadline参数必须是主编排原absolute shared stop，不是已扣尾储备的work_stop，不能重设成now+6600。`require_numeric_window(original_shared_stop)` 在prepare前后检查；caller真正调用run_numeric前必须立即再检查。

- 唯一总预算6600秒，120秒尾储备，N0完整3600秒。
- 原deadline剩余至少3720秒，故前置最多2880秒；不足抛 `Rejected('INCOMPLETE_N0_WINDOW')`，必须停止INCOMPLETE，不缩短N0抢跑。
- 返回 `original_shared_stop-105` 给原run_numeric。其内部再减15，恰是原stop-120；没有重置预算。
- 原supervisor callback同样硬夹原stop-120，不重复扣尾储备。
- 原Host3540s total/3510s work、compare30s total/15s work/25s CPU、8GiB AS/4MiB FSIZE不变。

call_phase仍接受 `(name, argv, work, env, limits)`，返回含evidence_root的dict并追加真实stages；必须复用既有supervisor的waitid/natural exit/reap/process-group cleanup/RSS合同。不要用裸Popen、合成receipt或CI原43-stage摘要替代新的本地续接合同。只追加真实capture/comparison完成项，不填造runtime/reference frontdoor完成项。

## SOURCE冷测

```sh
N0_CONSUMER_SOURCE_REPO=/absolute/fixed/checkout python -I -S -B test_consumer_cold.py
N0_CONSUMER_SOURCE_REPO=/absolute/fixed/checkout python -I -S -B -O test_consumer_cold.py
python -I -S -B test_inherited_numeric.py Numeric ReceiptLabels
python -I -S -B -O test_inherited_numeric.py Numeric ReceiptLabels
```

新增consumer17+17及原Numeric/ReceiptLabels21+21通过。覆盖固定/同buffer源、所有原函数AST、显式三路径leaf/parent/无fallback、Python/runtime失败、原receipt不可改标、源postflight、完整窗口不足、原run_numeric在pure mock中送出historical/显式runtime/reference argv及原预算和失败语义。stage_entry.py仅是继承测试的未改冷加载夹具，未执行获取或安装。

本片没有实际preflight运行、Host/native执行、数值runtime import、reference forward或实际FP32数组读取/比较。cold源码固定起点2b0f065831d670869753ba06ae7212919002f8e8；parent推进后13份来源内容仍一致。v1冻结片未改。本public目录可单独搬迁；测试仍须显式指定包含13份固定来源的checkout。

## 本次公开投影状态

TEMP_SOURCE，实际未执行。独立SOURCE审已通过，结论为SOURCE_GO_LOCAL_HISTORICAL_CONSUMER_ONLY；这只接纳固定源码与纯mock合同，未获实际执行资格。只发布列明12件安全源码/测试/元数据及计划纯尾；私有实路径binding、原reference私有receipt本体、runtime/wheel、实际库存、原日志、测试输出及临时副本均不入Git。COLD_RESULT保留作者冻结时记录，后续独审只补本节、STATUS与计划元数据，不改生产源码。

来源public MANIFEST 3289 B / SHA256 1f82e98fcc762433fecf2415f779ec4b0cf7f6ca7d4109b3079a6fcd0c41086b。现主backend/Host总编排仍另片，不能从本consumer源码或mock结果推断Host/N0实际PASS。原reference历史资格与当前local numeric结果严格分列；无workflow变化。

独审来源：review_local_historical_consumer_source_20261019T1645，MANIFEST 1426 B / SHA256 8029333009722a4307cd7c01fecbaef68fcaecddbdf92ff3283bc84a4e3c2877；SUMMARY 2392 B / SHA256 215b64c34796a8875e126226b674ca9a8495fcf8d2cdf42dfb2d87d9c5da1a9a。独立搬迁空工作目录中consumer普通/-O各17、原Numeric/ReceiptLabels普通/-O各21通过；23来源成员及13依赖逐件核验。独审未读取实际数组或native runtime，未执行Host或比较；整条续接仍须单独评审。
