# 观察链恢复：局部源与真实IO验证

实际候选 run41303497615 已通过 Dense 变换，emit_host 因真实端口85而非原122严格拒绝。源复基时 Top/Owner 误用了未含既有观察直出链的早版。仅恢复原基线已有的两个只读 Output、默认值和真实 producer 透传，含 profile 配置覆盖；不加ready、不改数值/调度路径。

独立逐159源核：148未改文件实际字节相同；原八观察override中六个完整保留。另五个被替换源的全部删除与norm改造对应，未见无关功能删除。两个恢复文件仅插入原baseline已有完整块。

实际11源类型检查以1711历史完整观察编译为底；首次局部LOW119暴露该历史class中rawScore缺最后三字段，随后补编当前真实selected RouterNumericalOwner。保留初次失败，不把旧classes当新source。最终生产类来源为1207严格11源编译+1211严格单源编译。

本fixture IO声明机械截取实际恢复Top，逐字等原已验Top完整IO块，使用真实Bundle定义；仅空逻辑、不实例化4096完整Top。官方Chisel→LOW生成122个有序完整typed端口，与原固定合同和driver方向/宽度精确一致。它不证明实际Top连接、全模型数值或最终RTL通过；下一完整构建仍须原全部门。

局部比较还提前定位新emitter的 Direction.toString 产生 Input/Output，与固定JSON input/output不符。仅对真实Input/Output枚举显式输出原canonical小写；不改expected，不接受任意字符串忽略大小写。所有失败及最终严格回执SHA在SAFE_EVIDENCE中；不上传IR/classes/rawlog/权重/参考。

新实际emitter（be1aeef…）已单源重新编译strict0，旧1133helper类仅作已验依赖，不将其旧emitter编译冒本次资格。类型检查不等于新完整SV已生成。
