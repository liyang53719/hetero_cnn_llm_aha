# DerivedAndPair R2：枚举绑定修复与编译限定结果

这是一份可公开源码摘录，不是完整可运行环境，也不是硬件功能验收。

## 修复与已验证范围

原版23个名字的 List 解构在真实 Scala 编译中报错，原失败保留。R2 仅改为一次 Enum(23)，按同一名字顺序取索引0至22。将新绑定块逆替换后，整个 owner 的 bytes/SHA 恰好等于原版。所有 FSM 转移、Memory/Scalar/Loan 请求与响应语句均不变。

15项纯 Python 小控通过，34个内容输入前后匹配；两条完整模拟轨迹及写入摘要与原模型相同。随后，26个完整 Scala 文件在原冻结工具链中真实编译成功，349个输入含身份 stamps 前后相同，产出142个 class，41个必要类均存在。两次资格分开；Python 模型服务共享数学实现，不能当独立数值 oracle。精确结果和资源限制见 SUMMARY.json。

编译成功表明这个最小绑定修复在本次固定工具链中消除了原编译错误，不证明 Scala 所有大于22项模式的普遍根因。原失败没有删除或改标。

## 文件及复现关系

- source/GdnChunkDerivedAndPairOwner.scala、owner.patch、ENUM_REBINDING.json 和两份 Python runner 均为冻结原字节。
- tests.py.patch 仅记录原测试组增加的绑定/逆SHA断言，不重复发布原模型。其前后哈希在 REPRODUCTION_PINS.json。
- 原仓库 candidates/qwen35_chunk_derived 已有模型与测试；这里不覆盖、伪装或复制旧模型。
- REPRODUCTION_PINS.json 引用既有公开 LoadPrep 编译输入表的精确哈希，在原342输入上加入6个完整源码与R2源manifest，共349项；包含26源的编译次序和41个必要类名。
- 精确 nsc.Main 编译依赖仍是已有87 JAR/314工具，不下载新依赖。原完整文件闭包包括13 HardFloat 源、真实 Loan/MemoryEngine/TensorProgram 和 P0 类型；并非提取Bundle或stub。

原 launch_compile.py 入口使用 CPython 3.12.14 的 -I -S -B 模式，绑定本次私有 FROZEN_PLAN 的内容哈希。本摘录故意不附机器路径计划，不能直接运行 launcher、旧测试或重新生成授权。新环境复现须用相对依赖pins建立受审的完整路径绑定，而不是修改PINS绕过校验；本包没有自动 hydration 或下载器。

## 不包含、也不授予

没有工具二进制、JAR、class、IR、原日志、原收据、机器路径计划、权重、数组或权限载荷。只编译声明，没有调用 App、构造候选 Module、生成 CHIRRTL/SV 或执行真实ACK/Scalar/Loan。完整chunk、Host接线、硬件数值与RTL仍未由此证明。旧Qwen2执行/清理UNKNOWN与外部依赖缺口不因本包改变。
