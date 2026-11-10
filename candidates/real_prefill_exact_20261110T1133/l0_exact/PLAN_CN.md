# L0真实M128上游数学参考审计（限定PASS；硬件INCOMPLETE）

## 实际覆盖
复核已有真实权重绑定及中间输出每个SHA，不换刺激、不重下载、不写硬件内存。输入仍既定caller synthetic dyadic hidden，不冒官方embedding。
- input RMS：128对sqrt/div，393344个mul、145536个add逐节点Fraction精确核验；保持原32lane分组/分块/折叠与normalize/gamma顺序。输出BF16全部匹配。
- QKV/Z/AB：1077936128个完整升K FMA，1052672个BF16输出全部匹配。有限BF16乘数/FP32acc下使用已审值等价+TwoSum精确残差flags，未用matmul。实际flags仅0/1。
- Conv4：四tap分别FP32 mul/add，BF16卷积边界，再原degree7 exp、denom/div/sign/activation、最终BF16；128token×6144channel输出786432及完整历史缓冲逐字一致。所有真实tap tiny-inexact共7084次单独Fraction精确RNE/flags全检。

## 原opcode与修正记录
GdnConv4Owner:13–15明确tap使用MulIeeeRne保留IEEE gradual underflow；GdnRuntimeConv4OwnerRecoveredV7:123–132实际tap选择MulIeeeRne，其他sign/activate默认Mul。首审计错误把所有mul统一fatal，session1013 exit1；已保留INVALID_UNIFORM_FATAL_RESULT/log，仅审计器错误，不是硬件失败。修复仅按既有opcode区分，未修改任何硬件/精度/fatal政策。正确session2915 exit0/12.52s；最终-O运行结果见RESULT。

允许tap UF的7084个操作（包括signed zero）全部精确核验，记录实际operand例。后续exp/activation独立mul/add未出现UF/OF；Div通过对所有真实唯一denominator的独立Fraction除法复核。历史chunk四head的fatal Mul仍原样拒绝，不因Conv允许MulIeeeRne而迁移政策。

## 数学方法与边界
FP32×FP32乘积至多48有效位，FP64精确容纳，单次FP32舍入给出原独立mul值/flags。FP32+FP32采用同指数差分支证明：d<=28时精确和至多53bits；d>=29时较小项不能跨越已精确FP32大项的RNE边界。TwoSum精确残差补inexact。仅当前有限数、RNE及保留次正规环境。前后fegetround==0；最小subnormal实测不被flush。
Exp所有单独mul/add仍审计；8个系数及LOG2E另用100位Decimal/Fraction复核。不是调用libm exp，不是把np.exp当原路径。

BF16物化采用既定RNE位操作并与全部保存结果一致，但不声称输入/输出格式转换异常flags资格。无Chisel/RTL执行，无周期/利用率测量，不外推RawPrep全部、chunk全部或后半FFN。本结果接续上轮冻结Conv/AB之后失败依赖锥，但完整L0依旧INCOMPLETE，原硬件head4 FAIL不变，五块硬件0/5。

重现：OPENBLAS_NUM_THREADS=1 timeout 600 python run.py（实际命令timeout 600）；内部CPU590s/AS2GiB。运行需要历史pin数据，不包含权重/数组。test_arithmetic.py普通/-O、test_coefficients.py及check_tap_underflows.py均有实际日志。所有原失败保留，不清理唯一证据。
