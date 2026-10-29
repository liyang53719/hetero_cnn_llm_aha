# BUILD_ONLY 本地身份摘要（TEMP，future-only）

原 run40862676969 已成功27 native阶段、五段archive/link，但原summary只保留manifest hash，**未导出binary SHA，不能从旧摘要补出，也不代表产物可下载**。本修复仅面向未来已授权执行，绝不重写旧证据、不触发重建。

packer在既有所有复制/hash/完整build检查后，返回六项payload_identity，每项仅sha256+bytes：binary、sv、driver、source_manifest、tool_manifest、build_receipt。无路径或文件内容；总bytes+manifest bytes必须精确等于expanded bytes，保持原4GiB界和固定V3driver。summary仅导出严格六项/两字段/64hex/整数正大小，状态明确 EXPORTED_HASHES_ONLY_NOT_DOWNLOADABLE。旧结果缺字段记 NOT_EXPORTED_IN_ORIGINAL_RESULT；坏metadata不导出、标 INVALID_IDENTITY_METADATA_NOT_EXPORTED，不抹掉其他成功/失败阶段证据。

不修改七文件内容、硬件/driver/参考、工作流/upload/caps；仅本地结果和受控summary增加身份标识。不能据hash声称可取得binary、ABI兼容、5profile数值通过或90%达标。

测试：4项身份契约单位测试normal/-O；原3项packer synthetic fixture测试normal/-O（明确fake ELF，非编译/DUT）；首次调用packer测试遗漏必需--driver参数导致argparse拒绝，补实际已pin V3driver后通过，未改测试/生产安全条件。无编译/下载/CI。

独立发布审查补充：新增 test-only R2 修正实际 pipeline/materialization 分目录测试布局，并增加真实 build_summary 函数的缺字段、合法hash、恶意path metadata 三分支单位fixture，合计7项 normal/-O；保留completed/阶段证据。fixture没有执行真实编译或DUT。
