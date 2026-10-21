# 三机同场正向对照

> 后续重要进展：手机已实测收到原版主机1FF8 BLE遥测，详见 `SKYGAUGE-BLE-TELEMETRY-CONFIRMED-20261019.md`。本文件中ESP-NOW仍失败的结论不能用来否定BLE路径已可用。

## 设备与授权范围

用户拿来原版从表，三台均连接电脑，要求开始测试。只读识别两块 ESP32 表，不刷写、不改 NVS/模式/主从固件。小米测试继续使用已经验证回退的隔离候选。

- COM10: Xiaomi Linux，USB VID18D1/PID0100。
- COM8: SkyGauge MASTER，BLE MAC [BT-ADDRESS]，ESP-NOW 主机。
- COM5: 原版 SLAVE，Wi-Fi STA MAC [BT-ADDRESS]。

首次打开 COM5/COM8 串口时，即使 SerialPort DtrEnable=false/RtsEnable=false，两块 ESP 都输出 `rst:0x15 (USB_UART_CHIP_RESET)` 并正常重启。没有发送串口命令或刷写，但打开串口本身存在复位副作用，已向用户说明；不要反复重开串口当作无影响操作。

COM8 启动日志：Device role MASTER、ESP-NOW started early (Master mode)、ESP-NOW already started earlier，BLE广告 SkyGauge-7730。
COM5 启动日志：Device role SLAVE，`ESP-NOW SLAVE up (listening ch1, presence 500ms)`。

用户在两块重启后明确回复原版从表“已连接”。因此已经有同场的原版接收端正向对照，而不再仅依赖源码认为主机应广播。尚未获得“联动测试两表实时同步”的用户反馈，已发出可选测试问题。

## 小米同场复测

临时服务 `mi4-wcn-positive-control`，profile=route，WCN_TRIAL_DIAGNOSTIC=1。
复用 `mi4-action-route-rx-20261019` 与只读诊断 module；无新固件补丁。

- 20:52:39–20:52:59，信道1，20秒。
- 用户态 921 帧全部Beacon。
- 驱动 rx_total=929、rx_beacon=929、rx_action=0、rx_drop=0。
- ESP-NOW / SkyGauge包仍为0。
- 实际寄存器：fb080800=0900030f、8f0=ffffffff、8f4=c77fdedf、914=00000e00、920=0008f200、934=0008f200。
- 20:53:02 自动恢复 wcnss.mdt running，Bluetooth/kiosk active。

这是“原版从表已连接、手机仍收不到”的更强对照，将调查重点进一步指向小米接收链路。不能仅据此证明是具体哪个硬件/固件过滤步骤，也不能宣称手机ESP-NOW已经修复。

## 后续

不需要为这一步先下楼连接汽车OBD。可用主机的联动/多表测试确认原版从表是否跟随实时转速；该验证不需要真实车辆。保持不改SkyGauge的约束。

继续调查小米Action后续过滤、地址/BSS关联与上送条件。不得把普通BLE配对成功、原版从表连接或HAL成功ACK冒充小米收到遥测。
