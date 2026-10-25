# M128 实际官方 reference pair01 增量

实际 single-layer baseline→observed 两 forward 已 exit 0，自检记录完成。独立执行复核 16724 项检查、0 失败；原公开包已通过独立技术审查，最终发布复核另行绑定；不是新的执行许可。

详见 ../candidates/qwen2_official_m128_reference_actual_pair01/README_ZH.md。

公开 source/mock 基线提交：9e4d51f1acf8f5ac62326c6dd3ec54d2ab8fc9ff。该旧 r2 20 文件仍冻结为 60 CPU / 90 wall 提案；本次实际使用独立审查的 120 CPU / 180 wall 监控 profile（4 CPU、4/1 threads、采样 1.5 GiB 非硬 RSS、最终 80 MiB）。只新增两个资源源码后像和脱敏逻辑证据，不改旧 pins。

本次：原完整 Qwen2DecoderLayer、原 32768 rotary config、真实 cold chunk128、raw embedding 0:128。y/prob 逐字相同，三边界 state 不变，29 observed 自检通过；不是全29 baseline无干扰、DUT/256 数值比较、RTL 或硬件性能结论。

48.158 秒 worker+cleanup，50.368487 CPU 秒，568340480 B 采样 RSS；完整终态 66356782 B（含 receipt/seal）。pre/post 全 manifest 各 18652 项，hash 时间在 worker budget 外。180 wall 是轮询 threshold，不是内核 hard deadline。

本公开增量不含输入/权重/tensor/raw outputs/maps/私有路径/完整私有 config/approval/claim。M16、旧 r2 和全部失败证据不改。后续实际运行需新 exact review、冲突检查及新的单次授权；本包不提供该权限。
