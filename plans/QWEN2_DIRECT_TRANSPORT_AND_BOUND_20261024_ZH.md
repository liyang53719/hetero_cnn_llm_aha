# Qwen2 直通对应与固定资源上界：检查表

- [x] 固定当前main1bdf70e与五文件选定Scala postimage；不把历史快照叫作当前bare-main实现。
- [x] 查清producer/consumer均64B/16×FP32容器、地址单位byte，BF16在数值物化/Matrix入口；复用已有无损packing适配。
- [x] 查明raw-KV是额外缓存/银行借用寿命，非纯表示差异；直通模式复用既有Public driver，不增加payload/cache/资源。
- [x] 新opt-in每edge检查身份、Dense/prefix排空、scratch/raw-transport为空、真实写ACK及terminal顺序；突变测试必须在下一edge前拒绝。
- [x] 原始Banks固定16×1376×256、真实RawKvPort ACK/release往返与位模式测试；M2直通控制回归不是M128或完整block通过。
- [x] 整数回归给出M128逻辑K/V读1,585,152对raw-cache4096 miss，387倍；不能把缓存差异当硬件对应已通过。
- [x] 源码单issue端口与互斥证明：QK55,296 + PV792,576 + 理想Dense1,462,272 → C≥2,310,144；固定4096分母给条件架构上界30593/48128≈63.56590758%。无Python tick冒充cycle。
- [x] 更强mandatory QK Scalar必要界：99,072 scores×17 Add/Mul=1,684,224请求，首次accept至最后result至少5,052,671拍；固定4096完整block上界1468464/5052671≈29.0631232471%，与Matrix界取max，不相加、不继承旧SiLU/PV6预算。保留该fold/scale时，仅修PV6仍不能达标。
- [x] 独立复核源码hash/行号、公式及小批控制/组合；修复真实region reserved、提前参数绑定、同类型client错绑service等审查缺口。
- [ ] 本选定baseline无法达到80%/90%目标，不为此启动长M128/RTL。优先只读审计仓库已有packed/batched PV或多query控制/数据路径复用。
- [ ] 未来实际新模式必须另审profile/source/input freeze，复用真正fullblock M128入口；不得改旧验收门、继承旧27PASS或以M1循环冒充prefill。

最终本批74项normal /74项-O PASS，原已发布批76项normal /76项-O回归PASS；独审覆盖本批74项每模式。整体保持INCOMPLETE；本次只发布小型可选对应路径及可复核证据，默认模式、原源码、既有workflow gates和历史结果均不改。
