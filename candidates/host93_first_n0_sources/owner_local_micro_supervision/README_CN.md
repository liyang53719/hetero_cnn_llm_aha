# Owner 局部诊断的有限生成、编译、运行接线（SOURCE）

本片仅准备一次 fresh QwenOwnerKernel 顶层合法端口刺激的固定调用方。源码准备阶段没有运行 Verilator、编译器或 RTL；尚无生成后 ABI、观察字段或实际目标边界成功资格。driver 协议与数值语义由单独固定的七成员生产包负责。

## 固定复用与最窄差分

- 复用已有官方 revision `4e194cc3ec8e27b18e17f80d7f99c15f984bbdae` 的 473 成员 backend，原唯一 seqnum 补丁、已成功四阶段 tiny receipt、原实际独审收据。每阶段前后重新核工具、配置 runtime、源码及依赖；不重做 backend 或五工具资格化。
- 原 319 iDMA 成员、13 retained 成员、相同完整 SV、307 个编译源、8 个 include 根、4 个 define 与 4 个原 VLT 保持。第五个 VLT 仅来自固定 owner 包；原精确告警约束不放宽。
- 原 generation argv 先逐项匹配历史 receipt，再仅改 top/prefix/driver/Mdir，追加 owner VLT。原 make 参数仅改对应 mk 和 target；保留 `-j1`、三个 `-O0`、固定编译器/AR/SHELL/MAKE 与空 OBJCACHE。
- 全新 owner 模型和 archive 必须在 fresh work 中产生；旧 Host archive 不作为 owner 实现复用。输入采用已验 N0 FP32 与原 Wq BF16 文件，各自固定大小/SHA；局部 fixture 不执行 N0 前缀，也不宣称重现历史 Host 的具体状态。
- 原 generation census 仅三条、原 cluster witness 函数仅四条字符串投影，逐项计数并逆变换恢复原 buffer。PROJECTION.json 给出原/派生身份。原 ci_support_v3 字节完全不变。
- 新生成 root header 才执行 95 个标量字段的唯一名称、CData/SData/IData/QData 类型及精确位宽核验。新顶层 header 必须逐项等于固定 196 端口表（150 input、46 output）；同时复验原参数化 cluster、库链接、seed 与 seqnum 初始化门。未知/缺失字段具体拒绝，不从旧 Host header 推定成功。

## 一次预算与异常边界

最早父 outer T0 通过唯一固定环境键传入私有 launcher，再由同 buffer 入口传给 main。读取 COMMAND、解释器、private binding 和源码的时间均计入同一个 1320 秒截止。

- generation：总 360 秒，原监督的 work/CPU 上限 345 秒，15 秒用于原 cleanup/postflight。
- build：总 600 秒，work/CPU 上限 585 秒。
- run：总 300 秒，work/CPU 上限 285 秒。
- 尾部落证：至多 60 秒，且不得超过原总截止。
- 全部阶段 AS 6 GiB、单 CPU；初始与每阶段重核 MemAvailable ≥ 8 GiB、磁盘 ≥ 3 GiB。
- 每阶段前以及前验之后，均须剩余完整该阶段窗口加 60 秒尾储备，否则 INCOMPLETE 首停。初始 hash、阶段间后验占用同一总预算，因此以上不是承诺三个阶段一定完成的 ETA。
- 父 outer 最迟在 T0+1310 发 TERM，5 秒后 KILL，并留最后 5 秒父落证；其命令只能普通 `-I -S -B`，不得用 `-O` 跳过固定父模板中的 assert。

任何 native 非自然 0、cleanup/未回收状态、资源超限、后验失败即停止，不开始下一阶段。保留第一个异常和原 traceback；日志观察、保存、timer/handler 恢复异常只在没有原异常时成为主错误。RESULT 仅投影现有固定安全边界/码；未知值 null，不保存任意异常文本。

完整 run native.log 使用原 identity 读取其全文件大小/SHA，最大 1 MiB；不截 tail，不解析 progress 或布尔以授予资格。driver 最多 18 行、有界 JSONL 的目标/失败/未完状态，需结合原 native exit、WNOWAIT、cleanup、源/工具及实际日志独审。某个保存/后验失败时，RESULT 可能已有完成阶段字段，仍须以原异常与 outer exit 综合判定，不能单独用 status 赋予 actual 成功。

自然 0 在本调用方只表明三个有限监督阶段完成，尚须独立实际审读末行。full job/full block 为 false，历史故障重现、official/application accuracy、typed-to-RTL 均为 null。部分 job 的 outstanding debt 不会因诊断退出被说成退休或 job 成功。

## 准备与发布

private binding、精确 COMMAND、父 outer、实际机器路径及现物日志保留在本地 private 目录。BINDING_TEMPLATE.json 是未绑定示意，不可直接执行。公开 SOURCE 只包含源码、固定相对来源身份、有限合同和纯 mock 结果。独审通过后由父执行唯一具体命令；本片不自行启动 native。

v2 相对本片 v1 的主生产只改 CONFIG_PIN 和 DRIVER_PIN，消费 driver F01 窄修后的七件 manifest；supervision.py 原字节未动。原 v1 和全部历史失败材料保持。

## 纯冷测边界

67 项 × 普通、`-O`、搬迁普通、搬迁 `-O` = 268 次通过，0 failure/error/skip。36 项检查固定监督序列/时窗/首错/落证，31 项检查固定加载、七项源码投影、argv映射、95字段门、既有backend收据范围与5项入口。每个测试进程 AS512MiB、CPU30秒、单CPU；audit 拒绝 native、网络及数值库。未调用生产 run/main 或原 run_phase，不把函数级 mock 说成端到端执行模拟。

公开测试可用明确 `--source`、`--entry`、`--repo` 参数搬迁；示例从候选根运行：

```text
python3 -I -S -B tests/supervision_micro/test_supervision_cold.py --source ABS/public/supervision.py --mode normal
python3 -I -S -B tests/caller_micro/test_caller_cold.py --source ABS/public/run_owner_micro.py --entry ABS/public/launch.py --repo ABS_REPO --mode normal
```

优化模式在解释器参数增加 `-O`，mode 改 optimized；搬迁复制已固定源和测试后使用显式绝对路径。具体8次原结果/日志身份保存在本地冻结清单，公开 COLD_RESULT.json 只投影安全统计和身份。
