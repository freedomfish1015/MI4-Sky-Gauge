# 小米4仪表 / SkyGauge 蓝牙故障交接

更新时间：2026-10-19，Asia/Shanghai。本文件优先于旧交接中的“SkyGauge 没有 BLE 遥测服务”结论。

## 1. 用户目标与最新授权

- 小米4作为触屏仪表，支持直连汽车 OBD 和 SkyGauge 两种模式。
- 直连 Vgate iCar Pro2：用户已实车确认连接没有问题，勿破坏。
- SkyGauge 模式：用户希望手机像原版 ESP32 从表一样接收主机数据。
- **最新授权：可以修改 ESP32 固件，尝试修复主机 BLE bug。** 此前“不改 SkyGauge 固件”的限制已放宽。
- 最新请求是编写交接文件，因此当前暂停修改/刷写。
- **本轮尚未修改 ESP32 源码、尚未编译测试版、尚未备份主机当前完整 Flash、尚未刷入 ESP32 新固件。**

## 2. 重要结论，避免重复误判

### 已证明

1. 原版主机104实际存在 BLE 遥测服务 1FF8。21:04:42 手机成功订阅并持续收到 F102/F103/F104。
2. 原版从表122 SkyGarageRC 也能通过 BLE 输出这三个字段。独立只读 D-Bus 监听严格匹配从表地址，8秒共216包，各字段72包，格式错误0。
3. 当前主机没有连接汽车 OBD，收到速度0、水温-40、进气温-40，**不能用这些缺省值证明实车数据或动态主从转发已验证**。未观察到真实 F101 转速测试数据。
4. 用户曾确认原版从表显示已连接主机，是原生链路的对照设备。
5. 手机确实有间歇性 BLE 连接/服务发现故障，不应把“Connected=yes”当成服务订阅成功。

### 未证明 / 当前故障

- 手机当前连接主机经常在服务发现阶段失败：`failed to discover services, device disconnected` 或 `_wait_for_services_discovery` 超时。
- BlueZ 曾出现 `Connected=yes` 而 `ServicesResolved=false`，bluetoothd 反复 `No matching connection for device`。
- 尚未确认故障完全在手机还是主机。允许修主机，不代表可以跳过取证直接刷入猜测性修复。
- **手机原生 ESP-NOW 没有接通。当前成功的数据路径是 BLE，不是模拟原版 ESP32 的 ESP-NOW 无线链路。**

## 3. 设备与端口

| 设备 | 端口 / 地址 | 身份 |
|---|---|---|
| 小米4 LTE | COM10，115200 | Ubuntu24.04 armv7，Linux6.15.11-mi4-audio1，用户umeko |
| SkyGauge 主机 | COM8；BLE `[BT-ADDRESS]`；Wi-Fi `[BT-ADDRESS]` | SkyGauge-7730；`main-104-9c3fa1b27e9d`；ESP32-S3，微雪1.85 ST77916 |
| 原版从表 | 之前COM5；BLE `[BT-ADDRESS]`；Wi-Fi `[BT-ADDRESS]` | SkyGarageRC；`main-122-aaf6e161d3c6` |
| ESP32 OBD模拟器 | BLE `[BT-ADDRESS]` | OBDII，非上述主机，勿误刷 |

最新 Windows 枚举只见 COM8 和 COM10，**COM5当前未枚举，需重新确认从表在场情况**。不要沿用旧端口假设刷写。

注意：用 .NET SerialPort 打开 COM8/COM5，即使 DTR/RTS=false，之前也导致 ESP USB 复位。读取串口不是绝对无扰动，应提前告知。手机 COM10 可正常操作。

## 4. 当前手机配置与运行状态

21:13检查配置：mode=sky，address=`[BT-ADDRESS]`，enabled=true，profile=bmw.fg；direct记忆地址 `[BT-ADDRESS]`。该direct地址当前BlueZ名SkyGauge-4CAC，身份未重新确认，不要仅凭地址断言就是Vgate。

用户曾选择SkyGarageRC，之后又切回主机。**部署前重新读取settings.json，不要用旧配置强行覆盖用户选择。**

21:16:05只读检查：`bluetooth`、`obd-gauge-kiosk`均active；主机Connected=yes；缓存UUID1FF8/1FF9。普通用户journalctl看不到系统日志，应使用sudo。

