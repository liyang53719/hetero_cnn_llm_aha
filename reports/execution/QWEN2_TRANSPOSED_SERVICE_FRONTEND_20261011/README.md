# 转置 Matrix service 前端证据

[SUMMARY.json](SUMMARY.json)只保存源码、生成物、日志身份及计数。完整纯源码和
复现入口见[候选说明](../../../candidates/qwen2_resident_matrix/transposed_route/README.md)。
实际编译基于 `590f8cf` 的原生产源码、固定return-tag补丁及新transposed补丁，
没有用未提交生产文件作为基线。

真实Scala编译/CHIRRTL展开：两条命令、20份IR、六组默认关闭严格结构等价。
最终发布检查器对原IR又做2,064,384个operand-pair坐标检查；包装版36测试及
两个baseline路径验证通过，但包装过程未重编Scala。两类执行身份在摘要分列。
新精确提交的CI另行编译验证；不能将本地历史结果改成该CI的成功。

该门没有执行SystemVerilog、Verilator、FPU或硬件时钟协议；未接真实bank读取、
M128 owner/Host及最终ACK链。原native/FP32-final FAIL和数值政策待决定保持。
Git不含权重、原始激活、IR载荷、ELF、jar或可重建编码数据。
