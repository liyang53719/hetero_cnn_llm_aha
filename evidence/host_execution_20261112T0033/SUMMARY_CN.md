# 00:33 候选Arc实际诊断与有限边界对照

## 实际编码构建与运行
从已验2333固定4096 HWIR生成新候选Arc机器码，原session53859 exit0；Arc87.80秒、llc-O0 41.93秒、链接成功。保持20严格回调组（105原error/fatal与1 immediate assert）、17真实native及85公共端口；新layout保留3诊断wire，使用新字段/hash，不沿旧offset。新libhost SHA1bc4578cb8f2de7726e70af2ec8c34c0db9416ff487fa563508faaded5b66f45，layout SHA f4927956f5876f53174864e2412d8c32bb4c8e3b6a27ebd5330f5ccbbd4b5c22。保留原数值精度和错误优先级；未默认删除断言，未改变4096 Matrix资源。

三项独立有限新候选执行均exit0：idle8周期无AXI/cause；synthetic首RMS +Inf172周期12AR/12R、零写，原Top仍Protocol7，新增诊断raw8/mask6实际可读。mask6表示当拍globalFault和authority.currentFault，不是完整根因。与1933保存的13采样1144输出word一致。finite零输入204周期无结果/故障/cause，与原11采样968word一致。Inf81637、finite12420均终态。没有声称所有周期或所有输入等价，未完成RMS数值或触发strict fatal；旧顶层预期8的FAIL仍保留。

## 输入桥实际工作
将dt_bias显式零padding候选接入1233 L0全部15段只读地址映射，复用现有AXI回应器局部测试，9项通过：原32B有效源不改、64B完整读、4周期R反压稳定/ID37/LAST/消费、其他14段首尾读；跨分配尾/空隙/缺hidden/中间输出/只读写/错误size均拒绝。新padding映射SHA80ec6c294f30499079744a58af3307e8829080c096a1795fd08540339dcf7777，不冒原未知padding恢复，未接完整Host。正式执行前仍需全量pin校验。

## 五块128与后续
完整原Chisel数值仍0/5，最终同刺激RTL未通过，完整block4096有效MAC80/90%未实测。Qwen2真实FP32新21-op绑定/独立参考仍在；未知旧Qwen2/L3会话及启动边界未解，不重启。0.8B L0/L3缺原hidden/身份证据；35B L0/L3缺完整payload且下载限制未解除，没有重试。原L0 head4 underflow FAIL保留，不继承遗失PASS。
当前PASS仅候选诊断可见性/有限控制对照和输入适配测试，不升级完整prefill、strict fatal或RTL资格。下一步在允许的独立边界中补诊断保持/复位和异常对照，完整模型需解决旧任务身份与输入缺口，不以局部测试冒主线完成。

## 版本、CI与清理
开工main0dad203afdc8175b0e7c3a3d3f69caf481efa989，CI43121691006成功，仅payload guard。工作树干净，可用RAM约9.1GiB/磁盘55GiB。临时清单已核，既有数据清理0、唯一证据保留。53859/81637/12420终态，无新完整profile。只发布允许摘要和hash，不上传源码、原始日志、权重或生成数据。
