# 测试入口与历史测试

推荐 `python3 tools/run_tests.py --full`，其名单是当前运行构建的离线回归，188项、2项明确的条件跳过；另有Windows installer/test.ps1的20项测试。

历史阶段的额外测试保留在development-logs/historical-tests，可能依赖当时的文件布局/功能或未再分发的样本，供创作者研究，不自动当成当前验收。真实SDL手势测试需要显式选择；真实aboot样本测试仅接受维护者自行提供的只读样本，不随公共仓库分发。

所有自动测试必须使用Mock/临时目录/内存中的块设备模拟，不执行真实flash/erase、不启动设备服务、不查询实车。新增公开工具/协议请加合成输入回归。
