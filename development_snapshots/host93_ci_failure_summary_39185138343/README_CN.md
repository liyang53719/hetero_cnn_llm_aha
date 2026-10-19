# 首次 Host93 CI：FAIL / INCOMPLETE

固定提交 `7e0ac9fdadb57e3751804b26731c520ee3bca6b1` 的首次 run [39185138343](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/39185138343)、attempt 1 已终态 failure。独立轻量 payload guard 39185138377 为 success，不能覆盖实际 job 的失败。

本目录三 JSON 是原安全 artifact 12157533845 的原字节。下载 ZIP 为 2311 字节，SHA256 `71637c7abd536304daef7a6d2a67e2ae57f58cef75e2c91bf76570d006e11b6a`；归档本体不提交。summary 为 INCOMPLETE / INPUT_OR_CONTRACT，主序列记录 63.518112 秒。官方473源、五version与五micro、fresh_autoconf、fresh_configure 共13个阶段记录 EXIT0_CLEANED；fresh_make 在47.995942秒后记录FAILED。

原失败行 exit_code=null、CPU=null、cleanup_confirmed=false 是主调用方异常路径的初始字段未被真实私有收据更新。尤其 false 不能据此认定实际清理失败；真实退出、信号、timeout与清理终态在这三件公开证据中未知。静态代码显示监督器可在保存私有 native.json 与 USAGE.json 后抛错，调用方未投影它们。原始编译日志未上传，已结束的临时runner数据不能假定仍可取回。当前不能判定编译错误、OOM、资源/信号、采样后验或日志上限哪一项是原失败根因。

Host SV/C++生成、编译、reset/launch均未执行；没有权重、RAM回放、N0或整块数值资格。原三JSON保持不变，后继将修复失败数字终态与有限去敏诊断，再单独进行有界工具构建诊断；不自动重试原run。
