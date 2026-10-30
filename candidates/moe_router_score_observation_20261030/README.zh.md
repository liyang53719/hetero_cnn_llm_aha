# TEMP R2：MoE 真实 selection 输入/输出观察联合候选（未选用）

升级同一候选目录；Git保留 `c63910d64f2ff63db260a2deeeb1e5993265b68a` 输入观察旧版。不是active硬件/consumer安装，不放宽原ABI/canonical门禁，不迁移旧PASS。

## 可复建基线与依赖

`BASE_AND_RESULT_PINS.json`固定全部base/result hash：Top和driver以仍保留的 `candidates/p0_resident_observation_20261030`（feafbd6d）为底；另外三Scala以原fixed155核心源为底；实际联合consumer以active7bb的00bac8ae为底；官方wrapper以805a31aa为底。**不依赖即将被本包覆盖的c639候选旧fullfile或local-only base。**

保留P0观察接口及真实owned consumer。R2联合consumer已合并P0 BF16位扩展比较和MoE完整输入/真实输出诊断，不能安装P0旧c482副本覆盖7bb。原ffb1 observation合同、host/ABI/环境/监督/calibration/exit2未回退。新版helper有内部hash检查，但外部connect/source pin闭包与producer资格尚未安装；不能仅改pin强跑。

官方model不在本包：须从固定Transformers revision/archive复建并校验ea77…，原runtime依赖及wrapper配置文件仍需独立pin。这里只有源码/patch重建能力，不宣称整个runtime可脱离依赖运行。

## 实际信号与协议

原FSM selectFeed的in.valid与selectRead的out.ready互斥，assert只验证无反馈。Valid复用kind0输入、kind1真实selection.out.fire，score/index/rank/last直接来自实际out.bits；token/identity来自原保留command。每token256输入+8输出，完整M128为32768+1024事件。输入131072B，真实输出FP32 score与UINT32 ID各4096B；无按ID回填actual输出。

保留P0 689bit观察后，MoE R2预期259bits/10个信号，总Top **122端口仅源码预期**；119是旧版预期，112是更早P0独立LOW证据，均不迁移至R2。原FP32算术/舍入/路由/topk同分规则不改，小ID契约未获用户批准。

## 已撤回的错误过滤与修复

旧R2 collector `15e0cd55…` 以actual score==input[ID]及降序/数值范围作为采集门，可能筛掉需诊断的错误值；该GO撤回，不安装。最终header `fc029f28…` / driver `f4f00dff…` **只对协议/身份/覆盖/fault fail closed**。数值link/order/NaN/Inf/负数/±0/>1只计数，任意UInt32原位型保存，绝不clip/round/nan_to_num或回填。真实clean完整数据的错误由consumer报告。

consumer分别报告：①实际out与实际input[actualID]内部一致性；②独立官方全概率在actualID处的误差；③独立官方全概率在官方未改topk IDs处的按rank误差。派生对应诊断不冒actual输出，文件缺失继续INCOMPLETE。全部原bits保留，ULP/绝对误差仅诊断、不创容差或数值验收。总体始终INCOMPLETE/exit2。

## 真实与合成证据边界

- **新Numeric R2没有编译/IR发射/ABI验证**，不能继承输入版862class/native0证据。旧IR session84990丢失终结RESULT/官方LOW属旧版，仍INCOMPLETE/观测不可用，不作为R2成功或停止证据。
- 原固定官方gate真实fixture native0，9.347591102秒，采样RSS354574336B，native pre/post各12；使用合成[128,2048]输入/合成[256,2048]权重，只验证同次router_probs对象捕获与原tuple/logits/IDs/weights不变。不是官方完整block参考。清理仅原reference supervisor stop/killpg/wait＋postverify，不冒strict IR清理证明。
- 跨语言NORMAL/BAD_BITS是实际执行的C++ collector→Python reader**合成fixture**，不是DUT或官方reference；包括NaN payload变化、±Inf、-1、-0、>1及input/output不等。独立复核已按预期位型核全部dump SHA一致；没有隐藏数值错误。证据仅hash/计数，不提交dump。
- 完整M128 block数值 **0/5**，最终RTL数值 **0/5**，无PPA/90%利用率证明。

## 复建与轻测

```
python -B materialize.py --repo "$VERIFIED_REPO" --output "$FRESH_OUT"
cd "$FRESH_OUT"
python -B -m unittest discover -s tests -p 'test_*.py'
OFFICIAL_MODEL_SOURCE="$PINNED_MODEL_SOURCE" python -B test_local_observer.py
```

重建严格核base与result SHA，仅写新目录。需要原生合成fixture时再显式运行 `tests/test_collector_reader.py --producer "$FRESH_OUT"`；它编译小C++、生成临时合成dump并清理，不执行RTL。不要把该脚本或mock driver语法当实际硬件。原完整reference wrapper运行仍需原目录依赖，真实完整reference未执行。

打包后从仍保留的7个base重建全部result SHA成功；新隔离目录38项测试＋7项官方observer轻测试通过。打包复核未重编C++、未导入Torch。

不含IR/class/raw logs/tensor/weights/机器本地路径；不改active pins，不远端发布，不删除原运行证据。

## R1 归档与重建准入
`legacy_r1/` 同字节保留原包的旧编译边界、旧 consumer guard 和三个旧测试；测试追加 `.txt`，不参与自动测试发现或 R2 结果。对应原位置应以普通 Git 删除，历史 c639 仍可恢复。旧编译证据不迁移给 R2。
`materialize.py` 的 base/result/hash/fresh-output 与补丁上下文准入使用显式 `ValueError`，不依赖可被 `python -O` 移除的 assert。
