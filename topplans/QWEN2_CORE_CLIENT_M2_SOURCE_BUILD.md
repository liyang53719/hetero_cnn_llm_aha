# Qwen2 Core：M2 source + single-TU build

- **已通过：**固定M2 harness/oracle/checker源码合成资格；单TU实际编译链接及静态16产物闭包。
- **未由本次证明：**M2行为/脚本数值、M3、跨16-key边界、完整Matrix FMA/128RTL/full29/90%MAC。960/288/828表只是静态编入，非执行事件。
- 保留父Python既有.pyc未pin覆盖限制；不是反向篡改/编译FAIL，旧证据不回填。原M1及所有历史FAIL/STOP/canonical状态不变。

[源码、可逆差异、复现和精确限制](../candidates/qwen2_core_client_m2_build/README_ZH.md)
