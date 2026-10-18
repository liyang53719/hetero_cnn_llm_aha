# 固定 Qwen2 raw13 获取复现源码

本包仅 SOURCE、固定项目来源与小型安全事实摘要；不含权重、segments/tensors/pending、完整执行日志、真实代理值、签名跳转URL或环境清单。测试中的代理/认证/URL均为明确synthetic fixture。

## 来源与实际结果边界

PROJECT_SOURCE_PINS.json 和 ACQUISITION_PLAN.json 固定真实项目 commit 9f1ca820c6d2ca241eea9bbd38457f60849994b2 的5个相对源码/metadata路径、Git blob、长度及SHA256。acquirer同bytes核验后，仅AST选取4个原helper，不宽导入项目包或数值依赖。

已执行的v3 raw门产生13 tensor、22 segment、94,382,080B；SAFE_ACQUISITION_FACTS.json仅保留计数、范围和来源/manifest hash。实际资产独审已PASS，其manifest hash列于安全摘要；本包不含原始数据，不代替该独审。未生成provider、未调用canonical loader、未运行RTL、未验证整模型LFS SHA。

本包从已执行v3做安全投影：平台代理API证据删去环境存在性清单，只保留公开小metadata观察字段；重新固定plan长度/SHA。acquire_raw.py除PLAN_BYTES/PLAN_SHA256两常量外，AST与已执行v3相同。这里的新源码本身未再次下载raw。API原body未保存，报告不能离线重放原HTTP body，也不证明早期URLError根因。

## 运输、预算与持久化

固定官方Qwen/Qwen2-1.5B-Instruct revision ba1cf1846d7df0a0591d6c00649f57e798519da8。目标origin/CDN限定huggingface.co/us.aws.cdn.hf.co；平台transit通过正常默认urllib代理路径委托，不声称物理链路仅经过目标主机。应用不添加Authorization/Proxy-Authorization、不安装凭据、不记录代理值、不改平台配置；无无代理fallback或自动重试。

固定13/22/94,382,080B，每段≤8MiB；socket90s、共享900s、AS≤512MiB、cache≤256MiB。继承SIGALRM blocked先拒绝，不解封。200在读payload body前拒绝，206及Content-Range/Length/编码必须精确，每段和tensor SHA均核验。官方目标跳转最多4次且不读跳转body；不得下载3,087,467,144B整模型。

段raw/receipt成对原子发布；组装再验缓存，同bytes tensor SHA及回读成功后发布。全部13通过才写新ACQUIRED.json。仅fresh独立目录，失败保全、无覆盖/清理/续传；不伪造历史work/framing/reference。本地权重不得上传。

## 入口

默认仅校验源码，无网络：

```sh
python3 -B -I acquire_raw.py --repo REPO
```

无网冷测normal/-O各24项已过，正常合成payload为4B，长body拒例响应最大5B：

```sh
python3 -B -I test_cold.py REPO -v
python3 -B -I -O test_cold.py REPO -v
```

实际下载须另有明确执行授权与fresh目录；本源码包及SOURCE审查不自动授权新下载：

```sh
python3 -B -I acquire_raw.py --repo REPO --output NEW_OUTSIDE_REPO_DIR --execute
```

任何平台策略/认证/网络失败立即停，不换路线、mirror或凭据，不盲重试。
