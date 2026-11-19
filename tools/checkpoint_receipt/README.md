# 检查点收据校验

- done：独立收据完整性校验器及合成测试。这里只验证文件完整性，不是数值、退休、RTL、资源或五块完整 prefill 的通过证据。
- todo：调用端在恢复前为相应执行器指定完整的必需文件和执行身份集合，并另行检查低相、状态和退休观测等运行语义。

`verify(receipt, workspace, required_files=..., required_identity=...)` 验证 JSON 固定结构和所列文件的 SHA-256。路径相对于工作区，检查点文件名只能是单一组件；拒绝不在工作区内的路径和符号链接。需要 Python 3.11+。

只接受可信来源的收据；SHA-256 完整性不等于认证，也不能证明清单完整。调用端必须独占并保持写入锁，从检查前直至使用完毕；路径检查、打开和后续使用之间存在 TOCTOU 竞态，不适用于非可信并发目录。

```sh
python -B tools/checkpoint_receipt/test_receipt_verify.py
python -OB tools/checkpoint_receipt/test_receipt_verify.py
```
