# Qwen3.5 状态搬运：Treadle 测试源码准备状态

状态：仅源码审查，尚未编译、展开或执行这个测试，没有 Treadle 测试 PASS。

本摘录包含一个原字节 Scala 测试及原设计说明。它直接实例化既有 GdnChunkStateTransferOwner，并显式选择 Treadle；不是 Python FSM 替身。生产 owner 与公共 M1、recurrent、Host 双根发布门均未修改。

源码预期只覆盖一个 cold M16 / head0 Initialize 命令：1,024 次对齐 64 B 零写及匹配 ACK，总计 65,536 B。请求背压预期 2,047 周期，响应 valid/ready-low 256 周期，延迟 ACK 2,304 周期；预期 active 6,399 周期、测试显式 step 6,412 次，上限 20,000 次。256 个响应背压周期已包含在请求接受周期中，不能重复相加。最后全部十个结果字段需保持八周期，并阻挡第二个 job offer。这些数字只是按源码独立推导，不是实测。框架自己的初始化不计入显式 step，未来仍须单独有界监督。

MemoryResponse 实际只有 data / tag / error，不含 nbytes 或方向。测试由已验证的固定 64 B outstanding 写请求核算字节，并不虚构响应长度检查。受控 ACK 端点不是 DDR 或真实物理总线。

依赖选择为 106 个 JAR：81 个既有只读引用，加 25 个缺件，共 19,329,566 B。缺件 URL、字节数和 SHA-256 与原锁一致；六个旧版本仅从新选择中排除，原 87 文件未修改或删除。本次没有重新哈希既有 JAR 内容，也未加载它们。

当前环境允许的出站域不包含官方 Maven 主机 repo.maven.apache.org。没有发出网络请求，没有已观测的 HTTP、DNS 或 TLS 失败，也没有下载、代理、镜像或连接器绕行。本包仅保存锁定的依赖元数据，不含下载器或执行入口。依赖路径获准并补齐之后，仍需冻结并核查独立 runner、全部运行依赖及资源边界；计划完整不代表可以执行或已经通过。

不授予 warm/export/fault、M128、浮点算术、完整 chunk/GDN、Host 发布、RTL 仿真、性能或利用率资格。既有 Scala 编译与 CHIRRTL 前端结果不自动成为本测试的握手资格；旧 Qwen2 执行/清理 UNKNOWN 不改变，五项 RTL 验收仍为 0/5。

文件边界：四个原文件逐字保留；SOURCE_PINS 只给逻辑名称及精确哈希。没有私有机器路径、原 INPUT_PINS/下载计划、日志、ADMISSION、JAR、class、IR、权重或数组。本摘录不是独立可运行闭包。
