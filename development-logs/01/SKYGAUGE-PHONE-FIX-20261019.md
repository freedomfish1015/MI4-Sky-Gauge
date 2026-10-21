# 小米手机端适配原版 SkyGauge 104 修复

## 已部署内容

只更新手机 `/home/umeko/desktop-offline/gauge_ble_protocol.py` 和 `gauge_sky_slave.py`，不改主机/从表固件，不改 boot/WCNSS/NV，不改主题/IMU/GPS/电量/背光/音频或用户 settings.json。

核验版本 `main-104-9c3fa1b27e9d`，原版源码固定提交：

- https://github.com/steveEcode/obd_brz_gauge/blob/9c3fa1b27e9ddd3114ca29386615dd7406aa470e/main/bsp_obd_dsp/racechrono_ble_diy.c
- https://github.com/steveEcode/obd_brz_gauge/blob/9c3fa1b27e9ddd3114ca29386615dd7406aa470e/main/export_path/screens/ui_ScreenPageRpmWarn.c

### 1. 原协议订阅与字段

严格在服务1FF8选0001 notify、0002 write（可选）。其它服务的相同0002，包括OTA，一律不作为遥测控制通道。ELM的tx字段保持None，避免当作UART。

通知仍是LE32虚拟CAN PID + LE32有符号原始数值。九个PID F101..F109对应转速、车速、水温、进气温、油温、负荷、节气门、电压、刹车温。负荷/节气门/刹车温×0.1，电压×0.001，其余×1。

连接后订阅notify，再只向1FF8/0002写 `01 00 64`：原版cmd1允许所有有效字段、100ms周期（周期为大端）。这是当前会话的遥测过滤/周期设置，不写固件、OTA、NVS，不是造数指令。

按源固件有效性处理：零转速不会被当成有效帧；未知/无效/损坏帧不刷新字段，-40°C按源协议保留，不能仅凭此值判断OBD连接。速度0合法。未收到的转速保持缺失，不强制补0。

### 2. 每字段过期及诚实状态

独立3秒TTL，持续收到温度不保活旧转速；断开/取消立即清空发布值。状态 `BLE遥测 · n/9项` 只表示当前收到的已知有效字段数量，不宣称车辆已连OBD，更不宣称ESP-NOW接通。

每5秒新增 `skygauge_summary`，包含总包数、格式错误、各字段计数、当前有效值和transport=BLE、vehicle_link=unknown。不再因日志采样恰好总是车速而漏看其它通道。

### 3. 实测修复的重连故障

首次重载后Bleak报 `Device with address ... was not found`，但 `bluetoothctl info` 显示该精确MAC Connected=yes、服务1FF8存在。已读手机安装的Bleak源：仅传地址字符串会先scan；已连接主机可能停止广播，导致失败。

现通过系统D-Bus GetManagedObjects只读找到 **地址严格匹配且Connected=true** 的设备，构造包含实际BlueZ path/props的BLEDevice，复用现有连接对象。无匹配则回落正常扫描。绝不复用其它OBD或从表设备。

21:04:41 实机日志 `skygauge_reuse_connected`，21:04:42 发现1FF8、协议选定、订阅成功，随即收到持续数据。没有重启/重刷主机。

仅配对服务的分支不再永远停住：关闭配对BLE后15秒抛出可识别“BLE遥测未开放，稍后重新发现”，交由现有worker按Unsupported协议约20秒退避后重试。

## 验证与备份

- 主机未连接汽车OBD时当前仍3个通道：速度0、水温-40、进气温-40，每项约9Hz；不应宣称其它通道已经真实验证。
- 手机关键协议/模式最终16项通过；桌面相关最终回归76项通过（2跳过）。
- 手机原版两文件备份：`/home/umeko/desktop-offline/ble-stock104-before-cn6OW3`。
- 第二轮中间版备份：`/home/umeko/desktop-offline/ble-stock104-before-zLjbXL`。
- 当前协议模块SHA256 `453859391cf722e0603082ff235083144c8d11fa220332146bf8eff1d4fedc38`。
- 当前从机模块SHA256 `c849b02f88e32d8b0eeb34a6998a7e955e21fabbd94f12cda303a62c945a3c78`。
- 当前部署包SHA256 `da2417bdbbe486dcfb06cbbac5864f64b95a60183aa0416cbbaba0a7d1aa448e`。
- 部署脚本 `install_sky_ble_stock104.sh` 包含当前已知前版本哈希前置检查及失败回退；不能无脑再次执行，下一次要核对当前哈希和新版包。

