# 便携冷预算候选

本目录可add-only置于仓库任意候选目录；Python标准库即可，不导入NumPy/native/Chisel/EDA。不得把本片输出作为RTL测量。SOURCE_PINS.json没有作者机器绝对路径；每项只有logical root、相对路径与SHA256。

## 无源文件也可运行冷计数测试

在本目录运行：

    python -B -m unittest -v
    python -B -O -m unittest -v
    python -B budget.py

最后一条没有源验证，JSON的source_pins_verified_count必须为null。预算公式可独立复核，但不能据此声称已重建/验证源组合。

## 在消费者机器验证来源

先取得或按相关候选的组合脚本在新的隔离目录生成以下三套源。不要覆盖冻结源；不要只把main checkout当成已组合候选。

1. production_source：production_qkv_reduction_patch_v2的source根，含chisel/、candidates/。本包pin的是冻结组合源码，不是BASELINE_PINS里组合前输入。
2. candidate_tree：hetero候选树的candidates/qwen2_resident_matrix目录，含attention_packed_m128/、attention_packed_owner/、attention_scalar_schedule/、sfu_silu_cycle_candidate/、sfu_microsequence_audit/。
3. qk16_source：packed_qk16_owner_compile_plan的scala根，含chisel/。仅QK16，不是packedPV版本。

用消费者自己的路径显式传入：

    python -B budget.py \
      --production-source /path/to/composed-production-v2/source \
      --candidate-tree /path/to/repo/candidates/qwen2_resident_matrix \
      --qk16-source /path/to/composed-qk16/scala

三个参数必须同时出现；缺失任一源或hash不匹配即失败，不退回作者云目录。成功必须得到source_pins_verified_count=18。没有来源包/重建配方时，本片仍能冷测，但源重现状态应记为blocked；不能伪造替代源或换成最新main通过。

已补最终组合M128 schedule的只读文本快照及第18个bundle-local pin。原M1/M2 schedule不能直接接tiled.patch；现在组合收据包含原M16中间链的完整source/own pins，最终generated hash匹配。可选source-only冷重建（需要系统patch工具，不运行数值/RTL）：

    python -B recompose_schedule.py --candidate-repo-root /path/to/repo

它先验证全部原组合输入hash，再在新临时目录调用原prepare.compose，比较最终schedule hash后清理。最终schedule未被import或执行。

本包只内嵌5,218-byte最终schedule文本审计快照，不内嵌整个源树，也不宣称从任何未验证的远端commit自动获取源码。精确源字节身份由18 pins裁决；相应源候选的发布/获取由上层交付管理。

## 可发布内容

budget.py、test_budget.py、recompose_schedule.py、evidence_sources/、SOURCE_PINS.json、REPORT_CN.md、README_PORTABLE.md、BUDGET.json、cold_tests*.log、ARTIFACT_HASHES.json。BUDGET.json是作者隔离环境的源匹配与冷预算收据，迁移后需重跑校验；不是消费者本地验证证明。无输入tensor/权重/数值结果payload。
