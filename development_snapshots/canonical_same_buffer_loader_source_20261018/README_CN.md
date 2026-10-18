# Same-buffer loader 纯源码包

本包包含四个 C++ 源文件、独立 portable runner、mock cold、相对源码 pins 和安全数值摘要。没有 ELF、用户 tensor、当前机器编译器路径或二进制 SHA 库存、完整运行日志或生成数据。未来执行仍动态记录实际选择的 compiler bytes/SHA/版本，未削弱审计。

## 已实测的有限结果

完全相同的四个 C++ 输入在 GCC 14.2.0、C++17、-O0 下完成一次有界单 TU 编译与执行：编译/运行 exit 0；421 次 check() 检查通过，包含循环及 helper 检查，绝不是 421 个独立 case。compile 阶段墙钟 1.393817 秒，run 0.127493 秒；这些只是单次阶段耗时，不是性能 benchmark。三个已启动 stage 的进程组收尾均确认。

合成 RAM 最大声明 payload 为 65,537 bytes，mask 等长；不是测得的进程峰值。标准 SHA 向量包含空、abc、100 万个 a（1000-byte 小块重复更新）。测试还覆盖 padding/64 KiB 边界、严格 EOF/短读/尾随/坏流、name/order/hash、元数据深拷贝、one-shot token、同 RAM span，以及 seal 前、token 兑换前和显式 reverify 的故障拒绝。

四 C++ 文件与成功运行的 build 输入逐字节一致；runner/cold 与相同行为门源码逐字节一致，仅包位置不同。本目录没有另行 native 重跑。源码里的 SOURCE ONLY/未编译注释保留原始准备时状态，以保持实测输入字节身份；最新执行事实以上述摘要为准。

## 接口与边界

调用者独立认证有序 ExpectedInput(name/base/bytes/SHA-256)，构造 SameBufferLoader 后被深拷贝。依次 load_next(name, istream&) 以最多 64 KiB 块写私有 RAM；精确长度后的 read(1) 必须 gcount=0、eofbit+failbit 且无 badbit。任何异常都会永久 poison；不清除状态，不从输入流取得可信 hash。EOF 异常 mask 会导致拒绝；使用标准、如实报告 EOF 的 stream，文件用 binary mode。

finish() 要求全部输入完成，seal coverage 后从同一 actual RAM 重算 SHA-256，才生成私有 token。take_ready(token) 再复核一次并一次性兑换只读 view。正常路径固定三次 payload hash：流、seal 后、兑换前。view.read 检查 range/coverage，无 SHA；view.reverify 是显式 O(全部声明 bytes) 完整性边界，不逐 AXI beat 重算。

单线程；loader 必须比 token、view 和所有返回指针活得久。无正常可写 RAM 别名，旧 const pointer 无法撤销；不防御同进程恶意 const_cast、数据竞争或对象销毁后使用。测试探针仅记录构造期两个 64B allocation；delete 在 free 前撤销 live，读取前验证两记录仍 live、非空且唯一，再按完整内容识别 payload/mask，不猜对象布局。未知 allocator 形态会安全失败。

canonical 16 输入身份尚未绑定。这只验证显式 trusted expected 对应的初始化 RAM，不是 canonical-ready、完整 HostMemory 或 launch-ready。没有旧 framing/hash 继承、生产 Host 接线、业务写入、resident DDR 权限、B retirement、SSA/prefix、PhysicalObserver、RTL 或 EDA 结论。

## 文件和复现

- initialization_ram.hpp：原 RAM primitive；sha256.hpp：真实标准算法；same_buffer_loader.hpp：私有加载与 readiness 包装
- test_same_buffer_loader.cpp：唯一合成测试 TU
- run_behavior.py：仅本目录四个 pinned 编译输入，验证后将同一 raw bytes 写入新 build
- test_runner_cold.py：mock-only 监督及 schema 测试，使用验证过的同一 Python bytes 执行 runner
- BUILD_INPUT_PINS.json / PROJECT_SOURCE_HASHES.json：真实相对路径与精确 bytes/SHA
- RUNNER_DELTA.json：六个原监督函数字节身份；BEHAVIOR_SUMMARY.json：脱敏数值摘要

本包可整体移动，不依赖旧 workspace 或审计目录。Linux waitid/WNOWAIT 是 runner 的明确要求；需要已有 C++17 编译器，不下载或安装。

纯 Python cold：

    python -I -S -B test_runner_cold.py
    python -I -S -B -O test_runner_cold.py

明确决定进行新一次 native 复现后，在本目录使用尚不存在的输出目录：

    python -I -S -B run_behavior.py --compiler c++ --output ./fresh-loader-results

version 墙钟/CPU 为 5/2 秒，compile 30/30 秒，run 10/5 秒；每 child AS 256 MiB、单文件 4 MiB、core 禁用；每 stage 清理共用最多 5 秒。三个 stage 配置墙钟及清理合计最多 60 秒，不含 Python/文件系统开销。每 stage 日志超过 65,536 bytes 判失败。WNOWAIT 保留 unreaped leader 身份，原进程组处理先于 reap；未知清理状态保持 FAIL，所有 receipt/log/build 保留。没有自动扩大预算或无限重试。

未来 RESULT 会包含执行机器的动态 compiler 身份与路径；发布时仅分享需要的数值摘要，勿直接公开整个结果目录。
