# 固定本地五工具调用方 SOURCE adapter

本片仅接合已发布 bootstrap v2、独立本地只读 trust profile 与原 ci_toolchain。没有执行真实工具、复制真实工具、构建、Host或网络。source_entry 只核源；真正 prepare/bind/run 调用仍是独立实际动作，本文不授执行。

## 固定接口

- checked_inputs：same-buffer 原 binding 与显式 profile，核精确关联pin及当前只读系统身份；bootstrap/observer/profile三个代码身份固定。
- prepare：原 prepare_tools 单函数零逻辑编辑投影，仅在私有namespace注入已审本地 native checker。未来经批准调用时会真实复制68份数据（仅五工具0700），没有 native 执行。
- bind：只接受已存在且原 stage/result 验证通过的本次数据与私有工具副本。核stage69、tools68、固定byte/SHA/mode/single-link、七系统调用与独立profile；返回私有原 ci_toolchain 实例及projection证明。不会自动创建stage、复制包、获取源码或启动工具。
- 返回的run仍要求独立fresh工作根，必须与dependency work和repo分离；原callback拥有6600s共享绝对deadline、单CPU、阶段限制、WNOWAIT/four-observer、退出与cleanup。

## 有限差分

1. 原 qualify_tools 的首argv单锚改为 LOCAL_TOOLS[tool]，并将“official-image”来源文字单锚改为固定官方Debian包+本地已绑定身份。五version和五generation模式/输出断言保持原样。
2. 原run内CPPFLAGS_AFTER的flex lookup单锚改为真实private invocation key；原header witness读取同一flex真实路径。
3. 私有实例的 host_identities 返回原七系统键加五真实私有绝对键，禁止用/usr/bin五工具假别名。原unchanged_tools仍在每阶段前后运行，适配器额外逐次核原stage、全部68副本、系统/profile与源码。
4. environment保留原CI或micro的HOME/TMPDIR与Verilator字段，注入有限私有PATH/AUTOCONF/AUTOM4TE/M4/LEX/YACC及stage cfg/perllibdir/pkgdatadir。没有LD_LIBRARY_PATH修复或系统五工具fallback。
5. build_commands只改autoconf首argv和configure中的LEX/YACC，保原gcc/g++/ar/perl/python3/make以及-j1。
6. checked_phase薄包装在原监督callback前拒/usr/bin五工具首argv、原系统LEX/YACC参数、任何偏离生成环境的输入；再原样调用原checked_phase前后校验与有限日志/树验收。

函数投影都有单锚计数及逆替换证明。原473树、唯一seqnum补丁、源获取/header来源、生成验证、资源、原8GiB/3GiB准入、4/6GiB AS及6600s预算均未修改。首片本地profile有独立SOURCE审查，不能把其静态通过当native ABI或工具版本资格。

## 冷测

普通/-O和搬迁普通/-O各7组；入口普通/-O各5项，共38组。真实68小合成数据副本、原10个version/generation模式的合成callbacks均经过适配，核实际私有argv、准确来源scope；删/换private键、系统别名冒充、env/首argv回退、前后漂移和错误binding/profile全部前拒或后验拒。审计hook禁止network/native；这些不是真实工具资格化。

下一单次低资源工具资格须明确接收父已获取原五包的固定byte证据，不能倒填成旧下载阶段的WNOWAIT cleanup。预置包接收阶段、stage接合与资格执行合同另列，Host仍未启动。

## 本次安全发布投影与审查状态

- 状态：TEMP_SOURCE；独立 SOURCE 审查已闭合为 SOURCE_GO_FINITE_PRIVATE_TOOLCHAIN_CALLER_ADAPTER_ONLY。最终发布投影只更新本文和中文计划的审查身份，生产源码保持冻结原字节。
- 来源固定为 candidate_local_toolchain_caller_source_v1_20261019T1559，源 MANIFEST 5223 B / SHA256 3bda09357935defbded3c6b3cf3a226739fd92fda7a05251f38f7f4ba5ee175c。公开九份声明的安全文本，其中八份原字节，本文仅追加状态与范围说明。
- 38 项是作者保存的合成冷测记录（主冷测 7×4、入口守门 5×2）。独立审查另在搬迁后执行主冷测 7+7 与入口 5+5；每个主冷测运行含原十个工具探针的合成 callback，不属于真实 version/generation 执行，也不与作者 38 项合计。COLD_RESULT 的 PENDING 字样保留为原件形成时状态，正式审查身份如下。
- 公开代码和 SOURCE_PINS 的固定系统程序路径属于接口约束；本次不发布实际私有调用映射、绑定或 profile 内容、机器库存、日志、搬迁副本。依赖已发布的 local_binding_observer 与 local_dependency_bootstrap，不复制这些底层来源。
- 原 ci_toolchain 的成功字段或资格字样仍属于未来执行合同。本次 native 资格、工具构建、Host、N0 数值均 NOT_EXECUTED；真实调用须另行受原监督与预算约束。本片无 workflow 变更，不触发新的 Host/native 作业。

正式 SOURCE 审查：review_local_toolchain_caller_source_20261019T1606。MANIFEST.json：2890 B / SHA256 d97924a79077d65691e90f0530e908e5e1925d1c395479e06d39e88e40acde6f；SUMMARY.json：3685 B / SHA256 66f7c95408030ed958b189f81a4c00281a1c0211ac9559da1bbfe4a1df3b033a。审查只接受固定 caller adapter 的有限源码组合；预置包接收、真实 stage/prepare、工具资格化的监督入口仍须独立审查与执行准入，不能从本片推定已完成。
