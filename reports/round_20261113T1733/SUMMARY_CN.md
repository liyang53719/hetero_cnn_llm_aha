# 17:33 首RMS连续实跑与attention顺序差异扩散（INCOMPLETE）

现场未回退，工作树clean；main基线f1626244，CI43464972088 success，仅payload guard。原50943和86161两批正式exit0，均保存完整checkpoint后才启动下一批29364，不重启旧84795、不重算前缀。快照到cycle369445，实际B ACK输出190464字节=47616 FP32=31/128行，所有已写字节与固定hash独立参考相等，跨恢复无旧字节丢失。第三批继续，每3000周期保存完整Host/17模型/driver/AXI/control，再逐段数值硬检查，未到首RMS完成。

L3两种QK顺序分别继续完整softmax→PV：M128×8×128概率、M128×8×256 context；degree7 ExpNegative及原逐步精度、key升序PV保持。两条独立参考不互替：前轮2处masked BF16差异，传播为概率40处、context105处不同；首context[39,2,3]旧0xbd8b、当前源码候选0xbd8d。未修改硬件或原基线，不能把候选当用户批准的顺序变化，也不能迁移旧attention资格。PV主参考为有限域TwoSum顺序FMA并有抽样Fraction核验，不冒全量Fraction或硬件通过。

本地补8个真实Matrix端点共4096资源的invalid 0*Inf在途恢复：全部8恢复后12拍全部端口/time/edge一致，4096结果均原NaN，88组完整序列化状态hash一致。原Matrix ABI未导出mflags，protocol_error不等于数值fatal，因此该测试不冒Host fatal/underflow验证，旧原underflow FAIL保持。

五块完整M128原Chisel数值仍0/5：Qwen2首RMS进行中；0.8B L3独立参考推进但顺序契约有差异；L0原异常未解决；35B两块真实权重仍缺失。完整RTL与有效MAC利用率未测。临时清单已核，清理0，保留唯一checkpoint和运行依赖。源码/完整数据与日志仅本地；远端只允许摘要。
