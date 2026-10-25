# 完整入口正常绑定：精确补闭 PyYAML 依赖

**终态：r2唯一正常cold通过15 roles＋9方法代码绑定；68项四模式测试通过。完整M16参考/数值/运行时无干扰仍TEMP，旧失败不改。**

父提交 `5e703311d62ab05ae7679d17d7ba101c1e201525` 保持原 TEMP 和 v2/v3 FAIL，不改历史 pins。新片只升级完整正常 source import 与九个服务方法的代码绑定资格。

最小实现为独立 yaml-only 依赖目录和适配器，完整保留已安装 PyYAML 6.0.3 的 17 个 Python 文件及 `_yaml` 扩展。逐 RECORD、源码、ELF、DT_NEEDED 和实际映射核验，不开放整个 site-packages，不删除 cyaml 或预加载绕过审计。

Cython 初始化产生的两个无独立源码模块采用窄结构/来源关联检查，精确绑定扩展事件、实际 ELF、当前对象和导出函数类型；原 module audit 不修改。该检查不声称观察了 C 内部 module creation 调用，也不放行未知模块。

只允许单独独审后的正常 cold：1 CPU、256 MiB、20 CPU 秒、25 wall 秒。允许原依赖初始化和已 pin 的只读 metadata，禁止任务服务/owner/Observation 构造、Matrix ELF、任务 job、用户 tensor、编译、完整 M16/M128 和 RTL。

最终结果与精确源码/配置身份见[候选说明](../candidates/qwen2_fullgraph_normal_binding/README.md)。即使正常绑定通过，完整 M16 独立参考仍未闭合，实际 observer 无干扰、完整29节点数值和硬件周期全部不升级。固定 4096 MAC 与 legacy PV 63.57% 完整 block 上界保留。
