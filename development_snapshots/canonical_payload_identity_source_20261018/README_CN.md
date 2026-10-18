# M128 原始输入身份恢复 v1

仅冻结已发布来源和 14 个 readonly provider 的预期身份，供下一 loader 审核使用。没有原始 tensor、生成数值、旧 framing、reference payload 或新运行收据。

## 使用

在本包目录运行，REPO 为调用者选择的已发布源码仓库：

    python3 -I -S -B verify_identity.py --repo REPO
    python3 -I -S -B test_identity.py --repo REPO
    python3 -I -S -B -O test_identity.py --repo REPO

校验脚本只读取本包身份 JSON 和仓库的 7 个固定相对路径。一次读取源 bytes，核对长度、SHA256 和重算的 Git blob ID，然后仅解析同一缓冲中的 JSON；不导入项目 producer，不调用 Git、编译器、网络、NumPy 或 Torch，不写入任何文件。测试只在临时目录建立小型源码副本，覆盖坏源、错误 provider/尺寸/集合、JSON 重复键、路径和 symlink 拒绝。

## 冻结内容

INPUT_IDENTITY.json 固定来源 commit b8ca25fa71e5b68cddbf0dd8eabf3dc787688f65、tree 570f2e6724ae71445d78ab00b17bd5da5f31f4b9，以及每个项目相对路径的 bytes、Git blob 和 SHA256。校验器验证所列文件实际字节，不证明调用者当前分支或整个 Git tree。固定 hash 是身份约束，不是签名。

- config/payload_pins/qwen2_layer0.json：13 份原始 BF16 tensor 的名称、shape、长度与 SHA256。完整 range/分段身份保留在该固定来源中。
- config/upstream/weight_headers/qwen2_1p5b/manifest.json：固定官方模型与 revision 来源。
- ffn_public/fullgraph_numerical_receipt.json 的唯一 rows=128 case：14 个历史实际 provider 的预期 SHA256 和大小。
- canonical_host_metadata_source_20261018/EXPECTED_LAYOUT.json：14 readonly 名称/尺寸/地址/shape/dtype 及两张表，逐项与 receipt 交叉核对。
- 3 个既有 Python producer/载入源仅核字节身份，不导入或执行。

模型为 Qwen/Qwen2-1.5B-Instruct，revision ba1cf1846d7df0a0591d6c00649f57e798519da8，layer 0，rows 128，epoch 7，relocate 0。provider 总字节为 94,916,608；commands 384 和 descriptors 3456 合计后为 94,920,448。

## 重建边界

真实输入转换规则保留在 check_prefix_numeric.py:324–366 和 check_fullgraph_numeric.py:97–103：7 个 BF16 矩阵转置；5 个 norm/bias 向量和 embedding rows 0–127 扩为 FP32；rope 按既有 double libm→FP32 配方生成，shape [2,1024,64]，其余位置为零。此包不实现或执行转换。将来重建后仍必须逐项核对 provider SHA256，不能仅凭 recipe 相同接受。

恢复时 13 份原始 tensor 和 work/ 依赖未找到。旧 producer 的 input_spec 还依赖缺失的 recipe/saved-stage metadata，不能直接调用或填造文件使其通过。历史 reference/中间结果不属于此输入契约。此包的 SHA 记录是未来输入验收预期值，不是当前已验证的数值 bytes。

safetensors header 存在于已发布 Git blob ed550aa50e12f2579ae10d1849a5a6c4797d0008，38536 bytes，SHA256 124516afba769374e2b948e185dd3e9203e2412daaef3f2ccf7bdbaca0f88987；恢复时仅被 sparse checkout 排除。本包不复制或要求加载该 header。

本包没有定义 wire format，也不复用旧 framed-stream SHA/长度。新 loader 只能把这里的固定身份当作预期输入门；不能由此获得真实 payload 存在、原 framing 恢复、RAM 初始化、physical launch、actual/参考比较或完整 block RTL 通过资格。
