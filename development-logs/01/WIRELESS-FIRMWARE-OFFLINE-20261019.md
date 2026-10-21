# 小米无线固件离线分析（候选补丁，未加载）

用户已同意进入小米无线固件研究阶段；助手承诺先备份、离线分析，替换前说明具体方案。本轮没有替换或重新启动无线固件，不改SkyGauge。

## 原始备份

- 手机root独立备份 `/root/mi4-wireless-backup-20261019-MbWXow/original-wireless.tar.gz`。
- 手机用户目录 `/home/umeko/desktop-offline/mi4-wireless-original-20261019.tar.gz`。
- 电脑 `[LOCAL-PATH]`。
- 归档SHA256 `4ff232a5e7467b730a0d8ee013193c66467b1504b7e3daefcbbc25412c2dcea8`，USB下载已校验。
- 包含9个wcnss ELF/分段文件、根目录和wlan/prima下所有相关NV/INI/DAT、原wcn36xx.ko；SHA256SUMS 17项全部通过。
- 离线原件 `[LOCAL-PATH]`，不修改。
- 实际WCNSS为`/sys/class/remoteproc/remoteproc1`，name fb204000.remoteproc，firmware wcnss.mdt；共享Wi-Fi/Bluetooth。**编号会变化，操作前须按name匹配，不硬编码remoteproc1**。其它协处理器：modem和ADSP，禁止误操作。

## ELF及校验结构

ELF32 little-endian ARM，入口0x0d201a70，10个program headers，无section表。
主代码段b06文件长度3600260，VMA0x0d229000，原SHA256 `25553bc6350579376d89e48f3c81719d5568e99d3d78f55089417e074de0551b`。
b01长度360：40字节头 + 10×32字节SHA256。第1槽是哈希段自身，不是普通段，不应递归计算；inspect脚本显示它hash_match=False不代表原备份损坏。其它存在的文件段均与各槽匹配。
mdt长度732=372字节ELF头/PHDR + 完整360字节b01副本。头声明signature_size=0、cert_chain_size=0，但不能由此保证平台接受改过的固件。

## 离线定位证据与候选假设

b06含Thumb与ARM混合指令，不能全程以ARM模式解释。
字符串`halRxp_setSystemRxpFilterMode`，地址0x0d4b324f，文字指针位于0x0d2c1778；函数入口0x0d2c1448。
函数调用0x0d2c0df8获取模式掩码，最终调用0x0d2c0dbc写入帧过滤寄存器。
0x0d2c0df8中内部mode1分支的日志是`RXP filter to SCAN mode`，从指针0x0d5311c0读取掩码：low=0xc77ffedf，high=0x0000ffff。
该low低16位只有bit5和bit8为0，与管理帧Probe Response subtype5 / Beacon subtype8相符，和实测只收到Beacon一致。**这是逆向推断，不是正式硬件文档确认**。
候选只清除bit13（Action subtype13）：low 0xc77ffedf→0xc77fdedf。b06偏移0x3081c0，实际只改偏移0x3081c1一个字节0xfe→0xde，不改指令、不启用发送、不改NV校准。
同步更新b01第6槽（偏移232..263）与mdt嵌入副本。其它分段保持原样。

## 候选产物与验证

- 构建脚本 `build_wireless_action_candidate.py`，只离线生成新目录，存在目录拒绝覆盖，原文件SHA/ELF布局/旧掩码均严格验证。
- 候选目录 `wireless-fw-analysis-20261019/candidate-action-rx`，含9个固件文件和candidate-report.json。
- 新b06 SHA `6c184d00f9167c4aa8bdc98518acf3ae461306490f869ff57fb55d108f088cbe`。
- 新b01 SHA `78068c2fb3056699aeb0adfa2b52402bf9526440d4cb0ab3bb9a3aa50d4b1e92`。
- 新mdt SHA `e269f17d4cc466a2309f56cb6a048c5d68b8789f699559bdd5b8000a07caeb66`。
- test_wireless_action_candidate.py检查单字节单bit差异、哈希槽范围、MDT一致性、其它段不变、原件不变、不覆盖已有候选。

## 后续实机测试方案（尚未执行）

下一步若获确认：在/lib/firmware的独立测试子目录放候选完整分段，绝不覆盖原wcnss.*；通过WCNSS remoteproc临时选择替代mdt，测试后切回原firmware名称。不改boot、不改开机默认、不改ADSP/modem或NV。
必须先按remoteproc name识别WCNSS、确认串口USB可用、记录原firmware名、准备独立超时回退脚本。停止使用WCNSS的蓝牙和Wi-Fi客户端，随后测试会中断Wi-Fi/Bluetooth；若无线处理器无法正常启动，需经USB回退原固件，必要时重启手机。
当前用户界面从机模式只完成BLE绑定；即使Action帧能收，也还要核验源MAC严格匹配、数据版本/长度、过期失效、模式切换清理与从机presence，不能把接收计数>0等同于完整交付。
