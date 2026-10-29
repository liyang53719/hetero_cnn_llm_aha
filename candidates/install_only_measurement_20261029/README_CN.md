# 历史 INSTALL_ONLY 采样摘要

仅发布路径无关的数值/hash摘要与其提取器；不包含runtime、wheel、权重、输入/reference、binary、SV或原始私有路径。`export_install_measurement.py --input RETAINED_MEASUREMENT.json --output NEW_SUMMARY.json` 只能读取原SHA为5d576a08735254a983db7ab31b77d686d2d1456dbdaa4fdf2670f046a5789179的历史测量，不是安装入口，也不宣称仅凭公开摘要可重建原runtime或证明新机器准入。

实际执行binding619bf929…、runner810a3edb…；原source proposal manifest a372db17ff2f1f8b0228581e87d3f901aaa6f2add6b8fd0b8c5eab335eb9e3cf，后续R2只加锁内4GiB MemAvailable/8GiB disk gate和全日志父树监控。原版本/安装参数保留；Qwen2增加owned TMPDIR，Qwen35内部不自建session，由外层严格监督回收。

四阶段cache/Qwen2/08B/35B全部native0；总阶段wall152.473s，最终inode去重3506537745B。**最大process采样间隔12.176789747s、census12.123572151s，观测峰值不是连续峰值或数学上界**。没有Torch/reference/DUT/EDA，没有权重下载或删除旧证据。五profile全链数值仍0/5；三runtime共根安装不等于五份逐profile复制策略可准入。

3项提取器测试normal/-O通过；其中positive使用真实保留测量、negative拒绝哈希漂移、输出检查禁止路径/PID/argv并限制16KiB。未重跑任何安装或构建。
