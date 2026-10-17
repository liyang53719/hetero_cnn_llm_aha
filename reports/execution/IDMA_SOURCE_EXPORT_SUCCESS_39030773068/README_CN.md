# iDMA 固定源包成功证据

唯一本次 run 39030773068 / job 117390605122 / attempt 1 成功；main 0077355800e3040dfdd6d79def697f3ff6456c2c。官方源包已下载并逐文件独立复核，927 manifest 条目通过，另 manifest 自身共 928 文件、33,744,483 字节。源码、锁、生成产物及校验元数据均保留原字节；本小包不收录该 33MB 源树。

原 run 39026847303（条件 UVM include 检查失败）和 39028560366（合法 backtick 被旧检查器拒绝）均保持 FAIL。此前已发布的两失败证据不删除、不改写。微资格 v2 仍总 FAIL，微资格 v3 仍仅微测试 PASS。本次成功限固定 source 生成、物化、预处理闭包及哈希核验，不代表完整 Host 编译、综合或动态数值通过。

## 获取与重建

源 artifact 12099239717，ZIP SHA256 a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce，9,926,876 B；safe artifact 12100621065，ZIP SHA256 63d63333002a2eba08a11c9f7601325c1768ad9dc722c8b36d47837907c97f93。官方 metadata 记录两者分别于 2026-11-16 12:00:15Z / 12:00:17Z 到期（30 天保留）；届时可能不可下载，不是永久归档。

在可用期间从 run 原 artifacts 下载，先核 ZIP digest，拒绝绝对路径、上溯、重复条目、symlink/nonregular，再物化 idma_export。使用该提交 scripts/idma_source_export_20261017/export_source.py 的 verify_export 只读验证官方 COMMITS、Bender.lock、每文件 manifest、SOURCE_CLOSURE 和两精确排除。SHA256SUMS.json 的 SHA256 为 a699b8074b8099e00859d5174c0a5fb6b5a171a28cad30bab8dd96226dc67b19。

过期后的 source-only 重建入口固定为上述 main commit 中 .github/workflows/idma-source-rebuild-20261017.yml 及 scripts/idma_source_export_20261017；18 文件哈希见 REBUILD_SCRIPT_HASHES.json。必须先取得一次新执行授权，使用新的隔离输出和 run 身份，不重跑或覆盖历史 run。不升级官方 iDMA/七依赖/Bender/uv/Verilator pin；工具与发行包 SHA 见 SAFE_IDENTITY.json，八个源码 commit 见 COMMITS.json。Python 使用审定固定 CI 解释器（本次 3.12.3），uv --locked，UV_PYTHON_DOWNLOADS=never。复用原 bootstrap → export --execute → 原 deadline verify → success source upload / always safe summary 的配方和预算，不增加 FMA/Host 编译步骤。

新生成应重新核完整证据；ZIP 封装、runner 路径、工具记录或 .d/预处理输出中的路径可能变化，不能要求新 ZIP 与本次 ZIP 完全相同或自动复用本次 PASS。持久源码和固定输入哈希若变化必须诊断，不能静默接受漂移。

## 真实宏配置与证据边界

实际 294 sources、8 include dirs、312 admitted 输入、309 记录依赖。Verilator 5.032 参数 -E --no-std --relative-includes --MMD，单 compilation unit；初始宏 TARGET_ASIC、TARGET_RTL、TARGET_SYNTHESIS、TARGET_VERILATOR。保留内建 VERILATOR/verilator/verilator3（仅已核已知列表，非穷举）。UVM 不在初始宏集合，唯一词法缺失 uvm_macros.svh 经真实预处理条件处理成功；未添加缺失文件豁免。未来消费者若换 profile 必须另验。

stdout 6,288,028 B、stderr 0 B，stdout/.d 哈希见 VERIFICATION.json。原 stdout、.d、完整身份 proof/主机日志按审定范围没有上传；此小包只能复核记录和各源哈希的一致性，不能重读原输出或重新认证原 cleanup 身份。58 个 stage 摘要均 exit 0/cleanup verified，范围仅 original group 与 observed identities；global_cleanup_verified=false，未声称全局 absence。

源包排除且只排除固定 iDMA target/sim/vcs/jobs、target/sim/vsim/jobs 两条已核 symlink，理由/精确 mode/blob/target hash 见 SOURCE_EXPORT_POLICY.json；最终源树零 symlink。安全元数据不含主机 PID/PGID、boot_id、monotonic cutoff 或原 proof。

审核采用固定可信上游源、严格参数/直接 include 准入与事后依赖检查，非 OS sandbox 或任意恶意宏防护。保留原 900s source+verify、180s stage 工作、32MiB stdout sampled/postcheck、2MiB stderr、64MiB 单文件硬上限及 1GiB 树采样软限；没有将软限宣传为磁盘硬配额。
