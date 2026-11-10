# 共同Host外部稀疏内存组件（TEMP）

原profile1/2程序使用64GiB/128GiB等64位地址，旧Qwen2稠密vector不适用。新增纯供数SparseHostMemory按4KiB页分配，不按最高地址分配；不进行任何算术、不产生预期中间值或producer receipt。所有读取逐字节要求已有readonly初始输入或真实写入；byte mask、readonly、溢出和64B对齐均检查。

普通-O2/-Werror及-DNDEBUG构建测试通过，覆盖高地址未初始化读、部分写、readonly保护、溢出、对齐及零mask不分配页。

仅组件测试；尚未接入真实Host AXI bench，不能声称数值或4096资格通过。生成可执行文件本地保留不提交。
