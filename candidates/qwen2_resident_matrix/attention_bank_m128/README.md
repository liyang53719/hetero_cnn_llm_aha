# 单作业分块 Attention：M17 → M32 → M128

## 中文计划与状态
- 已完成：独立候选实现，每个查询按最多16个key分块QK，仍是一个多行作业、一个实际Dense owner和同一个A Banks。
- 已完成：M1/M2逐位、计数、时序和流摘要与冻结bank模型一致；17-key局部QK验证尾块、顺序、写ACK后有效性。
- 已完成：独立审查通过；12项冷测试正常/-O均通过，77个依赖与7个候选文件源检查通过。
- 待办：审查后真实M17边界作业和M32成本校准；获得明确预算后，才运行真实M128。当前没有M17/M32/M128整作业PASS。
- 待办：Q/K/V输入、最终输出物理放置，真实RTL控制/mux/异常标志和端口时序验证。当前host输入不能证明硬件可供数。

## 数值与存储
controller只将原先单块QK拆成递增16-key块；每个输出仍是8个depth步骤、16条stripe顺序fold、BF16 dot、FP32乘0x3db504f3、BF16 score。softmax、逐key求和、全体归一化后PV的顺序保留。最终不满16个key的块仅填充未选择的B列，不增加任何有效因果key的FMA。

storage.write_score_packet将一个已完成块写进原score区域。每头prefix只能递增，只有匹配clean ACK后更新；Matrix live结果保持到该块score写ACK。没有复制16KiB结果tile，没有128-word score缓存。score/prob仍在同一96条scratch line中，7P条64B事务。源文件和旧候选均未改写。

## 运行与证据
冷测试须用显式模块（namespace package不支持本目录通用discover）：

    python3 -S -B -m unittest candidates.qwen2_resident_matrix.attention_bank_m128.test_controller candidates.qwen2_resident_matrix.attention_bank_m128.test_runner -q
    python3 -S -B -O -m unittest candidates.qwen2_resident_matrix.attention_bank_m128.test_controller candidates.qwen2_resident_matrix.attention_bank_m128.test_runner -q
    python3 -S -B -m candidates.qwen2_resident_matrix.attention_bank_m128.check_sources

run_numeric逐次运行原始owner Fraction oracle与候选，完整比较每个score和output word，验证请求、返回、ACK、银行事务及源前后身份。只有安全摘要/散列输出，无tensor上传。M128必须先提供同一精确source map的成功M32 receipt；这只证明准备条件，执行仍需预算批准。

预算提案：M17内部25s/外部30s；M32内部75s/外部80s。M16原始+候选实测13.55s，按因果对数推算M32约52.6s，M128约823s。M128内部1200s是可选入口上限提案，不是已批准或已执行的结果；外部硬期限必须单独设置。没有native替代，也没有RTL执行。

## 资源口径
M128 P=99,072；QK分组6,912，PV分组256；Matrix步骤71,808，selected FMA25,362,432；旧owner请求1,585,152。scratch事务693,504，最少2,080,514个模型银行边沿（含acquire/release）。这是明确串行、保守策略，单银行成本已不能支持80%整体目标。

hypothetical_ticks仅为假定捕获/除法输入下的预约模型，不是硬件周期。4096固定MAC与完整block有效MAC6,014,828,544分母不变；原始scalar/SiLU成本、owner互斥和未放置输入均不能消失。本候选不声明整体利用率、RTL PASS或完整block数值PASS。
