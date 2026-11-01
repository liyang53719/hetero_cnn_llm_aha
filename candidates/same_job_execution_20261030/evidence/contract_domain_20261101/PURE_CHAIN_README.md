# 双来源合同纯数据链检查

实际材料来自已关闭的 1738 首次新候选执行，九前置阶段成功，P0 connect 因 builder/executor 合同路径域不同拒绝；DUT 未启动。

修复不重写外部 review 的 path/bytes/SHA，独立验证 executor 固定角色、canonical regular 文件和唯一 source catalog row。8 个轻测含内容漂移、角色/catalog/符号链接和未授权 adapter 拒绝。

本地 R3 使用真实 artifact/review、真实 20-stage 编译证据及 P0 inputs，实际调用 hydrate、corrector、assemble、load_binding、完整编译 proof、source_links、full spans 和 anti-oracle。无 verifier mock，无子进程/网络；Python audit hook 拒执行，AS 1 GiB / CPU 60 s。

**不是生产端到端准入。** 为只读保留原材料，三个 program bindings 指向原 views 对应的已核同字节文件；UNADMITTED bundle 位于两组文件的共同祖先。原生产 containment 门未修改，但此 fixture 不证明生产 material 根布局。未调用 liveowner/budget/ABI 新身份准入，不执行 ELF，不授数值 PASS。首次 R1/R2 两个 fixture 路径拒绝全部保留。

`reproduce_pure_chain.py --help` 接显式本地路径；--inspector 指原 offline_consumer_preflight/preflight.py 的真实 inspect 函数，--bundle 应为双方文件共同祖先中的全新 JSON。不可将该 JSON 用作可信执行输入。源 snapshot 的全部 catalog pins 在调用前逐字节核验。摘要记录 810-pin 测试 snapshot，不把后续加入此证据的 catalog 冒本次实测。
