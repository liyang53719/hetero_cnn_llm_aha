# 原4096 Host真实接口闭包（TEMP）

原分层任务确实执行，38.04秒exit2，子Verilator丢失-f内的include/define，非内存失败。只把原idma.f现有8个include和4个define显式传入命令行，实际子参数已核。Top RTL/硬件资源/算术未修改，无stub。原失败日志保留。

本次session8474，5GiB/600秒预算，310.80秒exit0。生成全部真实Host C++接口，Top SV哈希保持。随后新Python参考只读bench用真实头完成g++ -fsyntax-only；首次缺标准svdpi.h，通过加入官方include/vltstd解决。

PASS精确范围：Verilator --cc生成和bench语法。未编译/链接C++模型、未运行数值仿真，完整block硬件仍0/5；原head4 FAIL不变。生成C++/SV/头文件留本地，不进入源码包。
