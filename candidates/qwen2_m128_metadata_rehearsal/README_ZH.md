# 持久 metadata、精确缓存回退与一次真实 metadata-only 冷验

本包发布默认关闭的新源码后像、两份最小patch及已有证据的脱敏投影。一次独立metadata_cold01已通过正常完整source加载、provider包装和真实public21 metadata生命周期：21 commands、215 descriptors、8持久metadata文件。8文件hash逐个等于旧失败尝试生成的对应文件。这里没有完整DUT数值PASS；本包自身不作为新长DUT的执行准入证据，也不涵盖本包冻结后的DUT尝试及其结果。

## 旧失败与最小修复

旧真实DUT尝试仍为FAIL。Matrix ELF加载和签名配置已到达，但尚未构造service/reset/job/PC算术：真实fixture的TemporaryDirectory退出清理走fd-relative os.open，被始终SEALED的oracle门拒绝，函数尚未返回。由traceback及固定源码控制流定位，不冒称独立每native符号调用计数。原claim、49份产物、FAIL及全部输入/源码不改。

metadata patch只新增可选keyword metadata_root/metadata_parent和窄目录helper。默认两个None时原TemporaryDirectory清理不变；新选定runner显式使用fresh输出下唯一metadata父目录和TemporaryDirectory(delete=False)，成功/失败都保留8个metadata文件。原pack/convert、命令/描述符内容、算术与阈值不改，不开放relative oracle读取，不monkeypatch tempfile/shutil，不删除失败证据。

cache patch仍对所有pyc读抛PermissionError，不允许cache内容。只有精确CPython SourceFileLoader同一live调用、固定.py原字节source-open、实际compile bytes/hash、完整exec code及原loader对象匹配时，才将该次拒绝归为EXPECTED_PINNED_SOURCE_FALLBACK。未知、未完成或oracle原hook拒绝仍sticky；exec audit不证明模块体完成，后续异常仍独立失败。最终snapshot发现late denial必须推翻成功，不能盖掉原异常。在本包覆盖的验证中，新数值worker后像仅经mock验证；本包记录的实际metadata cold采用独立metadata worker，不据此声称新数值worker已执行，且本包不涵盖后续DUT尝试结果。

## 真实冷验范围与资源

正常15 source roles和9服务方法绑定；真实observer.load_observer工厂执行但不创建Fields/Capture/ServiceTrace/owner。14原provider共94916608 bytes逐hash读为immutable bytes，仅创建并验证原bytes_provider包装，没有调用包装读取、没有tensor算术。允许原NumPy/PyYAML依赖初始化和已固定扩展加载，禁止Matrix ELF、服务/owner/reset/job、任务算术、oracle值读取和比较器。oracle全程SEALED、comparison_attempted=false。

208个cache fallback事件关联205份固定源，204 NORMAL＋4 METADATA_ONLY，cache字节全部拒绝。独审以同固定解释器/filename/flags和named-local代码对象生命周期复算全部hash。marshal不是通用跨进程稳定编码：初次reviewer临时compile表达式产生引用编码差异，失败和归因保留；按运行同样named-local方式复核一致，没有target import或cold重试。

实际资源为1CPU affinity、20CPU秒每进程硬限含线程、1GiB AS硬限；25wall监测另cleanup3秒，512MiB树RSS采样限不是内核hard cap。实际worker9.715559731秒、reaped CPU9.660251秒、sampled peak RSS150667264 bytes；1303 pins／423753872 bytes前后opaque核hash一致，父pre/post时间在worker预算外。44产物共3023789 bytes含receipt/seal，低于32MiB；日志空、trace0、worker已reap、无剩余自有进程。prelaunch辅助检查的scope误写“after terminal”源自复用helper默认文字，实际时间及launcher顺序证明启动前核验，原文件未回写。

## 公开文件及复现边界

metadata_postimage下fixture/runner、cache_postimage下runtime/worker/common和两份测试、metadata_cold_source下5个源码及patch均为原字节。source pins列preimage/postimage、runtime唯一ordinal+bytes/hash，重复描述不合并。evidence保留原23×2、33×2、42×2历史日志；原review/receipt/seal hash与新projection自己的hash分别绑定。公开包不包含原private config、APPROVAL/claim、PID/object id、raw modules/maps、provider地址、命令/描述符二进制、输入/权重/oracle tensors。

cache的30＋3纯stdlib tests可在Python3.12独立临时副本复现：python -I -S -B cache_postimage/test_cache_fallback.py 和 python -I -S -B cache_postimage/test_worker_policy.py，-O分别复跑是另一模式；这些只是synthetic loader/worker策略验证。本次打包没有重跑。旧23 fixture测试和42 combined测试还依赖本地原composer/exactconfig及未公开closure，公开仅保留历史日志和身份，不声称直接checkout即可复跑。

两个source patch只能应用于pins中精确旧后像，不能套裸main假定兼容。完整replay须提供原source/runtime/provider/oracle及旧FAIL闭包，重建新本地path绑定与14候选、固定解释器，保持source/code/module/maps、父子能力管道及单次新claim硬门；原admission.py内私有解释器常量不复制到公共payload，只保留hash，不能补任意解释器绕过。公开源码故意不假装自包含执行环境；没有创建未经实际执行的替代public adapter。

后续真实DUT必须独立新profile、exactreview和一次GO；原旧失败不能重试原账本。metadata成功不升级 observed_domain、full29、event_protocol、actual_terminal、Matrix ABI、RTL或利用率。实际RoPE provider为[2,1024,64]、active/canonical128、其余零、double math.pow/cos/sin后FP32；256仅旧参考诊断标签，官方32768不改。4非物化节点和3因果域的数值范围不变；固定4096 MAC与legacy PV63.57%理论上界继续保留，未证明80/90%。
