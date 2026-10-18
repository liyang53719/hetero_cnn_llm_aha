# canonical16 固定输入绑定源码 v1

本包仅为 SOURCE-only 绑定候选。没有调用 factory、构造大 RAM、编译或运行 C++、下载权重、加载 canonical tensor 或参考 payload；不继承依赖包的 native 结果作为本绑定的运行结果。

## 最小接口

canonical16_binding.hpp 提供不可变的16项 POD 常量表，以及无参数 make_canonical16_loader()。factory 没有 caller expected、地址、长度、budget 或 SHA 覆盖参数；地址/长度均为 uint64_t 常量。内部只把固定表转换为既有 loader 所需 vector，并直接返回非可移动 loader 的 C++17 prvalue。该 factory 此次仅作为源码存在，未被调用。

顺序固定为 commands、descriptors，再按 EXPECTED_LAYOUT.json 的 allocations 原顺序过滤 readonly：wq、wk、wv、wo、wg、wu、wd、gamma0、gamma1、bq、bk、bv、rope、x。不使用 identity providers 的名称排序。N0 的 gamma0 固定 index 9，x 固定 index 15。两张表保留384/3456字节 padding，不缩为21×16/215×16。这里使用新绑定的 tables 键名，不声称恢复旧 stream framing 或原流名称。

## 来源与冷校验

SOURCE_PIN.json 只使用相对路径和真实已发布 commit 9f1ca820c6d2ca241eea9bbd38457f60849994b2 的 Git blob/SHA。两个 JSON 与已发布 RAM 源均 pin 到该 commit。三个依赖头另行 pin 到真实发布 commit bc36afdfe4fcb7b6f85da33ef49aaff93932a628，路径 development_snapshots/canonical_same_buffer_loader_source_20261018，逐项保留 Git blob/SHA，逐字复制，不改核心实现。

verify_binding.py 一次读取固定源 bytes，核对 SHA/Git blob 后只解析同一 JSON 缓冲，不导入原 producer。它交叉核对16项身份、真实 readonly 顺序、35 reservation、两表和 workspace 的范围/重叠/64B对齐，以及四region的相邻关系和fixture权限边界；完整渲染应有头文件并逐字比较。校验只读，不调用Git、编译器、网络或数值库。test_cold.py 先核同一validator源bytes，再直接compile/exec；不经动态import或pyc载入项目代码。

在本目录运行，REPO 为调用者选择的仓库：

    python3 -I -S -B verify_binding.py --repo REPO
    python3 -I -S -B test_cold.py --repo REPO
    python3 -I -S -B -O test_cold.py --repo REPO

## 单RAM预算和明确边界

完整四区区间为 [4294967296,4508440896)，bytes=budget=213473600，低于 primitive 的256MiB逻辑容量上限。16输入共94920448字节；其余118553152字节不属于初始化白名单，包括输出、workspace、间隙和BF16 guard half。

现有 primitive 分配等长 payload 和 initialized mask，两数组共426947200字节，约427MB或407.17MiB；另有64KiB chunk、元数据、allocator及运行时开销。budget约束单数组逻辑容量，不是进程内存限制。未来实际 AS 1GiB 运行须另行门控，此次没有进行该分配。

35 reservation和四region来自fixture元数据，不是恢复出的HostMemory权限实现。完整RAM地址范围不授权任何输出/DDR写入，尤其不能凭region.write将Gate/Up改成可落DDR。未初始化区域mask仍为零；factory不扩充16项输入白名单。这里未实现HostMemory、输出写入生命周期、B退休、PhysicalObserver、AXI或launch接线。canonical未加载，未取得canonical数值资格、DDR权限或Host launch资格。
