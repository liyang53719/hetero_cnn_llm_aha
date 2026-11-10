# TEMP：逐K NumPy BF16-input FMA候选与真实M128 Q参考

candidate.py不是替换精确Fraction：独立API，明确finite输入；FP32存储先同原Matrix入口BF16RNE。用两个显式numpy ufunc作FP64乘法、FP64加法，最后一次FP32 cast。每个输出按K=0..K-1迭代，不使用matmul/dot/einsum。SFU仍调用精确Python。

## 数学条件和待审范围
BF16有效位至多8，精确乘积至多16位，其非零范围约2^-266..2^256，FP64无乘法overflow/underflow。乘积与FP32累加数接近时，舍入所需的有效位和对齐范围可由FP64容纳。指数相差很大时，主项为可精确表示FP32的数，小项通常不影响FP32舍入；但需单独分析主项为未对齐的次正常乘积、临界半ULP、overflow midpoint和signedzero。此处是推导方向，不宣称穷举证明或全部硬件异常等价。依赖NumPy/CPU采用IEEE binary64/32 RNE并保留次正常数；有界测试覆盖当前环境。未设FTZ、未改安全配置、未用fastmath。

VERIFY.json：91557组0差异。覆盖全部255×255有限BF16 exponent对（每对随机mantissa/sign/c），定向±0、最小/最大次正常、最小normal、±1、最大BF16、FP32极值，10000组随机生成的精确消去及邻点。oracle用Fraction一次RNE，overflow结果位可比较但不表示硬件应接受overflow。随机种子0x20261110。3项Dense测试正常/-O通过，包含5×37×9逐K对精确参考、顺序反例、nonfinite拒绝。

## 真输入完整投影（不是切片）
先重核x/gamma0/wq真实payload全文件SHA与大小。精确Legacy RMS覆盖128×1536全部输入，用786944次scalar原语，4.391秒；然后候选Dense覆盖128×1536×1536，即301989888 MAC，0.451秒。四个坐标再次使用完整1536-term Fraction点积核对，0差异。输出norm0/q0仅保留本地二进制；交付只有pin/hash/摘要和复现脚本。

范围：仅独立软件参考的RMS+Q Dense，未bias、RoPE、其余block；未对Chisel/RTL比较；全block硬件0/5。不得写“Qwen2完整PASS”或“RTL PASS”。也未验证使用真实硬件时的最终吞吐与利用率。

## 可执行后续路线
继续保留逐K，允许完整21-op调度显式选择候选Dense，不默默覆盖精确实现；QK/PV也须逐lane/逐key更新且分别对Fraction资格。其余scalar保持精确有界执行。验证后可尝试128真实完整独立参考，不能以其结果替代原Chisel/同刺激RTL。

运行：先解包同轮legacy_python精确参考至../legacy_python，运行verify.py、test_dense.py；real_q_projection.py依赖本地既有FP32输入及绑定manifest。单次实际运行wall上限180秒，session69620正常exit0。不上传.local.f32，未push。

## 后续运行更新
用户授权后已用原Host输入配方当前平台冻结cos/sin；见TRIG_MANIFEST，绝不声称官方Torch或历史hash。freeze_trig.cpp仅生成输入表，不计算任何forward中间量。full_m128.py复用已核checkpoint，预算1800s CPU/wall和2GiB地址空间；CANDIDATE_REFERENCE各阶段落盘，Matrix状态/flags始终NOT_QUALIFIED。其full结果需读full_m128/RESULT.json，不从进程存在推断通过。
