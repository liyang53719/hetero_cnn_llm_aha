# 固定预处理微型资格证据

v3一次实际执行及独审结果：PASS_MICROFIXTURE_ONLY。6case退出0/1/0/1/0/0均符合预期，3个路径/源line负例实际在preflight拒绝。UVM开关、缺include拒绝、合法注释与identifier token-paste、已知Verilator内建宏及-E --MMD依赖输出均实证通过。官方top+5header的.d为6个输入加固定binary共7项。

SAFE_CASE_RESULTS.json列输出/.d哈希与原限定scope cleanup记录；POSTFLIGHT_SAFE.json列归一化输入/dependency集合，13个原fixture、工具、manifest及case复制输入执行后全部匹配。无主机路径、PID/boot/session/monotonic、argv、raw proof、__verFiles.dat或原日志。原完整私有receipt哈希列在QUALIFICATION_HISTORY.json。

前一次v2微资格仍总FAIL：前5case符合预期，第6漏资格fixture deprecated/registers.svh；3preflight流程未到达。v3仅补官方固定header和literal递归预检后获得新的单次批准，没有重跑v2或合并成假总PASS。

两次真实source export 39026847303、39028560366均保持FAIL，没有可复用DMA provider source包。第二次失败安全摘要在相邻IDMA_SOURCE_EXPORT_FAILED_39028560366目录，第一份安全记录已另行保留。

当前v8真实source-export后继采用固定官方-E路线，仍仅候选/冷测，未执行。微资格通过不能替代完整生产闭包。其边界为固定可信pins+严格filelist/直接include路径检查+事后.d未知依赖拒绝，非OS sandbox或任意恶意宏防护；未知动态include必须逐个审计，不能宽放。
