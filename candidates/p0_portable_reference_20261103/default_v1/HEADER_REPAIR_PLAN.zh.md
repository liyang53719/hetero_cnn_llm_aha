# TEMP：run41720209902 的最小 header-only 修复诊断

这是独立一次请求，不是原run rerun，也不会自动启动full reference。

## 已知事实和未证实部分

原run41720209902的三个安全JSON显示：原26-wheel/runtime安装和实际import阶段PASS，16.007秒、实际ATen DEFAULT、4 intra-op/1 inter-op；weights阶段native1，0.396秒、PRECHECK_PIN、checked0；reference和RoPE未开始。这个结果不是数值不符。

只读历史请求证据确认，相同canonical checkpoint URL曾有22次HTTP206、PASS_RANGE_BYTES_ONLY，最终host均为us.aws.cdn.hf.co。其中header恰为0–38535/3087467144、38536字节、SHA124516afba769374e2b948e185dd3e9203e2412daaef3f2ccf7bdbaca0f88987。原新候选漏掉这个精确host，其URL guard必然拒绝这条已成功过的路径。只补这一个host，不采用后缀匹配，不降低HTTPS、range、length或SHA要求。

原失败的三个JSON没有保存redirect/HTTP失败点。因此“遗漏已知CDN”是已证实的兼容性缺陷，但不能宣称它就是run41720209902的实际失败根因。此次只用固定enum诊断收集缺失证据。

## 唯一执行范围

- header_probe只从原canonical URL请求原38536字节header。最多4次受限redirect，URL必须HTTPS且host精确allowlist；redirect响应直接close，不沿用urllib无限read redirect body。最终body一次有界read最多38537字节，以一字节sentinel拒绝超量。
- HTTP206、Content-Range、Content-Length、Content-Encoding均严格验证；header SHA、8字节前缀、JSON重复key/非有限值、原12项name/dtype/shape/range全部验证。无权重body读取。
- 不安装runtime、不运行Torch、不获取12权重、不运行两forward/RoPE/DUT/EDA。header通过也不自动继续。原fixture、26 wheels、12权重SHA、24tensor+RoPE SHA和所有数值路径不变。
- reuse既有supervisor源码，并给新小job显式60秒CPU动态门（原reference默认3600保持）；从checkout前单一clock计180秒，stage work最多120秒，cleanup最多30秒、RSS验证最多5秒、尾部最多5秒；实际remaining优先。stage CPU20秒，RSS256MiB，AS1GiB，新owned tree16MiB，file/raw log1MiB，compressed log512KiB，entries5000。真实内存余量≥RSS+1GiB，磁盘初始≥2GiB、持续≥1.5GiB。CI总5分钟兜底；GitHub checkout/上传action CPU不在controller CPU记账内。
- 同样需要native/owned-process-group cleanup/EOF/gzip/RSS日志完整验证。归属不完整标INCOMPLETE，保留root，不借用既有未知owner资源，不宣称escaped-tree containment或零超调。

## 输出、seal、一次性身份

仅三个固定小JSON：RESULT.json、CHECKS.json、HOST_RESOURCES.json，各≤4096字节、总≤12288字节。只含固定status/reason/point/host enums、HTTP status、长度、hash、12元数据检查数和资源计数。禁止signed URL、任意host字符串、headers/body、异常自由文本、权重或任何编码载荷。HTTPError不读取错误body。

私有TERMINAL seal绑定本run identity及三个文件hash。PASS_HEADER_ONLY额外要求GitHub真实controller outcome=success，写出JSON后deadline/alarm失败不能上传残留PASS。schema拒绝unknown字段、NaN/Inf、bool冒充int、symlink/hardlink/额外文件。seal不上传。

新的唯一入口是ci_launch/p0_portable_header_repair_41720209902_once.json，必须仅新增这一文件、first attempt、source是launch直接parent，manifest明确failed_run_id=41720209902与HEADER_ONLY_NO_RUNTIME_WEIGHTS_REFERENCE_EDA_THREE_JSON范围。源码发布无nonce；只有父任务统一发布并另加唯一nonce才启动。PASS只证明当次header网络路径/字节/元数据有效，不证明原失败根因或任何reference/硬件数值通过。
