# M17/M32 实际 Public transport 分块边界验证（准备中）

单独 typed profile 接受M17/M32的独立Attention job，使用原始 OfficialAttentionOwner、ProfiledMatrixService、PublicKvTransport、ParentLoan和同一个Banks。仅添加显式selector分支，原默认/M16完整程序不改变。复用已验证packed ELF，不编译、不下载。

成功case比较所有score/output与原始owner AST/Fraction参考；所有enabled cell由native Matrix计算。query16/key16的第二panel重载时故意在实际raw response已可见时保持ACK七条边（不计响应等待延迟），要求PV group/tag/index16不变。两个独立M17 fault case分别在此处abort、随后返回匹配DDR错误，检查债务清空和query16不发布。

拟议预算：M17成功+两个fault共90秒内部/95秒外部；成功后另一个M32成功case同预算。每个case只有一个真正多行job，不循环M1。已完成4项 normal/-O 冷测试（1.999/2.202秒）；进行中：独立复审。实际数值仍未执行，执行须复审与授权。

冷测试：python -m unittest candidates.qwen2_resident_matrix.attention_packed_tiled_transport.test_prepare -q，另用python -O重复。

保留显式384B panel资源；软件tick不代表硬件周期。全块21事件、完整M128、RTL和80/90%利用率均未由本fixture证明。
