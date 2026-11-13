# 10:33 真实联合执行验证（INCOMPLETE）

现场执行闭包保留，未重编已成功库。新Host与真实17已完成链接与12reset/idle，105断言/19clock组保留；原printf配对和跨组首错误顺序尚未资格验证，不冒完整语义PASS。

本轮真实17直接实例对shared17：20周期、340全端口快照及340高相冻结快照一致，独立门控/ready变化及非法clock后永久失败禁读验证通过，仅reset/idle范围。

原86606新Host真实Qwen2前缀exit0：439周期，实测3.124694804秒，15读beat含原FP32输入4×64B；pc0/jobs1/resetRequired0，无写回。使用本轮仍在的新库独立验证，不继承失踪证据。连续输入每64B相隔94cycle，仅首遍12288beat外推约1155072cycle/2.284小时，尚未包含后续归约和写回；这是预测不是完整block实测或MAC利用率。未启动长任务或重复冷前缀。

新增严格AXI输出捕获接口，9组错误/事务测试通过；成功周期握手且B OKAY后才提交，拒绝地址/WLAST/strobe/BID/RESP/重复周期等。仅单outstanding对齐64B INCR；未收到真实Host输出，不预装参考。

五块完整128原Chisel数值仍0/5，35B完整权重缺失，原underflow FAIL保留；完整RTL及有效MAC80/90%未测。工作树干净，临时清单核验、清理0、未知旧Host未重启。基线dc7d59d0 CI43402421818 success仅payload guard。源码与证据保留本地，远端仅允许摘要。
