# Qwen2 内部 owner 的 Host Command128 接入

基线：dfe80d57007bf6b11c53701ba6a9f238c5176975。本文件是开发计划，不是通过报告。

目标：取消新验收 root 对 block launch 自动15阶段执行的依赖。Host 从DDR提供原有21种次序的算子命令，硬件读取Command128和typed descriptor，绑定实际tensor地址后启动既有计算原语。共享一套原512-MAC和一套pinned iDMA；硬件修改只在Chisel，保留RTL不得手改。

先实现可独立启动的Norm、GEMM、Bias/Residual、RoPE、KV_APPEND、Activation owner。QK/Softmax/PV采用明确的三命令流式融合合同：逐条校验全部三条命令、descriptor、event和中间tensor唯一使用；只有最终PV成功写回后才发布三条成功completion，不能以新的opaque block opcode替代。虚拟score/probability tensor不得被后续独立命令读取，禁止将完整score矩阵落DDR。

验收包括：与原公共Python ISA parser互操作；取消/破坏任意命令不得自动推进；改变descriptor地址必须改变实际访存；读写错误和错误tag不得解锁消费者；tiny及真实尺寸16-token完整数值与旧基线对照；按所有实际tensor输出保存完整比较与源码哈希。完整原始GGUF字节兼容、整网q1024和DC仍单独验收。

本地agent只复核指定提交并执行固定脚本，不承担编码、修改阈值或修复失败。旧构建、日志、checkpoint和临时文件保留，新开发使用独立目录。
