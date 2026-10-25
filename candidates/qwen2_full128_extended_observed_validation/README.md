# 原模型完整 M128：独立扩时验证（观测域与完整协议 PASS）

原始运行 `extended_m128_01` 已正常 EXITED/0，保存回执为 `PASS_OBSERVED_DOMAIN_M128_DUT_NOT_FULL29`。独立逐值/完整事件流审核及独立 metadata/runtime/cleanup 审核已完成，精确原件 hash 与安全投影见 evidence。本目录是源码与必要摘要证据包；公开包自身的 hash/CI 不替代实际运行身份或数值证据。

## 运行与范围

- 本次真正完整 128-token、原公开 21 命令的软件计算已到终态，未缩小几何、未以 M2 或逐 token 替代；不是 helper 模型。软件程序内部 token 循环不是将多次短运行拼作完整 block。
- 相对原 0941 冻结，只将 CPU 3600→9000 秒、wall 4200→10800 秒与版本身份显式变更；原硬件资源、输入、数学、顺序、容差及其他预算不变。旧 3600 秒 CPU FAIL 和 startup argv FAIL 均保留，不重标为成功。
- 经独立复核，21 个 public completions、17 个真实 owner jobs、1 个 launch result；worker CPU 5960.80416 秒（reaped user+system）、worker wall 5961.600773993006 秒、2,478,339 完整事件；这些是软件/监督资源，不是硬件周期、模型加速或利用率。采样 RSS 高水位 550,350,848 bytes 不等于连续完整进程树峰值。
- `y` 原 max/mean 双门独立复算 0.03125 / 7.282360456883907e-06，原阈值 0.05 / 0.01 保持。所有实际观测域的精确范围和指标见终态比较投影，**不能称全部 bitexact**。
- scores/prob/softmax 只比较 99,072 因果元素，各 97,536 future 元素未观测；不填零补成通过。softmax FP32 仍为无批准比较容差的诊断，row-sum 单独原门报告 7.248891051858664e-07 ≤ 2e-05。
- mask / repeat_k / repeat_v / logits 物理未物化，不存在其独立数值通过。协议证据不等于四个完整数值张量。因此 full29=false，硬件/RTL=false，90% MAC 利用率=false；父任务、其余四 block 和历史所有 FAIL/TEMP 保持原状态。
- RoPE 旧 comparator 的 256 是历史 project-reference 注记，不是当前 DUT table capacity。实际原 provider capacity 1024、active/generated positions 0–127，官方 max_position_embeddings=32768；仅披露原配置差异，不改官方配置或归因为隔离因果。

## 源码、pins 与隐私

`assemble_sources.py` 只校验并复制 16 个原字节候选/observer 源码与元数据，不导入 target：一个新 runner 原字节文件，加 15 个已公开引用。`EXTENDED_LOGICAL_FILES_DELTA.json` 以已有 2206-pin 元数据和 39 个新增角色记录重建本次 2221-pin 顺序；它不是私有可执行配置。

gate 的两个版本/时间变化由原文件 hash 与精确允许字面量替换记录限定；含私有解释器定位的 admission 等部署文件不公开、不改写冒充原件。私有 rope SOURCE_PINS 只保留 hash 与已有安全投影引用。公开源码组装不包含完整私有 runtime、输入、权重、任何张量/原始事件或执行授权，也不保证离线数值复现环境齐备。

原始输入、权重、local.npz、remote.npz、可重构权重编码、raw outputs/fields/events、私有路径/进程身份/配置/claim/approval 内容均不上传。这里只保存必要 hash、角色化来源、资源和数值摘要。组装 utility 测试不算 DUT/reference/native 验收。

## 独立复核及不可扩大范围

- metadata 审核 6,315 项：2,221 source/input/runtime pins 共455,168,677 bytes、141 artifacts 共330,635,481 bytes，原139-entry pre-parent inventory＋receipt/seal闭合。输入仅不透明hash；真实运行旧文件未改。pre/post hash 与cleanup在worker-wall预算之外。
- 独立 stdlib 流解析只读一次237,446,391-byte原流，核完2,478,339 frames及footer/EOF、6,912 QK2和12,288 PV0组、所有128×12头的完整调度；无债务、abort或残留lease。这里只公开计数/hash，不公开事件。
- 独立逐值checker读取23实际终态载荷、全部10字段4,723,200物理cells（2,577,408 observed）、25个不变官方reference载荷，复现全部原count/max/mean。24个具有批准阈值的BF16域通过；softmax FP32诊断与4非物化节点单列，不捏造29个全域通过。52,448,739为checker逐条件计数，不是独立测试case数量。
- prob/softmax_fp32各因果cell发生8次、7次相同重复；其他已观测字段频次1。所有future-cell presence/frequency为0且固定sentinel未变。Gate/Up为真实resident tile审计值而非DDR写回；scores/prob为被动因果观察；KV=K拼V、PV与ACKed Attention输出逐值对应。
- 冷载入原始module审计的namespace/dependency例外和早期registry TEMP/missing-source历史标记均保留；后置源资格/实际比较另列，不覆盖原记录。mask cleaned记录中的role_masks是预期安装契约；实际零local/global和释放lease由精确源码谓词验证，CPython callback getter不可用。oracle SEALED→post-terminal compare→CLOSED由源码/实际终态/前后policy支持，不是kernel sandbox或完整successful-open syscall日志。
- 没有fresh full128 off/original/identity对照，**observer noninterference仍未证明**；没有新的reference代码执行，只有留存官方payload只读比较。扩时完成不证明观察优化加速，helper未采用，Scala/RTL未新增验收。

## 本已过软件case的 MAC 账（不是90%利用率）

实际owner useful=6,014,828,544，native FMA calls=6,621,757,440；两者之比90.83432304038005%的分母是软件实际FMA调用，不是物理4096 MAC×完整block时钟。Dense/normal accepted steps=1,462,272/847,872；以4096×2,310,144 accepted slots为分母得到69.98005319148937%，也排除了空闲与时间，**同样不是利用率或占空比**。实际非重叠17阶段、源算法crosscheck和缺失证据见CASE_MAC_ACCOUNTING_PROJECTION。

完整硬件cycles、MAC active/busy timeline与验证后的物理容量均缺失；host-model ticks、软件service edges、CPU/wall不作替代。硬件有效MAC周期利用率和active duty均unknown，90%目标未通过。
