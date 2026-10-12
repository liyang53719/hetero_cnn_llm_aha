# 0.8B L3 完整 prefill 模型接入

当前目标是实际128-token完整Attention block的软件模型，随后才在Chisel接入并重放冻结RTL刺激。前一项0.8B L0的cold128→真实carried128完整typed模型已在37b7de的记录中完成全部已分配数值门；对应Chisel/公共Command128仍有明确缺口，不能混为五block总验收完成。

## 官方BF16参考入口

新增capture入口使用固定模型2fc06364715b967f1860aea9cf38778875588b17、Transformers 14e738b5d0cc69aa27a95dde272aea41fde44f2f、Torch2.10 CPU DEFAULT和原checkpoint混合dtype。它运行原TextModel.forward，从真实BF16 embedding经过完整GDN0/1/2到完整L3，在L3输出后才停止；未执行其余层、最终norm和LM head。没有候选算术替换或向模型注入中间golden。

同一个原DynamicCache连续执行cold和carried调用。M16的fixture取0..15和128..143，真实cache长度是0→16→32；RoPE position有显式间隔，不能把它描述成128-token历史。M128才是0→128→256且位置连续。causal mask使用实际cache长度，保留原GDN history/state和Attention K/V的完整前后哈希、形状、dtype与原始字节。

模块钩子与ATen观察只读取实际输入/结果，不替换算术、mask或返回值；未观察到的内核归约树不补造。原57-producer契约与旧FP32门不变，此入口只采集官方数据，不授予数值PASS。后续需要把实际共享owner数据链逐项映射到这些观察，并沿用全部已分配数值阈值。

## 失败保全与环境恢复

每个raw tensor先写完并fsync，再追加并fsync一条带key/shape/dtype/bytes/hash的JSONL索引。只读恢复默认逐文件验证，拒绝完整坏行、重复key/file或内容漂移；仅可忽略未换行尾行。没有索引的raw文件保留，但不能猜key、造tensor或据此继续执行。模型构造前保存已核验的源码身份；普通异常保存失败回执，部分证据不算成功。

进程内120秒CPU硬限不能保证异常回执，SIGALRM也不是原生库内部的严格墙钟限制。调用者必须外部监督退出码/信号与墙钟/内存。已准备的单次监督为150秒外层上限、3GiB地址空间上限和256MiB捕获字节上限；这些是宿主预算，不是硬件资源或周期。

20:08 UTC原环境的M16官方采集曾正常退出，226个实际tensor共14,402,048B，manifest SHA4a22043eed901f9e959a63e76e2f75542cfb21e39ef1e1e12f1eb666de38dec2；随后唯一M128采集启动。20:10工具返回executor key changed/transport disconnected，原工作目录在当前环境不可见，M128没有可恢复退出回执。不能归因人为删除，也不能将其算数值失败或成功。原始M16/M128数据当前不可验证，因此旧采集结果只作历史记录，不复用为当前数值通过。

已在独立新目录从远端恢复精确37b7de及原CI工件。两份capture源码从可访问创建内容和补丁逐字恢复，最终SHA与旧版本一致，随后在新环境重新跑11项小测试；python -S也通过，证明该小门只需标准库。旧L0/L3权重可逐hash复用；固定runtime和额外29份prefix payload分别重新核验/恢复，不重跑已完成的GDN长模型。

## 当前清单

- done：固定BF16 prefix/L3参考入口、真实cache/position区分、观察边界、partial索引与失败保全、独立源码审查、恢复后11项小门。
- ongoing：新环境固定runtime/payload恢复和一次新的受控M16→M128官方采集，必须有新的来源身份与实际终态。
- to do：L3实际RMS→Q+gate/K/V→Norm256→partial64 RoPE→KV→矩形QK/Softmax/PV→sigmoid gate→O/residual/postnorm/FFN/residual完整模型接线及原门验真，随后Chisel/RTL。

新CI只有标准库11项源码/失败保全测试及Git payload检查，不下载权重、不跑Torch或RTL。Qwen2 cold M128和0.8B L0双M128维持各自已完成模型范围；0.8B L3、35B-A3B L0/L3和五block联合验收仍未完成。
