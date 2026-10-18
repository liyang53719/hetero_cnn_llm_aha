# 固定 raw13 → provider14 转换器复现源码

本包只含源码、固定规格/来源pin、原冷测摘要及小型安全实际计数。没有权重、bin、完整日志、环境路径库存或实际输出目录；没有网络/native/EDA或reference数据。原source和actual资产未改。

## 来源、原样保留与证据范围

以下5文件与已审且已实际执行的原SOURCE逐字节一致：convert_providers.py、test_cold.py、CONVERSION_SPEC.json、PROJECT_SOURCE_HASHES.json、COLD_TEST_RESULTS.json。未重新设计入口或改变固定expected。规格内7个项目相对source pin与6个原FunctionDef pin，包含真实commit/Git blob/SHA；PROJECT_SOURCE_HASHES固定本地converter/test源码。

原冷证据是normal18项与-O同18项，不是36个独立case；包括tiny transpose/FP32位映射、拒NaN/Inf、文件边界/失败保全、blocked SIGALRM、合成RoPE M16。本次迁移只作内容/同bytes检查，没有在新目录重跑冷测、固定M128转换或实际raw读取。原冷摘要中的“actual=false”仅描述该原冷测范围。

原实际转换已产生14 provider / 94,916,608B。SAFE_ACTUAL_FACTS.json仅保留计数、scope和来源/receipt哈希；2775B实际receipt的14项有序name/bytes/SHA与既有规格全部一致。本次打包只读该小receipt，未读取任何provider/raw payload；不把metadata核对冒充新的完整payload独审。canonical loader/full host/launch仍未建立。

## 固定转换与提交边界

固定raw13总94,382,080B。7矩阵仅BF16转置，gamma/bias/x按原小端word<<16映射为FP32LE；x先检查全部256 embedding行finite，再选token0..127。RoPE保留原double libm公式与FP32存储、M128及padding身份。任何旧expected SHA不一致就失败，不换公式或reference回填。

每raw只读成一个私有buffer，核同bytes SHA后转换；逐provider块≤64KiB写新.part，长度/SHA及回读通过后不覆盖提交。14项全部通过才产生PROVIDERS.json；失败保全，不清理、不重试、不更改expected。新裸provider文件不冒充旧wire framing；不生成两张metadata表，不调用loader、不授予DDR写或launch权限。

固定门：AS≤256MiB、CPU≤60s、共享wall120s、输出≤128MiB，源检查时间计入deadline，保留更低继承限制；最大raw buffer27,525,120B。阻塞SIGALRM/已有timer先拒，不自动解封。output必须fresh且位于repo/raw-root/源码包之外。

## 相对参数入口

默认仅源检查，不需要raw路径：

```sh
python -I -S -B convert_providers.py --repo REPO
```

原冷测可复现命令（本包迁移后未重跑）：

```sh
python -I -S -B test_cold.py --repo REPO
python -I -S -B -O test_cold.py --repo REPO
```

后续实际执行必须另有授权，并使用已验证raw及全新输出；本源码包或SOURCE发布不授权再次转换：

```sh
python -I -S -B convert_providers.py --repo REPO --raw-root VERIFIED_RAW_ROOT --output FRESH_OUTPUT --execute
```

实际进程终态、完整receipt和独立资产审查应共同使用；部分.bin或源码测试通过不能替代完整provider身份或canonical16装载证据。
