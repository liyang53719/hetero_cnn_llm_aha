# TEMP：原始 Chisel 观察接口的独立 IR-only 有界尝试

发布父基线为215f4670a92f29f67ba03aab52944e4653ed2aa3。专用闭包616项：原active598字节不变，加8个统一硬件观察覆盖与10个IR入口/测试/workflow；所有bytes/hash已独立核验。原32项轻量测试normal/-O均通过，不等于真实编译或发射。

仅执行原JDK/编译工具/107 JAR/固定Verilator包身份准备、完整fresh_host inventory、固定155源（8覆盖、147原文件）完整Scala compile、原DiagnoseOriginalHostMoePhaseV5空参数HIGH及official LOW。Verilator包仅供原identity inventory，不调用frontend；没有SV/native backend/权重/reference/DUT，不按模型重新elaborate，原canonical/SV门保持不变。122端口仅待测预期，不能沿旧112/119或V1 class证据。

每阶段在原supervisor.execute之前做一次只读、非原子preflight：root父子去重、lstat不跟symlink、按inode计文件bytes，保留8项元数据空间。不可读或超过原entries/tree/file/free-disk cap则不启动execute。原supervisor的memory gate、limits、monitor、cleanup全部未改；运行期仍是原采样限制，不冒连续严格上界。

独立GitHub runner与原numerical job共享hetero-exclusive-numeric-bootstrap组，cancel=false。首步monotonic总预算3600秒，阶段wall2580+cleanup225=2805秒，保留795秒。IR RSS5GiB、wall480秒、CPU420秒、tree1GiB、file384MiB、log8/raw16MiB、entries20000均不放宽。目标runner资源未预先PASS，后续有界尝试必须实际准入。

唯一上传是64KiB内的typed summary，artifact名字hetero-observer-ir-summary-实际run_id；只固定枚举/数字/hash/计数，不含rawlog/IR/class/tensor/权重或任意异常文本。即使发射成功，canonical、host全链、numerics、最终RTL及物理性能资格均为false。

本次只有源码，无activation manifest。源码发布/CI确认后才可能单独增加ci_launch/observer_fixed155_original_ir_r2_20261030_once.json；guard要求main、attempt1、单parent、source为直接parent、只新增这一文件。不得重用任何旧nonce或把旧local84990未知状态解释为结束/通过；原run41096005966的build/dedup失败证据亦保留。

完整五块M128 Chisel/最终RTL数值仍0/5。此步骤用于给新真实观察接口获取可复核IR事实，不替代完整block数值回归。
