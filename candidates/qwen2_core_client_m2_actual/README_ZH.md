# 真实 normal_m2：原 SV Core/PackedClient 限定行为 PASS

本次固定M2真正执行原生成SV的Verilator模型，使用已公开M2 harness和脚本Matrix/memory。**实际时钟行为PASS**，不只是源码/编译/mock；source+single-TU build已经先前发布，此包只追加本次实际证据/当前runtime门，不含ELF、raw log/events/packet或未执行M3。

## 直接观测与被动断言分开

- **12143 body +3 reset =12146 rising edges**；独审一次完整日志解析，16,619事件条件，828 OBS（Scan384/Fold384/Scale24/Retire36），24heads内phase连续，token1的两次retire为连续边沿。
- 36个有效scoreWrite均+0；token1第二retire的pre-edge max实际为+0，覆盖12heads；其余816 max为-Inf。这是比M1增加的特定观测，**不是full max/softmax tensor验收**。
- 四请求口payload rechecks为2/234/86/47，总369，可能跨口重叠且含release边沿，非369唯一stall周期。
- memory960、PV288完整被动字段断言及消耗计数通过：依据冻结源、真实编入表、同ELF执行身份、终态计数/exit0链。**没有外部rawmemory/PV逐包trace可供独立重放**；具体源断言与直接OBS不同层级。PV A0为1或1/2且其余操作数0；外部FMA结果仍脚本化。
- QK192 steps、24 groups/results/dones、owner1、12288 output bytes；owner状态/reset与8步稳定/3步quiet检查不等于每个owner payload字段完整预期值证明。

## 当前runtime补门，不回填旧证据

本次184 declared+2 self=186 pins、63absence、6aliases；2,233身份检查与原owner清理闭环。parent runtime原80+新增47=127：42正常.pyc、3 stdlib source、2locale/gconv身份；root在Popen前及终态后保存42cache SHA+11额外absence，记录逐字相同。实际parent LANG/LC_ALL/LC_CTYPE均C.UTF-8；child的LANG/LC_ALL=C为另一环境，不能混用。

`-B`只禁写不禁读；42缓存与固定源码代码对象一致是当前门依据，不是签名Python发行证明、任意条件import/dlopen或连续全机隔离。**旧M1/旧M2 build的未pin .pyc范围缺口不回填，旧PASS/FAIL均保留**。这里只上传角色/hash，不上传系统pyc、ELF、locale缓存或机器路径。

CPU20.360171047s、outer20.472671524970792s、采样RSS7,651,328B；RSS非连续峰值。host时间不是硬件周期/频率。

## 不能扩大的结论

`828/12143 =6.8187433089%` 仅本case被观测vector-phase占比；其余11315 body edges不证明idle。1824 accounting不是MAC数，没有真实4096-MAC分子/完整block周期分母，不能据此宣告达到或失败90%MAC目标。

j1/第二retire控制实际被观察，但j0/j1活动QK对角值同为0，**不能区分两者数据alias，也不能消除一般索引/W005风险**。只在单packed组内，不跨16→17，不是M3/M17、full128/full29、真实Matrix FMA、完整block、物理DDR/STA/时延/利用率通过。原M1、软件M128观测域及所有历史FAIL/STOP不变，canonical整体任务不置done。

## 最小源码复用

原checker/reference/generator/harness与build证据见精确refs。新增`test_referenced_log_controls.py`只在合成字符串上运行原4项log控制和5项边界控制，**不读真实日志、不执行模型、不作为实际行为证明**：

```
python3 -B candidates/qwen2_core_client_m2_actual/test_referenced_log_controls.py --repo-root .
python3 -B -O candidates/qwen2_core_client_m2_actual/test_referenced_log_controls.py --repo-root .
```

未来其他case/新harness须单独冻结、审核与批准，禁止自动串跑。本次reviewer最终标签纠错仅审查侧，原目标无重跑/修改。
