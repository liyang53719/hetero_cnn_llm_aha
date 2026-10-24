# 正常源码加载与 code 绑定资格补片

范围：`PASS_NORMAL_MODULE_LOAD_AND_CODE_BINDING_ONLY`。绑定已发布 observer 父提交 c8de5739b68e7cfc3489cbe677681a5af6009442；不修改其 AST 测试、TEMP 历史、源码或 pins。

## 本批实际做了什么

- 复用 R2 原 assembled source 的全部316个文件（4457398字节），启动前和结束前逐hash复核。
- 在独立 CPython 3.12 `-I -S -B` / `-I -S -B -O` 进程里正常 import AttentionOwner、ProductionQk16Schedule、OrderedFoldWork/Adapter、PackedClient 和原 PackedFields buffer。没有 AST definition alias，也没有绕过 prelude。
- 真实模块 __file__/方法 co_filename、七个 DUT 方法和四个 buffer 方法的完整模块编译 code object、行号/line table 匹配既有 observer 固定 SHA。没有创建 Observation/owner/service、接受 job 或运行调度。
- 额外10项纯配置门测试确保精确runtime路径/pins、observer/buffer/worker额外文件集合及manifest不能被放宽。四个绑定负例：错 digest、同字节错误路径、一字节源改变、替代方法，全部拒绝。原源文件未改，负例文件只在新输出目录。
- 运行时只读 allowlist 从首次发现用1586文件收缩到202个精确文件，最终报告检查181个具有文件身份的已加载模块与18个实际映射文件。18个是16 ELF + 2个 locale 数据文件，不能写成18 ELF。映射文本先保存，再校验 device/inode/文件hash；未知映射必须FAIL。
- 每子进程1 CPU、256MiB AS、20CPU秒、25wall秒。源/配置/日志身份、进程身份、退出和进程组清理均留记录。所有子进程显式 -B；-S 禁止 site 自动 .pth 扩展，不通过预加载隐藏依赖。

## 允许的依赖初始化，不是“完全无 native”

正常 import 传递链：attention_owner/schedule/client → prefix_arithmetic → ctypes + NumPy；matrix_service 也 import ctypes。

原钉定 ctypes/__init__.py L473 执行 PyDLL(None)。原钉定 NumPy/__init__.py 执行自身初始化、扩展/BLAS加载、float32 ones(2).dot 自检及20×20 ones 矩阵乘的 BLAS FPE 自检。它们保持原样，未删除、mock、alias 或预加载。这些微量依赖自身算术/数组属于明确允许的初始化范围。

禁止的是任务级 Matrix ELF 显式 CDLL、configure_library、服务/owner构造、reset、job、QK/Attention算术、用户tensor/参考读取、外部进程/编译。新审计门只允许 ctypes.dlopen(None)，不放行 Matrix ELF。该审计/指定入口拒绝器不是通用沙箱，也不能独立证明任意代码都不会执行算术；本结论同时依赖固定源码及顶层副作用审查。调用监控拒绝所钉任务源中的 __init__/configure_library/tick/run/op/_op/_matrix_step/td_reset 入口；只执行模块定义与绑定。

## 不能推导的结论

这是 normal import/code identity 的 PASS，不是正常 runtime 观察器执行的 PASS。未进入 Observation 上下文、未捕获实际 runtime 十字段、未验证新观察器对真实数值服务无干扰；此前 AST fixture 的26项不由此升级为真实服务行为。未运行新的 Matrix/Attention/native数值、完整block、M16/M128、RTL/elaboration。不能将本片耗时当硬件周期或利用率。

## 复现

必须已有 exact R2 assembled source、同hash CPython/NumPy runtime 和已发布 observer。MANIFEST.json 不含私有绝对路径，prepare_profile 按提供的根定位并逐hash验证。不能将未经组合的 main 当 selected assembled source；缺字节即拒绝，不下载/重编译、不改历史pins。

```sh
python3 -B candidates/qwen2_ordered_source_binding/prepare_profile.py \
 --source-root EXACT_R2_ASSEMBLED_SOURCE \
 --observer-root candidates/qwen2_ordered_observer \
 --buffer-source candidates/qwen2_resident_matrix/attention_packed_tiled_observation/capture.py \
 --numpy-root EXISTING_PINNED_NUMPY_ROOT \
 --output NEW_PRIVATE_CONFIG.json
python3 -B candidates/qwen2_ordered_source_binding/run_bounded.py \
 --config NEW_PRIVATE_CONFIG.json --output NEW_RESULT_DIR
# 可独立新目录测试优化模式，不能覆盖前次证据：
python3 -B candidates/qwen2_ordered_source_binding/run_bounded.py \
 --config NEW_PRIVATE_CONFIG.json --output NEW_OPT_RESULT_DIR --optimized
```

路径相关配置、负例临时源码、完整 maps/进程stat 本地保留，不上传用户tensor或原始私有路径。公开仅脱敏摘要、内容hash、源码与限额。后续若要资格化真正 source-loaded observer，仍需新的精确输入/运行配置/独审和单Attention授权，不可自动运行完整block。
