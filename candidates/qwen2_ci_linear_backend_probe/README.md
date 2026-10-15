# BF16 Linear 后端分支小探针

这是合成输入分支观察，不是完整 block、数值验收或利用率测试。一次 CI 总上限 12 分钟，固定官方 wheel 安装 7 分钟，两独立进程合计 2 分钟；每个子进程按 50 毫秒轮询检查 50 秒/128 KiB 日志阈值，允许轮询间超调，不是 OS 硬上限。仅自身 workflow 路径 push 或手动启动，run_attempt 必须为 1，不自动重试。

两进程均复用已审 AVX2 平台初始化，核固定 native 字节、版本、导入来源、4/1 线程及 deterministic。分别显式设置 mkldnn enabled/disabled，对固定非零合成输入调用一次原 nn.Linear：BF16、连续 1×128×1536、输出 1536、含 bias。不加载模型权重，不执行参考链。

详细 oneDNN verbose 仅在 CI 本地。公开输出仅固定 mode、execution、backend、ISA 枚举及 matched/count/evidence。没有匹配日志只能标 UNDETERMINED，不能证明 ATen fallback。没有输出 tensor、值、hash 或逐项元数据，没有上传 artifact。

固定 Torch 449b1768410104d3ed79d3bcfe4ba1d65c7f22c0 的 Linear.cpp 将连续 3D+bias 展平 addmm；CPUBlas.cpp BF16-output gemm 先尝试 oneDNN。固定 libtorch_cpu.so（原 native pin）机器码在 0x1e46c8b 调 mkldnn_bf16_gemm，失败后经 0x1e46cc3 get_call_ptr→0x1e46d25 调 gemm_stub，没有 sbgemm 中间分支。这是静态编译路径证据，与本探针执行观察分开。

来源：
- https://github.com/pytorch/pytorch/blob/449b1768410104d3ed79d3bcfe4ba1d65c7f22c0/aten/src/ATen/native/CPUBlas.cpp#L315-L372
- https://github.com/pytorch/pytorch/blob/449b1768410104d3ed79d3bcfe4ba1d65c7f22c0/aten/src/ATen/native/Linear.cpp#L49-L119
- https://github.com/intel/ideep/blob/719d8e6cd7f7a0e01b155657526d693acf97c2b3/include/ideep/abstract_types.hpp#L81-L87

ATEN_CPU_CAPABILITY 只限定 ATen dispatch；mkldnn disabled 是新的显式候选设置，不追认旧契约。即使分支观察符合预期，仍须独立原29参考比较，不能直接修改旧期待或启动 DUT。

冷测试：python -B -m unittest candidates.qwen2_ci_linear_backend_probe.test_parser candidates.qwen2_ci_linear_backend_probe.test_worker candidates.qwen2_ci_linear_backend_probe.test_runner -q；再用 -O 重复。
