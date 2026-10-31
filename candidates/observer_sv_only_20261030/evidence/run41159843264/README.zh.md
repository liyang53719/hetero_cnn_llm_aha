# 实际 SV 两模块限定差异证明（非数值回归）

实际 GitHub Actions run 41159843264 / source c312f2ee0a3ccbf23d898f0d8fe9142dedab8cd8 / launch b845ae540e073130b5565bb6f71b0f534f59bb72 成功。原 ZIP 3936B、SHA256 950e3b29ff109bbd1738782c07cda817ac4a4b6b89d67e2b9f476b10d0582a64，经下载后先核 digest、精确两 JSON 文件名与128KiB上限再解压。本包仅保存两原样安全 JSON、独审摘要及只读重审脚本，不含 ZIP、SV/IR/classes/log/ELF/权重。

15 阶段均 native0/errors0/strict cleanup、EOF、gzip 成功；old/new scanner 68.158/82.948 秒，projection52.739秒。原阶段180/300秒、whole10800秒均未扩展。

旧/新 whole normalized SHA 固定6555ede3…/ec70f911…，canonical固定90464ff4…/00897fd4…。两模块实际投影删除仅四字段61-bit端口/直接透传：Router8ports+4assign+12SourceInfo，Dense4ports+4assign+8SourceInfo；其余 normalized bytes 通过双流直接比较完全相同，分别179237B与44477654B。实例标签仅语法位置豁免引用检查，实例/注释本身未删除或改写。

同一 whole normalized身份连接既有完整92模块表：82不变，8个既定observer变化，另2个在本次严格投影证明；没有新增/删除/顺序变化。这不是整芯片一般等价证明，也不证明八observer的数值正确性。新raw9a8c64…与此前实际frontend run41118989254相同。

运行重审：`python audit.py --source-root /path/to/exact-c312-source --frontend-metadata /path/to/frontend-qualification.json`。脚本要求原676 pins闭包逐文件一致及原frontend文件SHA510fa27c…；只读校验本包JSON，不运行编译/硬件/仿真。若后续main改过闭包请使用固定c312源码，不静默继承新源。ZIP传输校验由本地原始审计执行；此脚本仅保留其固定已验摘要，不假装重新下载ZIP。

PASS 精确范围仅实际两模块61-bit观测透传规范化字节差异。生产门未由本包自动更新，full M128五块/最终RTL仍0/5；不得从此升级数值、利用率或最终RTL资格。
