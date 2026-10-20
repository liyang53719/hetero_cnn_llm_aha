# Owner Numerical 首坏只读闭包 v4

状态：SOURCE 待独审；v4 native/RTL 未执行。原 v3 源码及其 actual 均保留。

## 唯一生产差分

生产仍为原7件，仅 owner_micro.cpp 增加只读观察。另6件逐byte同v3，196端口、95控制观察、VLT不变。NUMERICAL_CONSUMPTION.json 单独明确新增69标量、4096个真正消费的FP32结果叶、16个tile响应值与6个原burst端口，共4187个叶；不能把原95控制字段声称成数值覆盖。

实际当前root已具备全部成员和正确位宽，不需改VLT/重生成。引用的packedQk命名是优化后共享消费alias，固定生成C++证明它来自Matrix结果FIFO的当前head，Dense finite直接使用同一4096叶；不是另一个QK运算结果的假定。

原Ram、Progress、全部驱动输入/握手/有限门不动。删除唯一观察块及明确插入的只读调用和JSON附加后，完整源码逐byte逆投影回v3。每轮仍2次低前eval、1次高eval、2次下降低settle，2次timeInc；没有额外状态推进。

## 三条 Numerical 写入

只在原LOW_PRE_EDGE、真实消费fire捕获：
- Matrix result：valid/ready、旧status、context/error/last、written/captured/terminalIssued、K/groupSequence/seed与矩阵状态；扫描4096项，保原savingPrefix/job.m掩码和BF16输出范围规则。单独统计指数255、有限FP32但BF16范围失败及masked计数。
- Burst source：实际fire、sourceFinite分类、error/tag/last/received、FP32/BF16/转换模式；扫描实际16word或32half，保FP32转BF16 RNE溢出门。
- Active drain：实际response fire、pending、responseError、真实selectedTile响应key、重算matching及16个响应值。error优先，与matching无关；selectedTile不是当前请求key。

每次消费只保计数、LE完整样本SHA、第一坏index/raw32（BF16源为raw16）、sign/exponent/类别和坐标；没有写数组/权重。每类只保第一问题，加当前低沿样本及第一次旧status0→高后status8对应的低沿样本。原raw-high95和settled95继续保留。

三个Numerical候选重算仅形成候选集合。相同edge还可能有后写Protocol/Memory/admission/reset，未采全部后写门，因此winner明确UNKNOWN_NOT_ALL_LATER_WRITES_SAMPLED。RTL finite/sourceFinite只作交叉核，不独立替代实际数据/协议门。辅助采样异常记observer_error并保持原退出路径；原首错和report双故障返回码不变。

## 边界与预算

输出仍原最多17条JSONL、每条32KiB预算及有界标量；没有新增记录。调用仍原两个固定N0/Wq路径、完整输入SHA和相同M128/K窗口。沿原caller复用owner archive及540秒窗口：compile120/link60/run300/tail60，单CPU、AS6GiB。本包没有launcher，也没有执行任何native。

静态诊断只能说旧owner实际status8=Numerical；失败result.context、值、原因仍缺直接数据观测。输入数学范围小于116是正确算法包络，不证明RTL实际数据正确；Host故障同因仍未知。official/application/typed-to-RTL资格不变。

## 冷测

同buffer固定生产7件和测试源码，普通/-O、原目录/搬迁四模式，每模式138个纯mock/source测试和8个loader正负例通过。新增覆盖4096完整alias顺序、首/中/末坏值、第二physical half、NaN/Inf/次正规、M16掩码反例、BF16有限范围、source转换、三候选优先级、无fire不消费、重复stall仅一次、原调度/退出/只读逆投影及有界输出。没有把Python表达式当作RTL复现。

诊断计划独审：review_owner_numerical_firstwrite_plan_20261020T0022，MANIFEST 411B/5d1fc6521d62f2b9df0fdbb133406c66340e4fcf7e165f1eef39bdcdc0bb5220，SUMMARY 4460B/38ed35b8cc048613ad27895bd4519b4ee789557b33c9736dd93cfbc77b138c93。v4生产独审身份待填。

## 正式 SOURCE 独审补记（替代上文待审状态）

review_owner_micro_core_v4_20261020T0031 已封 GO_OWNER_MICRO_V4_NUMERICAL_CONSUMPTION_OBSERVER_SOURCE_ONLY。MANIFEST.json：2326 B / 0a21394bd641a78cd6e07831873e199669f81bd9c2068115abab04db97f58984；SUMMARY.md：4320 B / 1eee1058e4e64039525f9364b9ea8ed5e158843612b0f32e36057d83c096d50a。

独审核对 44 成员、7 生产原件、原 17 来源、固定 root 的 4187 叶、实际 FIFO 消费 alias 及完整 v3 逆投影。独立搬迁普通/-O 分别通过 138+138 主例、8+8 loader 例；作者四模式结果单独保留。另有纯算术边界与坐标反算核对，均不计作 C++/RTL 执行。

本内容后继只补真实身份与有限 SOURCE 范围，生产/COLD 原字节不变。当前本批 actual=NOT_EXECUTED；同沿 winner 仍 UNKNOWN_NOT_ALL_LATER_WRITES_SAMPLED。现有数值失败、原 v3/Host 因果未知及 caller 的现物/资源资格不因 SOURCE GO 改变。
