# 固定 canonical16 同 RAM consumer：纯源码复现候选

本包是原已执行源码的有限、可移植投影。已观察一次有界执行成功：16个真实RAM span全部匹配固定SHA，run14.692706秒，四阶段exit0且清理确认；安全数值见BEHAVIOR_SUMMARY.json。该摘要不冒充独立actual复核结论，本次打包没有重跑native或读取payload。默认 run_behavior.py 只核9份小源码，不执行 metadata/native。后继实际执行仍须在已授权资源门内。

## 固定原输入到实际 RAM

四个 C++ header 原样复制自已发布 development_snapshots/canonical16_binding_source_20261018：InitializationRam、标准 SHA256、SameBufferLoader、固定 canonical16 factory。没有改 primitive/loader，也没有开放 expected/地址/预算 CLI。

consume_canonical16.cpp 使用该 factory，按 commands、descriptors、wq、wk、wv、wo、wg、wu、wd、gamma0、gamma1、bq、bk、bv、rope、x 顺序打开 binary ifstream。文件须 regular/非symlink/精确长度，默认异常 mask；load_next 自身严格 EOF、流状态和 stream SHA 判定，失败永久 poison。成功后 finish 完整声明覆盖 seal + 同 RAM SHA，再一次兑换私有 token + 同 RAM SHA。

拿到 const view 后逐项 read 检查初始化 mask、长度和相对同一 backing array 的实际指针偏移，并再计算实际 span SHA。16项全过才输出 index/name/base/bytes/actual_sha256、coverage摘要。actual_sha256 是第四遍 SHA 的返回值，不是打印 expected。父 Python verifier独立逐行核 INPUT_SPEC，拒绝缺项/重复/顺序/额外字段/布尔冒充整数/错误hash。不会额外调用 view.reverify，避免第五遍。

覆盖仅声明16输入共94,920,448B，不声称全部213,473,600B arena已初始化。尚未使用输出scratch、DDR写权限、AXI、Host、DPI、launch或EDA；这些资格均为 false。const view借用只在loader生命周期内有效，单线程，无对抗任意const_cast/data race保证。

## 两表与14文件来源

两表复用已发布 development_snapshots/canonical_host_metadata_source_20261018 的 replay_metadata.py、SOURCE_PIN.json、EXPECTED_LAYOUT.json，三个文件逐byte复制并pin。metadata子阶段运行其原 CLI；原脚本对8个原项目模块同bytes hash+compile，抑制既知sys.path插入，不调用数值pack_words，不导入NumPy/Torch。原样产4个小metadata artifacts；本consumer只加载host_commands.bin 384B和host_descriptors.bin 3456B。父门从这两个实际文件重新SHA，与旧固定618cd4db…/1e4d35da…及子阶段log交叉核验。小产物仅本地actual目录保存，不作为SOURCE提交内容。

14文件来自成功PROVIDERS.json，精确receipt SHA6175d87d5913f9370d3723ccb6d6282cc24e9b0653c0963a7ccbdcb4697c3202。父门只读该小receipt并检查固定条目/目录/size；它不是payload信任替代。子consumer仍真实读取全部14文件，重新验证stream和实际RAM。原provider目录不改，不复制95MB输入进build，不读reference或旧work/framing。

## 有界执行与失败保全

复用已审 run_behavior.py 的 WNOWAIT保锚→先killpg→reap→只读确认group absent逻辑。require/digest/save/group_state/observe_exit逐函数不变；bounded只增加AS参数、设置对应RLIMIT_AS、记录对应receipt三处改动，冷测逐字归一核验。原清理5秒/阶段、FSIZE4MiB、core0、log接受上限64KiB不变。compiler身份在未来实际执行时动态读取并SHA，不库存当前机器compiler路径/hash。

- compiler_version：wall5s、CPU2s、AS256MiB
- compile：wall30s、CPU30s、AS256MiB；C++17 -O0 -Wall -Wextra -Werror -pedantic，单TU
- metadata：wall10s、CPU5s、AS256MiB
- run：wall120s、CPU120s、AS1GiB
- 上述墙时总165s，另每阶段最多5s清理；没有自动重试/放宽预算/替换hash。

两backing arrays固定426,947,200B（约407.17MiB）+64KiB输入chunk+小metadata/标准库开销，不存在额外完整provider/RAM副本。总SHA恰4×94,920,448=379,681,792B（流、finish RAM、token RAM、view RAM）；初始化mask/覆盖检查另有线性扫描。已观察一次run为14.692706s；120s仍是固定硬门，不能保证其他机器性能，不因达到上限自动增预算。256MiB不能容纳真实factory；1GiB为本阶段明确界限。

失败保留stage receipts/log/build。CPU硬杀/异常也由保锚监督记录；未获完整成功RESULT不得宣称canonical输入完成。任何超时、编译失败、hash不符、cleanup unknown均失败停止。

## 冷测与命令

18个 unittest 方法，普通及 -O各通过；其中8个复用mock清理场景，其余测source-only、固定pins/搬迁/漂移、结果schema拒绝、AS记录、mock全链、tiny metadata实际hash、receipt拒绝、监督差异及TU实际span语句。18+18不是36独立案例，mock成功不能替代真实consumer通过。

    python -I -S -B test_cold.py
    python -I -S -B -O test_cold.py
    python -I -S -B run_behavior.py

正式 SOURCE 审闭合及执行授权后，可在新的结果目录复现：

    python -I -S -B run_behavior.py --repo REPO --providers VERIFIED_PROVIDER_DIRECTORY --output FRESH_OUTPUT --compiler c++ --execute

FRESH_OUTPUT父目录必须已存在，目标不可存在，须在repo/provider/source树之外。目录路径不得含symlink。无网络、依赖安装、reference或EDA。

## 可移植包边界

复制并保留原四hpp、单TU、runner、cold及必要相对source pins。所有执行源码与9个build输入逐byte不变；仅文档/计划状态/冷测摘要投影，以及新增安全数值摘要。SOURCE_PROJECTION.json枚举有限变化。所有输入来源均须真实可用且匹配pin，缺失或漂移即失败，不取网络fallback或生成替代payload。PROVIDERS.json身份绑定本次确定性转换receipt，无法复现相同receipt时也不放宽。

本包无ELF/生成metadata二进制/模型payload/完整日志/当前系统compiler路径或hash库存。runner源码保留未来运行时动态计算compiler身份及记录receipt的逻辑；未来actual目录可能包含机器身份和ELF，不能直接当源码包发布。四hpp顶部的历史SOURCE/UNCOMPILED注释原样保留，描述最初来源阶段；当前实测范围以本包摘要为准，仍不授予Host/launch。
