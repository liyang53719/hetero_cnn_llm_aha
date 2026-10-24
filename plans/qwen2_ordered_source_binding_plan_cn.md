# 正常源码绑定补测计划及范围

1. 只读重验R2 assembled全316文件，保留原R1/R2与observer的历史终态。
2. 独立进程正常import五模块，允许原钉定Python/NumPy初始化自检，禁止任务级服务/native算术/用户tensor。
3. 固定七DUT方法及四buffer方法的真实文件与完整模块code，不使用ASTalias；源/方法/路径替换必须拒绝。
4. 精确运行时manifest、完整maps先保留再核device/inode/hash、异常立即FAIL。所有新尝试独立目录和限额。
5. 独审通过后仅升级normal-import/code binding范围，不升级正常runtime观测、真实数值、完整block、RTL或利用率。

详见 [候选说明](../candidates/qwen2_ordered_source_binding/README.md)。本片已暴露并保留stdlib源码缺pin、locale映射差额和site自动模块问题；没有修改旧pins以伪造旧PASS。
