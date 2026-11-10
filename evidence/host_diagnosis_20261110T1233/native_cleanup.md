# 原 Host 失败清理 SIGSEGV：最小 native 生命周期修复

## 已证实 FAIL
旧 1133 Matrix 库（cccd4794…）在独立进程 create 8 个实例、完全不 eval、逆序 destroy 时 returncode=-11 SIGSEGV。不是 timeout，也不是 Host 数值失败。见 ORIGINAL_FAIL.json。未覆盖旧库、未重试 Host。

## 生成码归因
原 `Vqwen2_matrix_command_endpoint.cpp` 析构只 delete vlSymsp，不自动执行 final。cluster wrapper 的 `__DepSet_hc67d292d__0__Slow.cpp` 在 initial eval 调用 protectlib_create 填 handle；`__DepSet_hf91cee90__0__Slow.cpp` 的 eval_final 无条件把 handle 交 protectlib_final。下层 `bf16_context_lane_cluster16_rev8b_b_candidate.cpp` protectlib_final 无 null 检查，执行 handle->final(); delete handle。未 eval 的外层构造成功并不代表 protectlib 子对象已创建，故此时调用 final 不合法。

## 仅 transport 修复
增加独立 initialization_completed 标志，在首次实际 eval 正常返回后置 true；destroy 仅在该标志为真时执行原 final，然后始终释放外层 model/context。不能使用现有 evaluated 标志：drive 会把它清 false，但已经创建的 protectlib 子模型仍必须 final 释放。保留每实例 context 选择及 context 释放前恢复 default context。

不添加隐藏 eval/reset，不改 RTL、算术或 fatal，不吞信号，不把失败改成数值 PASS。首次 eval 内部中途 C++ exception（部分 protectlib_create）不属于本次已测覆盖；其 eval 仍返回 -5，此候选不声称该异常路径完整资源清理。进程级 fatal/SIGSEGV 仍不能靠 C++ catch 恢复。

## 实测范围
- 8 实例，实际 eval 前缀分别 0/1/4/8，其后再次 drive（使 snapshot evaluated=false）再逆序清理：全部 exit0。覆盖 Host 构造失败前没有任何 eval，以及多实例仅部分已 eval 的 unwind 情形。
- 修后重跑真实 Matrix direct RTL vs ABI：400 halfcycles、208400 words、200 rise/199 fall、1 output beat/1 completion，512输出全1，exit0。只是原4096中一个512 slice transport 回归，非缩硬件完整block通过。
- 候选库 SHA256 b7bcefecf2d4c8991a61cd822e91079c50a13243348670003143dbeb5dba168e。
- 未跑 Host/EDA；Host 依赖环是另一个真实 blocker，本修复不解决依赖环。
