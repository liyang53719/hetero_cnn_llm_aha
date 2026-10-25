# normal_m1：CPU600实际失败与阶段归因边界

- 本次实际：CPU门失败，normal exit=null、cleanup reap=-9；没有READY/OBS/CASE成功，实际结果checker未调用。
- 已保留：24原始产物及1,191pins；LOW IR只证明文件物化，不能证明lowering完成、零clock或具体热点。文件mtime推断不是阶段CPU测量。
- 状态：整体任务仍ongoing；原compile/selected-on CHIRRTL与完整128软件观测域/packet结果保持；历史FAIL/TEMP不改，不新增行为/数值/SV/RTL/硬件利用率PASS。
- 安全证据：[`candidates/qwen2_core_client_m1_failure`](../candidates/qwen2_core_client_m1_failure/README_ZH.md)。本包不含未执行150秒采样候选，不授权重跑。
