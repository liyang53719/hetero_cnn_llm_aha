# Qwen2 原 AXI 格式桥：PASS 仅输入格式与映射小测

实际新增 adapt.py 将已校验 M128、21-command/215-descriptor JSON payload 转成原 HOST_COMPILED_INPUT_V2 与 AFFINE_BYTES_V1。FP32 bytes 原样 identity 映射，真实权重/输入逐文件复核 SHA。没有修改硬件、启动 Host/EDA 或调用独立 forward 参考。

原 C++ Config 与 loadViews/mmap 原实现测试 exit 0：16 readonly allocations、20逐 op观察；读取每个映射首尾并核 SHA。scratch 仅 rw 分配，不建数据 view。kv 只分配父区，cache_k/cache_v 是输出子视图；scores/probabilities 保持 virtual，不允许 DDR 输入。

RoPE 来自已 pin host_real_inputs.cpp 第123行：double角度、std::pow/cos/sin、float转换，theta=1000000，1024×64 cos 后接 sin。只抽取输入生成，不执行该历史 bench 的 forward/参考。当前 C++运行字节 SHA 为 9c59ecfe381ffd75e939cfda67423997454145376fff21991af06d98b8d06b7e；适配器强制该值，不接受同尺寸零文件。跨 libm 重建若 hash 不同需审计，不自动更新 pin。

小测含负例：零 RoPE 拒绝且不创建结果目录；篡改 views 内 source SHA 被原 C++ loader 拒绝；virtual 和参考没有映射；kv 不重复 allocation。临时负例文件由测试管理，仅删除测试自身可重建副本；未删输入、原证据或运行文件。

local_payload/host.tsv 与 views.tsv 可供当前 Host pin-only driver 使用，但本轮尚未验证当前 engine/顶层 schema 对接、AXI 周期握手、一次 launch、数值或完整 block。五块完整通过与利用率均不因本桥提升。metadata padding 来源于原 bin，不以参考补值。profileId=0/version=1/epoch=1 是 Qwen2 运行配置，后续 driver须核当前接口接受。

本目录二进制、rope.f32le、生成 TSV 为本地复现产物，不进入源码包。reproduce.sh 复用已存在真实 payload，且重新生成 RoPE、小测；它不触发 Host。

## 同冻结参考输入复核
额外只读逐字节比对 `round_20261110T0833/numpy_fma_candidate/cos.local.f32` 和 `sin.local.f32`：分别与桥 RoPE 前/后 262144 bytes 完全一致，各 65536 FP32 words 差异 0，覆盖完整 1024×64（不只 M128 前缀）。证据 `ROPE_IDENTITY_AUDIT.json`，没有修改参考或输入。此项只证明 RoPE 刺激身份一致，不扩大硬件或算子数值验证范围。
