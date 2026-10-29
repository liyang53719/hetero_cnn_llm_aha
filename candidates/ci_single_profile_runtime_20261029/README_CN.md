# TEMP：单 profile fresh CI 官方 runtime

新候选身份，不改旧 all-runtime 包。建议仓库路径 `candidates/ci_single_profile_runtime_20261029/`。

## 入口
`python3 -B prepare_runtimes.py --repo REPO --output OUT --profile N`
只返回plan，无下载、安装、Torch import或输出目录创建。显式追加`--execute-reviewed`才进行真实fresh setup；外层必须使用已审资源监督器、single-heavy-job调度。

| profile | 唯一安装 runtime | 获取内容 |
|---|---|---|
| P0 | qwen2 | 原25 runtime wheel +锁定pip bootstrap，共26 wheel |
| P1/P2 | qwen35_08b | 原38 wheel +精确14e738官方archive |
| P3/P4 | qwen35_35b | 原38 wheel +精确42ca970官方archive |

35B作业不安装0.8B；provider直接使用35B自身已锁NumPy wrapper。源码包中的其它版本锁只是固定registry，不会触发其它版本artifact获取或安装。

## 输出合同
`OUT/RUNTIMES.json` 的 `entries` **只有选择的一个runtime key**。该entry含wrapper/site/receipt/sidecar，格式与原all-runtime合同相同；这些指定文件位于OUT内。顶层增加profile与selected_runtime；provider_python指向所选runtime自己的wrapper。
成功状态仅 `FRESH_SELECTED_RUNTIME_NOT_REFERENCE_TESTED`，不迁移旧reference/Chisel/RTL PASS。

## 保持的验证
原archive/wheel锁、官方installer/driver/guard/backend源码、archive-derived sidecar、安装源/native hash验证全部保持；原安装函数的AST与旧包逐字逻辑一致。P0仍必须AVX512f及4threads；P1–P4保留DEFAULT/1thread，不无故要求AVX512。旧8GiB启动磁盘下限、下载/安装时间边界及失败保留逻辑未降低。
新job局部source root只用于满足原installer的root/work约束，不借旧runtime或全局cache；真实解释器身份进入新receipt，未声称Python patch版本/OS数值等价。

## 本次实际验证
9项轻量测试正常/`-O`均通过：五profile映射、非法输入failclosed、所选artifact集合、单entry条件installer调度、固定sidecar合同、五plan零副作用。静态核对所有原安装/下载/sidecar验证函数AST未变。
**未下载、安装、import Torch、执行参考或EDA。** 单profile真实CI setup/资源峰值/完整数值仍INCOMPLETE。权重选择、完整256专家及reference/provider执行由上层单profile准备器负责，不能用runtime选择缩减模型。
