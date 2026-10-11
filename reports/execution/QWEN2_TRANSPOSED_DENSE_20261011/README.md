# Qwen2 cold prefill 转置映射模型证据

本次是原 v0 算术的存储/阵列映射等价检查。Qwen2-1.5B 第0层真实数据依次完成
cold M16、cold M128 全15个算术阶段，各663,552、5,308,416个FP32值逐位相同。
使用同一冻结 C++/ELF/arena，每例只执行一次；CPU耗时100.310、169.967秒。
没有生成RTL，也没有执行Chisel控制。原官方M128阶段门及FP32最终门仍为FAIL。

[SUMMARY.json](SUMMARY.json)保留执行源/工具/输入、30个阶段哈希和实测软件计数。
只有摘要进入Git，输入、权重、输出、ELF均留本地。详细布局、端口和复现入口见
[候选源码](../../../candidates/qwen2_transposed_dense/README.md)和
[中文方案](../../../doc/QWEN2_TRANSPOSED_DENSE_MODEL_20261011_CN.md)。

执行时的driver保留原路径身份；发布入口只是参数化输出和baseline位置，需单列
新入口的小测试以及生成C++与已执行C++逐字一致的检查。旧执行成功不自动授予
新driver的完整运行成功。保存的baseline只在执行完成后比较，未注入中间结果。

固定资源为4096 FMA、五个FP32 context和原A688/B80 KiB。新映射仍需要实际
bank/operand/output路由、端口仲裁、返回/错误/最终ACK生命周期实现。当前软件
计数不含完整硬件周期，hardware_cycles和hardware_mac_utilization保持null。

全图流量187,432,960B是19个owner的解析账本，不是iDMA实测。保留当前读写互斥
的64B/cycle理想服务时，完整MAC利用率乐观上界50.1415%，尚未计其他等待。
down的DDR-prefix备选只有解析流量150,863,872B，尚未执行，不计入本次通过项。