服务：`obd-gauge-kiosk.service`，User/Group=umeko，WorkingDirectory=`/home/umeko/desktop-offline`，启动器 `/usr/local/lib/obd-gauge/launch_boot_video.py`。重启服务会重播NERV开机视频，这是预期现象。

## 5. 已部署手机修复

PC源码目录：`[LOCAL-PATH]`

手机源码目录：`/home/umeko/desktop-offline`

仅更新了 `gauge_ble_protocol.py` 和 `gauge_sky_slave.py`：

- 严格在1FF8内选0001 notify、0002 write；不得拿OTA同号特征做控制。
- 订阅后写 `01 00 64`：允许所有有效字段、100ms间隔。仅会话参数，不是造数、OTA或NVS写入。
- 九字段解码F101..F109，每字段3秒TTL；没收到RPM不伪造0。
- 状态显示BLE遥测，不宣称汽车OBD已连接。
- 无有效数据6秒重新订阅一次，再6秒仍无数据则抛出超时、清理重连。
- 若BlueZ中已存在严格匹配且Connected=true的对象，构造BLEDevice复用，避免Bleak按地址重新扫描却找不到已停止广播的主机。
- 仅配对服务分支不再无限等待，退避后重新发现。

当前期望SHA256：

```
gauge_ble_protocol.py
453859391cf722e0603082ff235083144c8d11fa220332146bf8eff1d4fedc38
gauge_sky_slave.py
c849b02f88e32d8b0eeb34a6998a7e955e21fabbd94f12cda303a62c945a3c78
ble-stock104-fix-20261019.tar.gz
da2417bdbbe486dcfb06cbbac5864f64b95a60183aa0416cbbaba0a7d1aa448e
```

测试：桌面相关回归76通过、2跳过；手机协议/从机16通过。它们证明代码逻辑，不等于长期无线稳定性验证。

手机备份两文件的目录：

- `ble-stock104-before-cn6OW3`：最初版本。
- `ble-stock104-before-zLjbXL`：中间版。
- `ble-stock104-before-ylNt9Y`：无数据看门狗之前版本。

都在手机app目录。`install_sky_ble_stock104.sh`有前版本hash检查，**不能未经更新直接重复执行**。

## 6. ESP32 源码、工具链与备份陷阱

### 源码

- 原版主机精确提交：`9c3fa1b27e9ddd3114ca29386615dd7406aa470e`。
- 本地 `[LOCAL-PATH]` 的git已有该commit，HEAD却是826a507，且工作区有大量用户已有改动（G表等）。**勿reset/checkout覆盖、勿直接拿工作区当104源码。**
- 仓库为缺blob的promisor仓库。`GIT_NO_LAZY_FETCH=1`下已成功读取104的racechrono_ble_diy.c，但读取同提交 `main/bsp_obd_dsp/elm327_ble_client.c`报bad object，可能该版本路径不同/对象不全，先查tree，不要擅自联网补齐。
- `[LOCAL-PATH]` 是更新的rebuild版本，不是主机104。其AGENTS.md已读，改动需同步文档；后续若在该repo工作也要查AGENTS.local.md。不要把新版整体当小补丁刷入旧主机。
- 用户要求GitHub下载使用中国国内快速镜像。优先本地已有对象；若确需下载，按要求选镜像并校验精确commit/内容。

### 已发现但尚未确认的源码风险

104的racechrono_ble_diy.c用全局单连接 `s_conn_id/s_connected/s_notify_enabled`；CONNECT直接覆盖conn_id，DISCONNECT不比对当前连接便清状态。可能存在多客户端/多角色连接状态污染，**目前只是检查方向，未证明它导致当前服务发现故障，尚未写补丁**。

还需检查：GATTS/GATTC连接事件区分、每连接CCCD、通知队列拥塞、断连恢复、服务启动完成后再广播、扫描/OBD并发与BLE共存。不要只加重试掩盖底层错误。

### 工具链

- ESP-IDF `[LOCAL-PATH]`
- 环境脚本 `[LOCAL-PATH]`
- Python `[LOCAL-PATH]`
- 此Python的esptool已确认v4.12.0（注意它用下划线老命令语法，勿照抄v5命令）。
- rebuild/build/CMakeCache来自作者macOS，含/Users/parklu路径，不能复用构建目录。

### 旧备份不是当前主机状态

`[LOCAL-PATH]`

