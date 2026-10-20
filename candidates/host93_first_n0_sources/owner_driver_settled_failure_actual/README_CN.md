# TEMP：Owner 新 driver 重链后的 settled failure

原 session 92317 已自然终态。compile 自然退出 0，用时 1.663322 秒；link 自然退出 0，用时 0.123427 秒；局部 owner run 自然退出 1，用时 150.140876 秒。三阶段均未超时且 cleanup 已确认。outer 退出 1，用时 159.6861525139975 秒，于 2026-10-20T00:12:16.633883+00:00 结束。原 EXECUTION_RESULT.status 保留 INCOMPLETE，failure_type 为 ValueError，failure_code/failure_boundary 仍为 null；run 监督诊断为 NATIVE_SUPERVISION / CHILD_EXIT_NONZERO。本摘要记录本轮实际 FAIL，不向旧收据倒填字段。

## 有限实际进展

本次从已核 owner compiled archive 和 runtime objects 新编译 v3 driver 并链接，未复用旧 driver object，未重做 generation/backend。12 个固定复用文件共 24,151,608 字节；新 driver 的 .d 闭包独立核验。新 ELF 为 12,726,288 字节，SHA-256 211b05da7c5747970277f2d0756ea25a39f6156113a3c1bf803796f57cd2ab4e。完整 run log 共 4 行、20,870 字节，SHA-256 4eacd6c718e0c7f69a440889a9d03345fbce45e13b30ef3028a8aaabbdca7ea1。

末条为 CONTRACT_FAILURE / RESET_REQUIRED_SETTLED，edge=92364，主采样为 LOW_POST_EDGE_SETTLED_SOFTWARE_RETIRED。保存的同沿 raw-high 标记为 HIGH_EVAL_POST_EXTERNAL_INPUTS_PRE_RETIREMENT，reset_required=true；正常 falling-low eval 后 win_resetRequired 仍为 1。两份观察均有 dense_state=6、dense_status=8、owner_sharedPoison/router_bad/coor_bad/coor_serviceError=1，banks_poison/matrix_poison=0。这是实际 settled failure，不能由同时为真的聚合项推出首写先后或上游根因。

软件账本已经记录首 drain 完整退休：128 个 write descriptors、1280 个 data beats、128 个 write responses、81,920 committed bytes，drain terminal edge=81467。它们是 owner typed-RAM 接口事件，并非 iDMA/AXI B 证明。本轮越过了旧 v2 的首 drain 早期失败位置；旧 FAIL 原件和结论仍保留。

随后第三 window request 在 edge=81469 被软件记录，末条 window requests=3、terminals=2；matrix groups=3、dones=2、issues=12800、current_window_issues=5120。当前 window 寄存元数据为 ng=160、K=[0,1024)、reuseA=1、blockId=1、pairReverse=1；当前 request/result valid 均为 0，不把寄存 payload 当作本沿新握手或已退休 terminal。RTL wideSteps=12800、steps=102400、sliceMask=255，N0/Wq returned 分别为 786432/819200 字节。与原 Host 诊断计数及窗口位置相容，只建立位置相容性，同因尚未建立。

## 资格边界

本轮仍是 owner 合法 job 的有限 typed-RAM 微场景，未执行 Host PC0 前缀或 iDMA/AXI；预定 ng=160 partial1 首 issue 目标未观测到，完整 job 未完成，五 block 仍为 0/5。official/application/typed-to-RTL 均为 null，historical_host_failure_reproduced 仍为 null。未将本轮推进解释为完整数值正确性或全链成功。

原七件证据 manifest 为 957 字节 / ebfd84179a8b3dd6ee270977a5959bc16aebc1d83c521a562afb2f65276c54cf。原完整日志、生成和编译缓存、工作树、数组及二进制保留在私有证据中。公开仅为固定安全事实和内容身份；摘要制作只读原件，无新测试或 native 执行。正式 actual 独审身份见下，原 FAIL 与具体首写未知边界保持。

## 正式 actual 独审与固定类别定义

review_owner_driver_relink_actual_20261020T0014：MANIFEST.json 770 B / 1e829f2d6553cc0f1b6fe0223851325767e8c7af5de934154ef554eafe0a8be2；SUMMARY.md 8002 B / 05bc84539e07589dbb3f216de953d32e64b9ed3f29b0161485be07eb51292953。verdict 为 ACCEPT_ACTUAL_OWNER_V3_RELINK_NATURAL_ZERO_SETTLED_NUMERICAL_STATUS_FAILURE_ONLY。

固定 Protocol.scala 为 3123 B / 5c94def481dede0195f989608c1827ded32f2d83c752617945695f7d82f64783，定义 Status.Numerical=8、Memory=3、Protocol=7。因此已观测 Dense status=8 归入 Numerical 类别；具体首写分支、操作数及上游原因仍 UNKNOWN，不能据类别命名补出故障因果。

独审核验当前 53 项工作树、7 证据、42 caller 成员、28 core 成员、7 fixture、12 复用输入、338 原生成输入，以及完整 N0/Wq 和新 ELF/.d/archive 关联。39 系统依赖沿已审 SOURCE 资格，本次未重新 hash，也未声称重新核验全部旧 compiled tree。运行失败后的 success-only caller postflight 未执行；独立终态读验不能倒填该阶段。v2 只绑定正式审身份及固定 status 定义，原数值和资格边界不变。
