# Hosted tiny consumer 固定案例实测证据

本目录保存 run `38991969943` / job `117276108074` 在提交
`4538a108904789de619a7a3bdb0b741fb8fc28c0` 上的实际输出。
结论仅为 **PASS_FIXED_ACTUAL_CASES**。这次保全不启动新的运行。

- Profile 2 原始套件包含 QK、PV、PV128 边界，以及原套件的 legacy 和非有限值案例。
- 原始 Scalar 测试 7 项；SiLU 成功向量 2 个、故障向量 3 个。
- producer、public M16、完整 M128、RTL、90% 和 selected fault timing 资格均为 false。
  PV128 边界测试通过不代表完整 M128 模型通过。

三份 JSON 原始文件合计 57,230 字节，按字节完整复制，没有删减或重写。
`frozen_contract.py` 和 `frozen_input_contract.json` 也是已冻结版本的完整副本。
`source_hashes.json` 必须与冻结契约的 114 个输入源、5 个 payload 源及 2 个生成目标完全一致。
实际导入的 Python 模块路径及 SHA256 由原 `contract.py` 验证器逐项核对。

三阶段记录的主机为 GitHub hosted Ubuntu 24 / x86-64，具有 AVX2，未见 AVX512 或 AMX。
Python 3.12.15，NumPy 2.3.5，GCC 13.3.0；新构建 ELF 的 SHA256 为
`d059c8d9bc04d964b15790fdcfc411f23303dd25b0e6294ff38b688f1cd86624`。
这是该次实测的身份记录，不表示其他主机或 producer 环境已合格。

artifact `12084699511` 的 ZIP SHA256 为
`11269eb83d8bd34ccca1584e36bbf38f81cd37370fcc24d8428962929b482b75`。
保全过程独立核对了 ZIP 哈希、恰好三项成员及其原始字节。
远端 run/job 成功状态由协调任务核实；离线验证只证明本地证据的一致性，不重新认证远端执行。
归档不包含 ZIP、ELF、权重、张量、NPZ 或运行日志。

在本目录执行以下命令即可进行纯元数据验证：

```sh
python -I -B verify_checkpoint.py
python -I -B test_checkpoint.py
python -O -I -B test_checkpoint.py
```

测试覆盖原始字节绑定、篡改 manifest 后的拒绝、严格 JSON、额外文件和符号链接、
固定案例/计数、来源闭包、实际模块与 ELF 身份、主机能力以及扩大资格声明等负例。
验证器只使用 Python 标准库，拒绝 native 导入、进程启动和网络访问。
`MANIFEST.json` 记录本目录 payload 的大小及 SHA256；发布映射在归档外单独提供。