16MiB，SHA256 `b302c0cc1b4d3749db97a9ba3ede2d5937449c37b5433f8c7864b67a13884238`。

**这是2026-10-17刷SkyGauge之前的微雪出厂演示程序，不是现在104主机的完整备份！不能用它声称当前主机可原样回退。**

`outputs/firmware-download-2026-10-19/legacy-prebuilt-NOT-rebuild.zip`含旧9c3fa1b-dirty现成固件；rebuild源码zip不是该固件。旧/新分区不能混刷。

真正刷写前，必须新读当前COM8完整Flash、记录芯片/MAC/分区/ota槽/配置、校验备份与恢复路径，再确定只写匹配布局的应用分区；不要整片擦除或默认覆写NVS/主题/bootmedia。原版从表先保留作对照。

## 7. 建议接手顺序

1. 确认当前端口、手机配置和主机身份，保持USB供电。
2. 先手机端有界btmon抓取ATT/HCI，停止app重试后做一次干净目标断开/重连，区分BlueZ陈旧连接与主机不响应。脚本必须finally/ExecStopPost恢复仪表，不留下黑屏。
3. `btmon`手机已有。当前sudo需确认缓存；不要为了BLE重启WCNSS/ADSP/modem。
4. 按最新授权备份COM8完整Flash。读取会复位设备，先说明，记录hash；不得把旧出厂备份当当前回滚。
5. 在隔离目录准备精确104源码和匹配工具链，先检查能否基线构建。现有脏工作区保留不动。
6. 依据抓包/串口事件定位后做最小固件补丁，并加事件日志和可控测试入口；不要默认持续制造假车况。
7. 验证手机重连、服务发现、通知恢复、多设备共存，原版从表继续可用。最后需要实车OBD验证动态数据。

主机原版已有测试入口：RPM WARN页，记下FLASH ANIM/LINKED FLASH原状态，LINKED FLASH ON后按红色TEST，结束恢复原状态、不改阈值。尚未确认用户确实执行成功；BLE过滤控制接口没有任意造数命令，勿向OTA乱写。

## 8. 日志、串口与传输

- 手机诊断 `/home/umeko/.local/state/obd-gauge/diagnostics/bluetooth.jsonl`及.1..4，1MB×5。
- PC有效日志 `[LOCAL-PATH]`。
- 同名不带`-serial`的PC .log是下载超时留下的0字节文件，**无效**。
- 手机完整 `sky-ble-stock104-fix-verification-20261019.log`仍在app目录。
- 只读监听器 `probe_existing_sky_notifications.py`可传目标MAC，只监听现有D-Bus通知，不连接、不订阅、不写GATT。内部特征路径按已知handle，换固件后要重新核对。
- 首轮测试进程PID2459在21:02:35写了mock RPM2300/2000到真实诊断，已加annotation。**这是单测数据，绝非主机测试成功。**后续测试要隔离OBD_BLE_LOG_DIR。

Windows串口命令：

```powershell
& '[LOCAL-PATH] -PortName COM10 -CommandText 'date; systemctl is-active bluetooth obd-gauge-kiosk' -TimeoutSeconds 8
```

支持`-OutputPath`保存命令输出。上传用同目录`send-usb-file.ps1 -PortName COM10 -Path <PC路径> -RemoteName <文件名>`，落手机app目录并校验SHA。**串口操作不可并发**。手机工具读写依赖/tmp/usb-receive.py、usb-send.py；长日志优先串口命令保存而非未经验证的二进制下载。

不在交接文件明文保存sudo密码；沿用设备现有凭据。提权失败再向用户询问，勿反复盲输。

## 9. 不要动的已有修复

- 手机boot包含OCV电量表、WLED左右背光、音频修复；BLE任务不需要刷手机boot。
- IMU/G值/GPS、仪表主题、1080p/触摸/设置均保留。
- 已有安全音频增益不再加大。
- 拔USB20秒自动关机、插电自动启动仍有效，勿无意触发。
- Wi-Fi原生ESP-NOW实验已回到原版WCNSS模块/固件。多轮仅收到Beacon，没有接通Action/ESP-NOW；不要把固件加载成功或寄存器改成功当成接收成功。

更多过程见同目录 `SKYGAUGE-PHONE-FIX-20261019.md`、`SKYGAUGE-BLE-TELEMETRY-CONFIRMED-20261019.md`、`SKYGAUGE-POSITIVE-CONTROL-20261019.md`。