注意：首轮手机单测进程PID2459曾写入诊断日志，里面RPM2300/2000是mock测试，不是主机发来的数据，已追加diagnostic_annotation标记。后续部署已用独立 `OBD_BLE_LOG_DIR=stage/test-diagnostics` 隔离测试。实机当前进程PID2554，从21:04:41起；不可将mock日志用于证明主机转速测试成功。

## 主机发送测试数据：现有入口，无须刷固件

原版104的RPM WARN页面，LINKED FLASH开启且非Standalone时，红色TEST调用 `espnow_link_trigger_linked_test()`，由主机驱动模拟转速上升/下降；若在从表触发，它会通过ESP-NOW向主机发起TEST_START。

BLE1FF8的控制接口只有过滤/周期命令，没有“注入任意车况”的命令。不能往OTA或过滤接口乱发字节冒充造数。可让用户在主机RPM WARN开启LINKED FLASH再点TEST（先记原FLASH ANIM和LINKED FLASH状态，测试后恢复，不改阈值），观察小米BLE是否收到F101。

已向用户发出此步骤，尚待用户触发/确认。不能把该测试描述为已完成；即使RPM测试成功，也不等于其余8字段实车验证完成。

## 最后一次修正与当前用户选择（不要覆盖）

持续观察中发现BLE仍Connected但通知停止，字段TTL确实清空了旧值。补充无有效数据6秒后重新订阅一次（仅1FF8），再无数据6秒则抛出TimeoutError让既有worker清理重连。不会无限频繁写过滤器，也不会注入数值。对应单测模拟静默连接，证明先修复一次、随后重连且从未发布假数据。

第三轮部署备份 `/home/umeko/desktop-offline/ble-stock104-before-ylNt9Y`，最终实机进程PID2624（21:07:46起）。其初始连续3通道按约9Hz更新，21:08:27已计1098包、格式错误0。没有发现本轮需要恢复无线实验模块；WCNSS/stock module仍原版。

用户随后主动在手机UI选择 **SkyGarageRC**，配置现在为 sky/`[BT-ADDRESS]`/enabled=true；direct仍记忆 `[BT-ADDRESS]`。**保留此用户选择，不得强行切回主机7C地址。**

BlueZ只读确认44地址Connected=true、1FF8/0001 Notifying=true；其1FFA身份为 `main-122-aaf6e161d3c6`（原版从表版本122，不是主机版本104）。它正是COM5从表的BLE地址，Wi-Fi STA地址是44:1B:F6:85:5B:FC。

为避免应用旧日志缺少address字段导致归属混淆，本轮另外用只读D-Bus观察器严格匹配44地址characteristic，8秒收到 F102/F103/F104各72次，共216次，速度0、水温-40、进气温-40、格式错误0，仍无F101转速。不能将这3个缺省值视为已经完成主机模拟转速测试，也不能仅凭数据存在就宣称整条主机→ESP-NOW→从表→BLE的动态数据已验证。

`probe_existing_sky_notifications.py` 已可选传目标MAC，默认仍旧主机7C地址；本次运行显式传44地址。它不会Connect/StartNotify/StopNotify/写GATT，只加D-Bus通知监听。

本轮最终回归76项通过、2跳过。手机完整诊断仍在bluetooth.jsonl及其轮转文件；另有phone `sky-ble-stock104-fix-verification-20261019.log`。二进制USB下载尝试超时留下PC同名0字节文件，**该文件不能作为有效日志**；已用串口命令日志另存 `sky-ble-stock104-fix-verification-20261019-serial.log`。不要因为存在文件名就认定下载成功。
