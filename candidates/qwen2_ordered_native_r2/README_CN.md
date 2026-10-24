# 默认关闭 ordered fold：真实单 Attention M1/M2 小数值验证

## 已完成与边界
本包绑定 owner 接入提交 a672a56feef9b661f6682bedfcbd702d1ddbc3fa。R2在独立静态审查及确切配置授权后，仅执行一次M1，再一次M2；每次包含default/off与ordered/on两臂串行运行。两臂均使用正常import的原OfficialAttentionOwner、原MatrixService与原唯一ScalarService，没有synthetic Matrix/Scalar替身；每臂正常acquire、实际结果消费ACK、done、owner终态ACK、释放，重置同一个原生accumulator后再跑下一臂。

- M1：1536输出word、12个score，与旧路径和独立原Python recipe逐字一致。每臂实际native FMA442368。ordered scan192/add_stripe192/scale12/retire12，live-held核验420次。
- M2：3072输出word、36个score，三方逐字一致。每臂实际native FMA933888。ordered scan384/add_stripe384/scale24/retire36，live-held核验864次。
- Scalar Add/Mul请求分别减少192/12与576/36；BF helper另减少24/72，不把BF当硬件Scalar请求。
- 两次child/launcher均exit0，无超时、无剩余进程组。每次1CPU、地址空间1GiB、CPU30秒、wall45秒，实际墙钟约1.369/1.772秒。17个实际映射ELF均通过完整hash/size/inode/device检查，输入完整payload重验成功。墙钟或owner/model ticks均不是硬件周期。

输入为冻结qr/kr/v的token-major M1/M2前缀，是明确声明的单Attention组件边界，已bias/rope，不是raw13/provider14→完整block。独立比较在两臂真实终态ACK后才执行；原Python控制/recipe不调用候选OrderedFoldWork，但与strict lane使用的基础exact RNE helper有共享，这一点不隐瞒。没有读DUT结果生成期望，也没有改容差。未对不同运算顺序的官方PyTorch score宣称逐字一致。

仍未完成：真实direct/PublicExecution前缀及full suffix、完整M16/M128、新完整observer资格、Chisel执行/RTL/频率/固定4096 MAC完整block周期分母。没有80%或90%利用率结论。本次原生Matrix FMA计数是实际模型端执行操作计数，不能直接解释为有效MAC利用率。

## 小补丁与资格策略
五个执行文件：admission.py锁独审receipt的exact config/source SHA；launch.py固定一次账本/预算/M1→M2门；worker.py核runtime、映射、分阶段证据；harness.py驱动真实owner；runtime_closure.py纯stdlib验证依赖图。默认模型路径不变，参数仍显式opt-in。

现有combined ELF不重编译，SHA c03ab303a6d0780f379a13f8f0339872a6b00e066c8481b8e8f39a16243cf5b8，profile2只QK16，PV使用legacy profile0，不是旧packed PV2库。SOURCE_PROFILE_PINS.json列实际316文件的运行源码组合身份；它包含旧服务guard要求的源码与新Python owner overlay，不能混称为selected Chisel postimage的硬件执行。

最终静态闭包5roots、19ELF、51依赖边，仅Python、Git、combined、NumPy eager multiarray/linalg及其传递库。明确排除compiler/as/ld、NumPy测试/随机/FFT懒载扩展。RUNTIME_ELF_PINS.json给脱敏精确身份，不发布绝对运行路径。完整加载maps及父子birth identity、阶段日志保留私有，公开摘要固定各原始文件hash。

## R1失败不改写
之前唯一R1 M1失败于终态后的映射检查：libz未入清单。exit1，无残留，M2未运行，无最终RESULT，不能叫M1通过。R1还发生最终测试CLI调整后config未再次锁独审hash的问题；事后重建完整旧SHA证明仅test条目的bytes/hash不同，但该流程缺陷仍保留。

R2新目录、新manifest、新独审receipt修复两点：递归精确DT_NEEDED闭包；启动前强制exact reviewed config/source SHA；所有maps在校验前保存，逐项收集差额；每阶段flush/fsync摘要。R1原目录/账本/失败证据全部不变。详见validation/R1_FAILURE_RETAINED.json。

## 可复现步骤
冷测试不导入NumPy/native、不生成RTL，可从完整main checkout根目录运行：

```sh
sh candidates/qwen2_ordered_native_r2/run_cold.sh .
```

本批实际已执行27项gate测试的-I/-I-O两模式及7项ELF mock测试。测试覆盖config一字节改变拒绝、漏DT_NEEDED库/边拒绝、不可达额外库拒绝、未知映射先完整落盘后FAIL、原finish释放顺序、reference阶段门与一次性账本。冷测试PASS不是native资格。

真实复现不是下载权重或一条自包含命令：需具备SOURCE_PROFILE_PINS的完整316文件已组合源码、原已pin Python/NumPy/native ELF、INPUT_PINS三份私有输入、原独立Python oracle源和真实Git身份。数据、ELF与私有路径均未上传。本包不含原私有config可直接运行副本；迁移路径必须生成新的manifest并重新独审，不修改历史pins。既有公开owner composer只组合其局部11文件，不能假装它独自提供完整runtime闭包。

1. 通过elf_closure.py --roots-json ROOTS.json --output NEW_CLOSURE.json对明确5根只读readelf建图，不用ldd、不加载库；核RUNTIME_ELF_PINS和真实路径。完整manifest同时绑定源码、输入、oracle、Git和运行库。
2. 独审新manifest，生成status为PASS_STATIC_REVIEW_REQUIRES_ROOT_EXECUTION_AUTHORIZATION的receipt，绑定config SHA、五执行源SHA及同一资源上限。receipt不代替执行授权。
3. 获得对应执行授权后，使用下列模板。已有attempt不可重用；没有M1全部终态成功不得M2：

```sh
python -B -I candidates/qwen2_ordered_native_r2/launch.py --config EXACT_CONFIG.json --review REVIEW.json --review-sha EXACT_REVIEW_SHA --m 1 --output NEW_M1
# 仅在同profile M1完整PASS且授权覆盖时：
python -B -I candidates/qwen2_ordered_native_r2/launch.py --config EXACT_CONFIG.json --review REVIEW.json --review-sha EXACT_REVIEW_SHA --m 2 --output NEW_M2
```

此次实际config SHA b1fe0eaa01065f507f79755f1eb446f727701f899908b7f5e3a3af1646f4ca7c；静态receipt SHA d1f9d815c7f972ebac2a1c605603304b0c8eced93e369f9cd9aebafa75584b97。路径迁移后不可继承这两个执行身份。
