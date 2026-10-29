# TEMP / INCOMPLETE：R6 SourceInfo目录身份工具修正

## done（精确范围）
- R5 run 40820439715：155源、10 helpers、high发射、canonical micro/full、变换校验及Host SV发射实际native0；sv_identity native1。旧summary仅保留671B子日志哈希，未保存actual identity，所以不能断言R5失败只由路径引起或判定硬件不等价。
- 对既有独立批准raw c7e9d25c128004bdfc90405171eead8a4441ba20e52e829d95de4bf1122e5d96（192175561B）审计，旧正则漏439915/871649个SourceInfo注释，包含压缩列集合和同文件多位置。新的严格完整注释语法只规范目录，保留文件名、全部位置、其他注释/pragma及所有非注释字节；未知形状不放宽。
- 新scanner b49c75780d2bfb295d3e90df6d478475f42c3129dba73c850b4d564e4114965b；从上述旧批准SV独立重算规范身份6555ede34ba2980a6ebfddb13325ffb14734063d3253fdadd493bfcb4bf67bb5，871649识别/0未知。全文件合成目录搬迁仍一致。这不是从新CI输出学习baseline，不迁移数值PASS。
- 失败也先写raw/规范/预期/scanner哈希、阶段、counts和固定错误码；之后可追加92模块诊断hash差异，最多16条。模块结果只定位，不替代全文件acceptance；第二阶段超时仍保留基本receipt。summary只导出受限schema，不上传SV、IR、权重或完整日志。

## ongoing / todo
- 新R6唯一launch需独立批准，source提交本身不启动作业。保留R5及所有旧commit/run，不重跑旧任务。失败应依原新身份检查receipt，不自动重试。
- 未改硬件定义、4096 Matrix MAC/32共享Vector候选、算术/舍入、容量、工具链、canonical或变换门槛。此次只改比较与诊断工具。
- Python独立参考5/5；五块128-token完整Chisel数值0/5、最终RTL数值0/5；有效MAC利用率未实测；MoE同分参考契约仍待明确。前端及模型完整数值仍INCOMPLETE。
