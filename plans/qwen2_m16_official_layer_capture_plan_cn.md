# M16 官方完整单层参考源码计划

候选：[qwen2_m16_official_layer_capture](../candidates/qwen2_m16_official_layer_capture/README.md)。本批仅源码、严格pins和纯mock证据，公共数值入口固定关闭，不修改旧生产路径/参考/pins。

已完成：原完整官方类与配置对应、raw13/12参数绑定实现、29原值hooks/trace、finite/shape/别名门及纯软件独审。发布仅适配测试路径，执行源码原hash不变。

下一步：独立正常import冷门闭合；新一次性参考worker/source-runtime-input manifest及资源独审；获准后一次真正M16参考生成，终态后比较。不能用旧M128切片、DUT自比或C++辅助参考代替。官方32768与项目旧256配方不得暗混。

保留：无实际forward/新参考、无DUT/RTL、无无干扰数值证据、无M128资格；4096MAC整block分母和legacyPV63.57%上界不改，不声称80/90%。
