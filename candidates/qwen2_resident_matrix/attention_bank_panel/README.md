# 显式 +384 B 面板与暂停/恢复同一 PV context

## 中文计划
- 已完成：新控制器、全行bank事务、独占租约独立审查；22+22冷测试通过，90+8源检查通过。
- 待办：审查后M17完整边界数值验证，再按明确预算进行M32校准。
- 待办：物理寄存器保留清单、真实mux/lease、Q/K/V输入与输出placement、RTL与完整block验证。
- M128执行入口关闭；冻结的bank_m128基线及其已通过receipt不修改。

## 资源诚实性
本版本明确提出新增96×32bit=384B panel寄存器。源码denseWeights upper96复用尚无物理retention证明，因此不声明零新增存储。panel只有一份，旧dv16为已有候选transport暂存，cv12/acc6/tmp16仍是待接线的原小寄存器借用。V与Q/K继续host输入，512B V stage未获placement证明，不能隐含称为免费。若最终新增256word输入stage，应记1024B，而非384B。

panel的整任务lease覆盖请求之间空隙，拒绝原loader full-vector clear以及普通owner准入。全部QK、score ACK和joined result退休后才允许panel phase。上下文/query/head/panel key和generation受检查；score/raw-weight只在匹配clean ACK后有效，accepted fault仍排空但禁止publish。

## 数值与调度
QK继承冻结的16-key分块、8depth/16fold/BF16 dot/FP32 scale/BF16 score。六头score beats逐一读入panel；每个key六头subtract→原exp→按key递增sum，权重原位替换score；每头一个完整beat写入prob区域。全部rawweight ACK后执行reciprocal。

PV重新读六个rawweight beats，逐key执行已接受Scalar乘inverse，保留FP32结果到Matrix ingress BF16 RNE。一个PV Matrix context保持全key的递增FMA，不在panel边界clear。Normalization从冻结bank模型的全行前置恢复到逐key前置，其每个结果及原始owner算术边界相同；异常发生时刻改变，须独立测试。

显式pv_context与suspended/issuing状态保存所有权。只有已接受Matrix step返回且pending为空时才能执行Scalar/bank；idle等待边沿记入Matrix context并由对应服务计入一次wall模型。禁止临时清空资源指针来绕过互斥。输出仍使用原joined slot，匹配ACK后释放。

## 计数与限制
每头每panel四条完整64B事务：score写/读、rawweight写/读。令G=12Σceil(keys/16)，则读2G、写2G、总4G，最小bank服务12G+2边沿（含任务acquire/release）。M128条件计数G6912，总27648事务、82946边沿；本版本没有M128实际运行。

固定4096 MAC与完整block有效MAC6,014,828,544不变。audit计入fold、softmax、FFN SiLU后的串行必要成本仍不能达到80%，division和输入供数尚需计入。数值校准使用divider_spacing=3仅作显式假设；最新独立源码审计给出现有除法25/26边沿下界，不能把3当实际硬件服务能力。hypothetical_ticks不是测量RTL周期，Pythonwall不是利用率。面板减少bank事务不构成80/90%验收。

## 准备检查

    python3 -S -B -m unittest candidates.qwen2_resident_matrix.attention_bank_panel.test_controller candidates.qwen2_resident_matrix.attention_bank_panel.test_storage candidates.qwen2_resident_matrix.attention_bank_panel.test_runner -q
    python3 -S -B -O -m unittest candidates.qwen2_resident_matrix.attention_bank_panel.test_controller candidates.qwen2_resident_matrix.attention_bank_panel.test_storage candidates.qwen2_resident_matrix.attention_bank_panel.test_runner -q
    python3 -S -B -m candidates.qwen2_resident_matrix.attention_bank_panel.check_sources

完整数值runner在源前后冻结下比较原始Fraction owner的全部score/output、固定Matrix/scalar/bank计数。M17内部25s/外部30s、M32内部75s/外部80s仅是待审查运行预算；没有native替代、权重或tensor上传。
