# LOCAL_DATA R2 启动提案（TEMP，未激活）

原 run40856253077 的 admission gate blanket 拒绝已存在编译/依赖产物，具体文件 UNKNOWN。源码修复 9bdb75d406d2a4da810420a4efe81a54fdb9df7e 仅严格验证并 pin 已知 native dependency 规则及补失败摘要；未执行 archive/link 或数值。

本提案只新建独立 R2 workflow/guard/test 与原已批准 203B launch 的只读 fixture。新 path `ci_launch/fixed_build_local_data_r2_20261029_once.json`，schema `BUILD_ONLY_LOCAL_DATA_R2_ONE_SHOT_V1`，nonce `fixed_build_local_data_r2_20261029_once`。profile 原样保持 `FIXED4096_VECTOR32_BUILD_ONLY_LOCAL_DATA`，fixture 实测 hash 494218b6…；不使用全局版本/数字替换。原 workflow/source/失败身份保留不覆盖。

执行仍同一 bootstrap、原350分钟/资源上限、完整4096/Vector32、同一驱动与算术；只有一次 ≤64KiB summary 上传。无 binary/SV 上传、cache、API下载资格，无DUT数值执行。公共七文件上传仍未获准。源码发布不含启动文件，必须另外批准实际 source SHA 绑定的唯一新增 launch commit；不自动重试旧 run。完整五块 M128 数值仍0/5。
