# 同 job consumer 最小生命周期接线（尚未实际 DUT）
保持所有原数值比较、load_binding、P0 覆盖、ABI 与本地 producer 证明函数 AST 完全相同。仅 execute/main 生命周期与显式 wall 校准接线改变。

实际入口：在原严格 supervisor 中，以此 consumer 作为其 session/group leader，传原全部参数并加 `--strict-outer-supervised`。调用方必须保持所有 stage/output/输入 watched roots 与 pins、实际完整 group cleanup 和日志 EOF 后才能结束 owner lease；flag/session 检查本身不能证明监督器存在。DUT 不再创建 nested session/group。execute finally 仅清理其 leader，剩余后代必须由实际 outer 清理。

可选 `--calibration-wall-seconds N`：只复制原 limits 并缩小执行 wall，1<=N<=原20000；原 bundle、128 token 刺激、max_active_cycles、CPU/AS/file、全部算法不变。每个 profile 必须真实登记，剩余 job 预算由 controller 准入。校准 timeout/运行失败仍 INCOMPLETE，不降低观测或冒完成。原 main 始终 exit2；controller 不能将此当 numerical PASS，也不能盲视为基础设施失败而丢失已写诊断。

需要本目录8个原 sibling：local_build_proof.py、runtime_abi.py、observation_contract.py、consumption_proof.py、driver_dependency_proof.py、correct_observation_policy.py、LOCKED_SOURCE_CONTRACT.json、attach_bundle.py（后者给 connect_bundle 使用）；全部原字节复制。旧 run_compare.py 未修改。实际 connect_bundle 可继续用原 consumer 校验，但最终生成 argv 应显式选择此新 consumer 并加入 outer/calibration 参数，不能覆盖同名原源码。

测试：test_consumer_owned.py --baseline 已发布原run_compare.py，normal/-O 各7个测试实际通过。涵盖全部原函数 AST（排除main/execute）、原limits不变、非法wall、outer声明/leader、mock正常/timeout无setsid/killpg、永久exit2。没有执行真实 ELF、loader、Torch或DUT；mock不能替代真实 outer ownership 测试。

本层是 CHISEL_EMITTED_SV_NUMERICAL_BACKEND；不是原生 Chisel 解释器，不是最终冻结 RTL 数值通过。P0 gate/up 内部值仍 UNOBSERVED，原同分契约仍未获批准。原 producer 四件硬编码pin保持不变，应从新上层controller调用原 BUILD_ONLY。
