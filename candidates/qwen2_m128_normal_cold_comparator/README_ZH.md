# 完整 M128 新 profile：正常加载与终态比较器资格

本小批发布已独审的默认关闭准备源码，以及一次真实 normal cold 的有限通过证据。唯一 cold_run01 exit0，完整15角色／9个继承服务方法正常绑定，另7个模块请求产生8次完整模块执行记录。没有运行完整DUT，没有服务构造／Matrix ELF／job／用户tensor或oracle数值读取。允许且实际发生原NumPy和PyYAML依赖初始化，包括已固定扩展库及正常依赖自检；不能称“完全无native加载”。

实际cold：736 pins／158235944 bytes前后重验一致；17 ELF加2非ELF共19个映射文件，331最终modules。1 CPU affinity、每进程20 CPU秒硬限、256MiB地址空间硬限、25wall监测；地址空间不是RSS。spawn至cleanup6.405191730998922秒，至postflight6.527706308988854秒。原证据未记录独立测量CPU/RSS，不补造。worker已reap，剩余自有进程为空。实际结果及独立审查投影见evidence/cold_execution_projection.json；公开投影hash不能冒称原review hash，原件identity单列。

比较器：cold只正常导入，没有执行数值比较。comparator/comparator.py是独审R2原字节，API由真实ExactOraclePathGate的live-terminal窗口调用，不能用常真guard。全32inventory涵盖stage/raw、十字段、SiLU seal及KV别名，不是32个独立物理tensor。KV两半必须逐word等于实际k/v，包含±0差异；所有观察域有限性、BF16低位、source/mask/frequency hash和比较前后数据摘要都校验。源代码不重算算子、不造中间值。

数值范围是22个完整实际源逻辑视图及3个因果域。scores/prob/softmax_fp32在M128只比较99072个真实因果位置，97536个future位置不补零。cos/sin用真实[128,64]操作数按column%64视图对应官方逻辑域，不构造新DUTtensor。mask/repeat_k/repeat_v/logits没有独立物化来源，不能从oracle补值，须另有真实协议证据，full29_numeric_pass固定false。原BF16算子max≤0.03125且mean≤0.005；y max≤0.05且mean≤0.01；FP32 rowsum≤2e-5不套给BF16prob；softmax_fp32跨实现误差仅诊断，没有自造容差。任一observed_domain_passed=false必须让完整验收失败。

256仅是旧参考诊断标签，不是当前DUT provider容量。当前实际rope provider为[2,1024,64]、FP32、524288 bytes，canonical/active均128，inactive rows128..1023为零；源码check_prefix_numeric.py337–345/458–460是Python math.pow/cos/sin double计算后一次FP32存储，不是旧文档所写FP32 powf/libm配方。provider SHA为f6c6e15e3f480afe2e9ebfb05719ff8d20a77a5a5551aa8a44bf2a49870d77af。官方32768／rope1e6保持不变，位置0..127合法不证明两种构造算术位等价。未来实际cos/sin和q/k比较可揭示差异，但不自动归因容量，也不声称完整block影响为零。冻结比较器中的project_rotary_positions=256字段仍是历史诊断标签，本批保持已审执行源码原字节；该标签不得被解读为实际provider容量或精确新DUT profile事实。官方参考生成PASS不等于DUT比较PASS。旧完整M16 DUT未运行，不伪造先决PASS；直接准备M128是因为dense固定128槽，M16并不节省同阶dense开销。4096 MAC固定资源分母不变；legacy PV理论63.57%上界仍挡80/90%，本批不是性能、RTL或硬件验收。

## 文件与复现边界

cold/下4个wrapper源码及qwen2_fullgraph_normal_binding原adapter/依赖pins保持原字节；comparator/下实现与3个测试同样保持原字节。pins列source组成、316个源、冷闭包逻辑标识及实际input/provider/oracle身份。配置中的私有路径、一次性APPROVAL/claim、原module地址/rawmaps、输入及输出tensor未上传。公开包不是自包含运行环境，不能仅checkout后执行run_cold.py就重现原成功。原一次账本已消费，不提供复用或再运行授权。

可在干净公开checkout用既有Python执行纯helper测试：python -I -B candidates/qwen2_m128_normal_cold_comparator/comparator/test_comparator.py；python -I -O -B candidates/qwen2_m128_normal_cold_comparator/comparator/test_inventory.py。这不是normal目标加载。test_callback.py使用完整M128形状合成数据并写SYNTHETIC_RESULT_R2.json，应在独立临时副本、有界45wall内执行，不在冻结证据目录重跑。其17.403秒作者记录只说明mock控制/索引，不是实际模型数值或全运行无干扰。

实际cold复现必须先根据pins重建旧公开source-only composer、14个新候选后像及已审正常adapter，提供固定解释器/NumPy/PyYAML和全部736文件闭包，再生成新的本地路径config、exact独审和一次性技术GO，使用fresh输出与claim。命令接口为 PYTHON -I -S -B cold/run_cold.py --config CONFIG --config-sha SHA --review REVIEW --review-sha SHA --approval APPROVAL --output FRESH --go GO。占位符不是可执行config；禁止绕过绑定以运行。原cold 17项测试依赖未发布的路径config，公开只保留原日志/身份，不谎称本包可直接重跑原17项。

历史R1两个比较器缺陷、缺/usr/bin/time导致目标未执行、review脚本误强制module顺序，以及原raw module FAIL账本都保留归因。后一review辅助问题不代表实际cold失败。公开投影只增加有限资格，不回写旧证据。新完整DUT仍NOT_RUN，后续须新的完整worker、实际trace／协议检查、预算、exact独审及root GO。

## 发布隐私更正

前版源码/数值结论不变，但发布预检漏扫解释器安装绝对路径，因此原privacy PASS无效；connector在远端写入前拒绝。新r4只修更安全metadata投影和准确provider说明，不重跑代码、cold或数值。全部736 pin_id、bytes、SHA、顺序和重复项保持，安装位置改python3.12逻辑角色，系统库改system-role加basename；ordinal是独立身份，绝不按basename合并。原review SHA保留为original_identity，投影有自己独立SHA。新包待同一发布通道按新独审进行一次重试，不以替代通道绕过拒绝。

扩展独审继续发现并阻断r3中的12个非复现必需地址字段：oracle两项原Python返回对象地址，以及五个provider角色各两处allocation address metadata。r4公开投影省略这12字段，不推断后者物理／进程语义；原manifest、旧投影和拒绝记录私下完整保留，original_identity仍绑定未改原件。roles、shape、bytes、hash、736 pins顺序／重复、源码／测试／原日志均不变，不重跑目标。
