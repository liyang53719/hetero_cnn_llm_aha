# GDN32 全162源 compile-only：独立nonce启动候选

这份代码没有激活CI，没有编译或展开Top。仅替代上一版manual-only/未知Java17hash的人为阻塞；不更改任何生产generation白名单，不继承旧artifact成功。

## 两次提交，默认休眠

父级唯一发布者先提交 MERGE_FILES 中源码、固定pins和workflow，**不添加任何launch文件**。这个source commit可先经过原source CI。第二次提交只新增 `ci_launch/gdn32_compile_only_20261104_retry1.json`，且必须是source commit的直接单父提交，push event before/after必须对应这两个commit。validator要求run_attempt=1、固定nonce、独立generation哈希、确切workflow哈希，diff只能包含该一个A路径；修改旧nonce、混入其他文件、重跑或其他分支均拒绝。无workflow_dispatch依赖。

第二提交的JSON精确字段为：schema=`GDN32_FRESH162_COMPILE_ONLY_LAUNCH_V1`，source_sha=已审source commit，nonce=`gdn32_compile_only_20261104_retry1`，generation_sha256=`2b2f02d698f16a57ba696c52c4669a1226a68c5378efdc8ebe392cc1b9098f52`，workflow_sha256=source commit中 `.github/workflows/gdn32-compile-only.yml` 的实际SHA256。本文不是已创建launch文件；父级仍须独审、确认资源和激活。

## 复用真实生产JDK策略，不编造pin

使用workflow官方ubuntu-24.04宿主提供的 `JAVA_HOME_21_X64`。调用仓库原 `inventory_runner_jdk.py` 与 `fresh_host.py` 的既有策略：Eclipse Adoptium、21.0.13、runtime21.0.13+9或+9-LTS、x86_64；源/launch/run绑定的 `BOUNDED_FRESH_HOST_V1` 允许新宿主image被重新清点。保存ImageVersion/ImageOS、完整JDK文件hash/大小、受限symlink及public cacerts，再把每个真实文件pin传给随后supervisor，前后检查漂移。

这里的供应链信任根是GitHub官方hosted runner/toolcache及源码审查后的固定版本/vendor检查，**不是预先存在的官方archive SHA或旧JDK资格**。没有伪造新hash，没有下载未批准JDK或要求用户先手填尚不存在的binary hash。21.0.13+9供应版本不匹配时按原生产策略停止，不能临时换版本。fresh-host合同只允许inventory，不是绕过性能/数值资格的批准。

官方107个Maven依赖改由小wrapper先验证actual162，再调用固定原restore_model_inputs.py的完整legacy159 source_inputs/run门禁与下载实现；保留原SOURCE_AND_TOOLCHAIN_PINS字节，逐个JAR bytes/hash检查。不能再把最初155-source数组用作已合法覆盖的model159目录pin。全162源码在一个scalac进程中fresh编译，helper是列表内唯一新helper，循环依赖同时编译。编译classpath只有官方JAR，绝无旧project classes、旧leaf、cache或shadowing。

## 资源和输出

单核、SerialGC、Xmx1536MiB、RSS采样2304MiB、AS8GiB、CPU900s、wall1200s、cleanup30s；JDK inventory120s、下载600s，compile步骤42min、job52min（JDK/下载/编译及各cleanup的累加上限可容纳）。编译总watch512MiB、阶段输出160MiB、logs各8MiB，门槛available RAM3GiB/free disk2GiB。以上是执行上限，不是新测量保证。

无artifact/cache上传、二进制转移、安装、Top展开、RTL、DUT或运行步骤。只有typed安全status/数字/hash摘要进入stdout，原日志/receipts留同job临时目录。native compile通过仅证明源码可编译。源candidate终态仍仅在匹配响应/ready/身份稳定/其他clients可排空条件下成立，未匹配债务保持safe quarantine/resetRequired，不能声称bounded terminal、协议仿真或数值PASS。

发布布局严格使用MERGE_FILES。source selector默认仓库root或显式--base，不包含私有scratch路径。SELECTED_SOURCE_RESULT、当地compile closure、重建脚本和含本地路径的manifest不得发布/上传。

## R3独审整改

除JDK树以外，现在真实执行新明确compile-only scope的fresh_compile_host.inventory。该文件是production fresh_host.py的固定basehash派生，只把Verilator参数/目标变为可选且本job省略，所有Python3.12/Ubuntu24/ImageVersion、stdlib/native extensions、ELF readelf/ldd、根路径及JDK context校验保留。旧production文件不改；FRESH_HOST_BASE.json及exactdiff可审。输出canonical hostpins进入fetch与compile的pins，raw→canonical alias在前后校验，实际symlink每段绑定进入supervisor，不把非symlink raw路径假当symlink。

全量hash改stream file_digest，不再将JDK lib/modules整读进96MiB supervisor父进程。新safe_compile_summary仅输出最多8条已选repo-relative源文件/line/column与固定typed error类别，不输出错误原文、源码/caret、环境或任意路径；另有有限supervisor错误码、native_exit和cleanup标志。原始日志仍不上传。

新增host inventory上限300s/CPU240s/RSS512MiB，步骤42min/job52min覆盖全部JDK120s+host300s+download600s+compile1200s与四次cleanup和余量。其余compile资源门槛不变。新162 generation合入已独审Execute32 cancellation源；条件终态及unmatched debt隔离限制不变，native compile还未运行。

## R4依赖阶段修复

已诊断原run41776506114在启动下载child前的确定旧155/model159 pin冲突，完整证据和边界见FAILURE_DIAGNOSIS.zh.md。新的fetch/compile不可变pins包含model159与actual162的172唯一源码路径及全部元数据闭包；compile argv仍只有162。安全失败摘要增加有限pin role/相对label/expected与actual hash，以及有限JAR reason。无旧nonce重跑、native执行或发布；硬件generation不变。

## retry1独立激活契约（未激活）

源修复与新workflow先提交，默认不运行；监听路径改为ci_launch/gdn32_compile_only_20261104_retry1.json，nonce同名retry1。只有父级后续另一个单父提交仅新增该文件，且source_sha等于直接父source commit、event before/after精确匹配、attempt1、固定hardware generation和新workflow hash一致，才运行。历史once launch文件保留不改不删；不重跑旧run、不修改旧nonce以触发。此revision不包含新launch JSON，父级仍唯一发布/激活者。
