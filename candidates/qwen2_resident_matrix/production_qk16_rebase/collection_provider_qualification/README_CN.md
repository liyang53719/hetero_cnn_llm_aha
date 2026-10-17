# 共命名空间与真实 endpoint lint 检查点

共同命名空间 A/B1 已实际通过：95源/557+4类，CHIRRTL39,466,374B；共同SV69,711,072B SHA53f4f4cb…，56唯一定义、原Bench76端口、四FMA端口、Bench内8endpoint/8clock/1iDMA库存通过。collection只是生成根，资格top始终Bench或明确分层endpoint。

完整Bench真实provider lint仍FAIL：AS4GiB下bad_alloc，481警告保留，未通过。单endpoint原32cluster×16lane=512、seed1与共同FMA分层lint实际PASS，零warning；不能传递成4096Bench或数值PASS。原endpoint v1无尺寸参数产生唯一warning的FAIL也保留，v2仅改1'b1单token，无warning屏蔽。SAFE_HISTORY是安全投影，不是原receipt字节；保留各原receipt/hash、相对cleanup、leader采样与规范化argv，无PID/boot/session原proof。未打包大IR/SV/classes/jars。

## 已包含原冻结操作源码
- structure/：共同生成类+A，只新增collection源，原557类由精确闭包兼容证据准入。完整source95与class pins在文件内。
- sv/：固定新A IR→共同SV，原180/150与128MiB输出门；完整源inventory checker。
- endpoint/：固定14组件文件+共同SV，默认timescale1ns/1ps、1bit seed参数、210/180及AS4GiB，警告默认fatal。保留1053完整source/header/tool pins；不偷偷改固定依赖。

各MANIFEST保留原运行源码身份。原PLAN建议路径属于历史重放布局，执行仍需对应显式输入且fresh输出；没有在安装时自动运行Java/EDA。structure原test_cold部分fixture依赖历史大IR，仅作为原测试源码保留，不能在无IR环境冒称全部冷测已重放。

## 便携只读命令
python -B verify_existing.py
python -B sv/test_cold.py
python -O -B sv/test_cold.py
python -B endpoint/test_cold.py
python -O -B endpoint/test_cold.py
python -B verify_existing.py --ir "$EXACT_COLLECTION_IR" --sv "$EXACT_COLLECTION_SV"

无大生成物时仍可检查冻结源码与19+19、8+8冷测试；最后命令只在消费者已有精确hash原产物时可声称实际离线重放。30秒内，无Java/native/EDA子进程。

## 公共重建链及边界
1. 沿已发布production_qk16_rebase/classcompile/README_PORTABLE_CN.md生产/QK donor/HardFloat公开源链重建92源。
2. 相邻silu_feedback_fix/reproduce_sources.py进行单表达式修复并include-bench得到固定94源；本包structure/source新增唯一collection源。95源均有hash。原557实际类可用公开fix兼容入口验证；从公共源重编时必须执行独立有界完整class资格，不能把新class/receipt假称原历史字节。
3. 使用structure/run_structure.py所列显式source-root/base-classes/offline/cache/java/out与固定工具，生成共同新IR；该历史launcher固定原557兼容证据，新的公共重编receipt需单独受审绑定，不热改本历史pins。没有要求私有云cache作为源的唯一来源。
4. sv/run_sv.py显式ir/receipt/firtool/out；工具可由已发布fma_components便携固定下载recipe获得。新receipt身份不同需新受审候选，本包保留可复核原输入身份，不自动接受任意替换。
5. provider闭包沿已发布iDMA source-export公开锁和七依赖重建；原Matrix12叶、tc_clk与共同SV组合，剔除仅四独立FMA。endpoint/COMPOSITION与INPUT_PINS给精确内容。完整Bench后续仍需警告与资源闭合，不以分层PASS替代。

后续动态必须消费同一共同SV的Verilator harness，避免Chiseltest独立重新发射造成helper命名冲突。此包无动态/数值/性能结果。发布状态以实际提交为准，本文件不宣称已推送。
