# PC1 qraw 两轨参考 SOURCE 候选

本目录只实现SOURCE及小规模合成数值/纯mock测试。C++尚未编译或执行，完整196608值尚未计算；数学/typed差异、实际时间、native运行资格均待审后实际。无RTL、Host、Torch、NumPy或官方参考重生成。official_raw_numeric_pass始终为null，不继承旧N0或27-stage qr的数值PASS。

## 固定输入与输出

PC1仅计算M128×K1536的n0与K1536×N1536的input-major wq，不加bias、不作BF16输出舍入。独立historical n0为786432 B/SHA256 3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f；wq为4718592 B/SHA256 ad7ce2dae58deb01656348a6ee2bd6919ed6c2bc83f31b88eed75381cd718b72。同次已验收RAM的actual_n0只作相同字节门，绝不成为模型输入，也不冒充恢复旧RAM连续执行。

prepare_reference.prepare的显式参数为repo、source_dir、independent_n0、accepted_n0、wq、destination。路径仅由私有调用配置给入；固定size/SHA后同buffer进入独立fresh输入快照，原件/源码后检。调用者仍须绑定既有N0验收收据，参数本身不证明该收据或RTL继续资格。原参考、PASS与生产源码不修改。公共文件无本机路径。

## 数学轨：精确实数累加，独立于DUT顺序

每个有限BF16为signed significand×2^e，significand≤255且−133≤e≤120。每个乘积是2^-266的整数倍，其整数幅值少于2^522；1536项总幅值少于2^533。分开正/负累加，各9个uint64 limb，最后相减，抵消没有损失。单输出误差与196608个绝对误差之和保守小于2^552；576bit容量足够。每次加法显式传播carry并检查溢出，不截短、不借FP64累加。数学遍历按k递增，完全不复制DUT partial或pair顺序。

exact_math.hpp从精确整数直接进行FP32和FP64最近偶数舍入，支持次正规、负数、负下溢零、舍入进位与FP32 overflow到infinity。精确实数零定义为+0；数学输入的有符号零不改变实数值。完整任务遇到非有限数学FP32投影或typed输出拒绝完成，不静默给finite数。C++小测覆盖正负overflow、正负零、次正规half-tie、正常值、宽累加/cancellation；Python小oracle独立使用Fraction和整数RNE核验边界，overflow明确拒绝。

输出qraw.math.f32le是精确实数结果的一次正确FP32舍入；qraw.math.f64le是同一实数的一次正确FP64舍入，误差最多0.5FP64 ULP。它们是自建数学oracle，不是原官方入口已冻结的无bias张量。

## typed轨：实现匹配模型

原dot16.inc逐字复制，固定[0,1024)、[1024,1536)各从FP32 +0开始，每个pair高k先低k、每项std::fma融合舍入，最后second+first单独FP32加法。源对应见SOURCE_CORRESPONDENCE.json，覆盖router范围、k读取XOR1、slot隔离、HardFloat单次FMA/RN-even与binaryAdd。不凭函数名宣称DUT匹配；当前仍是固定源码模型，尚无PC1真实RTL比较。

原DUT add的端口名称是slot0 lhs与slot1 rhs，recipe写second+first；在本有限RN-even域二元加法交换操作数结果相同，包括有符号零。没有利用重结合，也不把模型顺序冒称动态观测。运行要求FE_TONEAREST和FTZ/DAZ关闭。此约束对应固定HardFloat源码，不声称通用VDPBF16PS/oneDNN raw等价。

## 微反例与误差合同

MICROEXAMPLES.json列明：一般FP32融合与分离乘加产生−2^-46/0；合法BF16在gradual-underflow域的融合/分离结果为2/1个FP32次正规ULP；两partial/单partial为1/0；pair高先低/低先高为1/0；qraw=257/256与加bias、最终BF16舍入可区分。正常BF16×BF16乘积若可由FP32精确表示，不能谎称单独乘法必然产生融合差异。

完整任务必须先计算全部196608输出。报告bit-equal数量、七桶ULP分布与最大值、最大/总绝对误差的精确2^-266整数(hex)、近似均值、非零数学参考处相对误差向外包围区间、零参考计数和非有限拒绝。最大/平均绝对误差不是N0容差的继承；无任何由DUT qraw调宽的阈值。

额外解析诊断界预冻结为gamma1537×sum|a*b| + 1537×2^-150/(1−1537×2^-24)，gamma1537=1537×2^-24/(1−1537×2^-24)。1536次FMA加一次最终add、逐次RNE和gradual underflow、没有overflow时，这是保守前向绝对误差界。sum|a*b|精确计算，界的FP64运算逐步nextafter向外，最后把界转回精确整数与误差比较。该界不是应用容差；application_accuracy_pass保留null。只有以后的RTL逐位比较才能填写typed_recipe_bit_exact_to_rtl，当前为null。

## 测试与执行边界

运行test_reference_cold.py使用Python -I -S -B，普通和-O；测试通过固定size/SHA后的同buffer加载prepare与oracle，覆盖29组算术/来源/搬迁/拒绝路径。audit hook禁止进程、网络、ctypes、Torch和NumPy。所有输入均合成，无真实数组读取。SOURCE_PIN中原件只读验hash，C++编译能力不由cold推断。

EXECUTION_CONTRACT.json冻结后继三阶段argv和资源：compile、native micro、完整两模型，唯一shared210秒，单CPU/512MiB；完整phase总120秒、工作105秒/CPU100秒，超时INCOMPLETE，不自动扩大。必须复用原ci_support_v3监督器，固定真实g++及本次依赖、clean env和工具搜索，保留首错、WNOWAIT/reap、进程组清理、RSS和后检。当前执行依赖清单/调用入口与SOURCE独审未完成，不直接运行本目录C++。完整输出只在私有fresh目录，完成收据最后写入；数组不上传。PC1长RTL另审。

## 独立SOURCE审身份

核心固定SOURCE已通过ACCEPT_PC1_TWO_REFERENCE_MODELS_SOURCE_ONLY。独审review_pc1_reference_core_20261019T1844：MANIFEST 550 B / SHA256 161b9e043efcbcc89ec4c85ccf637559c62e0315578c417356752ffafdb7cdd2；SUMMARY 3927 B / SHA256 a880263eae21d76de8293d7d084238f9ba7675f0e22189e101a8e1d2e2d09a0d。作者四套各29组、独审普通/-O各29组通过；25来源成员与21原件核验。当前仍TEMP_SOURCE/NOT_EXECUTED，完整模型数值与native编译未发生。独立执行入口、固定编译依赖及精确命令尚需另审，不以本节授予实际或长RTL资格。冻结COLD不改。
