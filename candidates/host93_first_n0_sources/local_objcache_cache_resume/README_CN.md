# 本地 OBJCACHE 文本门与原473缓存续接 SOURCE

本片针对上一独立执行在 fresh_autoconf 后的父后验拒绝。旧输出保持只读；其四个自然退出 0、cleanup 已确认的阶段不冒充此次新运行结果。

## 有限修复

原 gate 只接受 `else $as_nop`。固定官方 Autoconf 2.72 生成的是 `else case e in #(`、固定 `e)` 分支与 `;; esac` 收尾。新增逻辑只识别固定 688 字节完整 OBJCACHE block，SHA256 为 f735474b483bdc4f30f18a57d97f3d0c527d692e6434f388dc2bf3befa777722。只在内存将此完整 block 精确投影回原形态，逆变换必须逐字节相等，再调用原 objcache_configure_witness；返回的 branch size/hash 指向原实际 688 字节，绝不误报投影后的 hash。旧形态仍由原函数检查。

语义证明是有限文本分支证明：原干净环境显式提供 ac_cv_prog_OBJCACHE='' 与 OBJCACHE=''，原 `${ac_cv_prog_OBJCACHE+y}` 为 y，test 命中 then，cached printf 完全相同；两种 else 体均不执行。相同的 OBJCACHE=$ac_cv_prog_OBJCACHE 赋空，后续原非空 version guard 继续由原 witness 强制检查。configure.ac 原固定 SHA、配置前空环境门、配置后四模板空赋值门和 make OBJCACHE= 均未改。未知/漂移模式继续拒绝，不运行 shell 来证明文本。

## 缓存与 fresh 输出

私有 source_cache 必须显式绑定原 acquisition 根。对固定 SOURCE.json size/SHA，以及固定 revision 的全部 473 个 Git blob、11,747,893 字节和原 mode，先用原 postflight 验证。新父 DATA_ONLY 阶段在原前置截止内最多 60 秒：原 copy_member 使用 checked_read 返回的同一 buffer 写入 fresh 0700/0600 树并 readback，再对新旧两树运行原 postflight。固定 receipt 从已验同一 buffer 写入；不复制 archive、派生树或任何对象，不借旧 acquisition cleanup 声称新 native 资格。

原 run 仅将 acquisition 段精确逆向投影为消费 fresh cache copy；原 receipt 判据、verify_official473、唯一 seqnum 补丁和全部后续代码保留。原 header 数据阶段、真实 header 编译与 autoconf 需在 fresh 路径再执行，绑定本次输出与后续配置。故本次为 2 个父数据阶段和 16 个 native 阶段；没有新网络获取阶段。

## 资源与失败信息

沿用唯一 t0+6600 总墙钟、前置 t0+2880、完整 3600 秒 N0 窗口和 120 秒落证。沿用单核、make -j1、原 AS/CPU/FSIZE 与四处 8 GiB RAM / 3 GiB disk 准入。原首错误优先、原 traceback 和清理证据保留。

RESULT 只增加 safe_contract_boundary 与 safe_contract_code：异常必须恰为当前固定原 ContractFailure，两个属性必须为 str 且都在原固定词表中。未知/伪造类型/未知属性为 null；不记录任意异常文本。

本片继承前 SOURCE v2 的 540 项冷测覆盖，不重跑并冒充新结果。本片定向冷测和只读已有 bytes 检查分别列于 COLD_RESULT。没有执行 native、下载、安装、构建、Host 或 N0。实际仅由父在本片完整独审后用显式 private binding/同 buffer launcher 执行一次。外层成功必须结合原 exit 与 RESULT 及原清理证据，不能单看先于 restore 保存的 RESULT。

公开只收源码、安全模板、定向冷测和有限合同。PRIVATE_BINDING、COMMAND、launcher、实际只读报告及原日志保持本地。
