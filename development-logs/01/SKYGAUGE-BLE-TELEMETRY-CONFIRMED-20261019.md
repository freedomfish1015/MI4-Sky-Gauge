# 重要更正：SkyGauge 104 的 BLE 遥测已实测接通

## 当前状态优先于此前诊断

用户在三机同场测试后反馈“小米显示已遥测”。只读检查现有连接证实，这不是假状态：主机 `[BT-ADDRESS]` 当前开放 1FF8，手机已经订阅并持续收到有效 CAN 通道通知。

**此前未发现 1FF8，不能推出该 104 固件永久不支持 BLE 遥测。不要继续依据旧记录只走无线固件逆向，更不要宣称必须修改 SkyGauge 固件。** 本轮没有刷写或更改 SkyGauge，没有修改仪表运行代码，没有重启手机服务，也未改变 BLE 配置。为何此前服务缺失、此时出现尚未确认，不能无证据归因于某个开关或缓存。

## 当前主机只读身份

复用已连接 BlueZ GATT 对象，读取 1FFA identity（没有另开 BleakClient、没有断开仪表连接）：

- board Waveshare ESP32-S3-Touch-LCD-1.85
- variant obd_brz_gauge / ST77916 / 360x360 / 16bpp
- flash16MB、PSRAM8MB、OTA slots2
- build_tag `main-104-9c3fa1b27e9d`，branch main，count104

仍是此前记录的版本。1FF8 characteristic read/notify；`Notifying=true`。

## 实测接收

手机应用诊断日志从北京时间 20:53:15 起记录 1FF8 服务并选择 skygauge 协议，随后持续记录 `skygauge_rx`。旧日志每5秒采样常只显示车速，不能据此认定只有一个通道。

`probe_existing_sky_notifications.py` 只对既有 D-Bus 通知加信号监听，不 Connect、不 StartNotify、不 StopNotify、不发 GATT 写或 OTA/ELM/控制命令；观察8秒结果：

```json
{"duration_s":8,"channels":{"0xf102":73,"0xf103":73,"0xf104":73},"latest":{"obd.speed":0,"obd.coolant_temp":-40,"obd.intake_temp":-40},"malformed":0}
```

三个通道各约9.1Hz，总计219条通知；无格式错误。未收到转速、油温、电压等其它通道。这是主机未接OBD时的实测值，不是实车有效数据；两个-40不能当作当前真实水温/进气温度。

UI 的“已连接 · SkyGauge 遥测”来自 `run_skygauge`：最近3秒内解码到已知 CAN 通道才显示，不是仅靠连接建立。不过它不等于“车辆OBD已连接”，也不等于所有字段齐全。

## 通道区别与后续优先级

- BLE 遥测：本轮已实测接通，使用原有手机只读兼容路径。
- ESP-NOW：三机正对照中仍为0包，未修好。这与 BLE 成功不矛盾。
- 主机/从表固件未刷写。小米仍使用 stock WCNSS 和磁盘原 wcn36xx；不应为已有可用BLE通道再冒险持久部署实验无线固件。

下一步优先实车：主机连接 Vgate OBD，小米保持 SkyGauge 模式，核验转速/车速/温度/电压等真实变化及现有轮转日志，而不是先假造数值或把ESP-NOW写成成功。当前两块ESP均连接电脑供电，不要求马上下楼。

拔掉小米USB会触发既有20秒关机倒计时；若移动实车测试需要保持运行，用户须点击保持开机或接外部电源。保留已有日志轮转功能，测试后可取回 bluetooth.jsonl 及 .1–.4。
