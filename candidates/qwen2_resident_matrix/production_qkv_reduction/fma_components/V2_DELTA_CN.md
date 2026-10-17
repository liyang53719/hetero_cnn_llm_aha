# v2 checker收紧

只改SV module inventory词法：去掉注释后遍历所有module/endmodule token，不依赖行首；检查完整声明、非嵌套/配对、定义唯一，拒未知声明形式。新增缩进、同一行重复和注释伪声明反例。生产源/发射器/runner/预算工具不变，8+8冷测，无Java/firtool运行。
组件目录精确四个非symlink普通SV文件，任何子目录/额外文件均拒绝，不能靠根glob漏掉额外SV。
