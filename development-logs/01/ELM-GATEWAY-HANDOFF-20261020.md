# 小米4 → Sky 主表：BLE ELM327 真实双向转发交接

> 后续已部署低延迟优化，最新文件哈希及实测见同目录 **ELM-LATENCY-20261020.md**：主机侧请求回复均值约89→35ms，转速查询间隔约393→141ms；下述文件哈希为优化前网关版本。链路架构和实车切换方法不变。

## 最新结论

2026-10-20 已部署 **AI Passport（BLE ELM 模拟器）→ 小米4 → Sky 主表**。
用户最后确认「现在都有了」。手机真实日志同时显示 `sky:true`、累计170条命令、上游2206字节回复、下发904字节；不是只看见主表数字就认定成功。
证据 `elm-gateway-live-route-proof-20261020.log`。

最初用户也曾说主表数值变化，但当时手机commands=0。该轮不算转发通过，不能引用为成功证据。
更新本地GATT后主动断开指定Sky旧链路，重新连接，才取得上述双向计数。

**这里的车辆数据仍是 AI Passport 产生的台架模拟数据；真实Vgate实车尚未在场验证。**
手机的传输确实经过两个真实BLE连接，非手机内置模拟源。

## 使用

手机设置 → 蓝牙连接：

1. 选择上游 OBD 适配器。当前台架为 `OBDII SIM`，`[BT-ADDRESS]`。
2. 保持“向 Sky 转发：开”；手机此时不再自己轮询，由Sky发起查询。
3. Sky 主表扫描并连接 `OBDII Mi4`（手机），不是直接连 `OBDII SIM`。
4. 手机和Sky尽量选择相同车型PID包。Sky发哪些查询，手机就被动解析哪些回复；没有被查询或不能解码的字段留空。
5. 实车时在手机改选 Vgate iCar Pro2 的真实BLE地址，保持转发开启；Sky仍连接OBDII Mi4。不要让Sky/其他手机直接占用Vgate。
6. 若只用手机直连，不向Sky传递，关闭“向 Sky 转发”，原有原生车型引擎恢复主动轮询。

旧 SkyGauge 从机模式仍已删除。“向Sky转发”是手机模拟一个BLE ELM适配器的独立功能，不是ESP-NOW从表。
当前simulator_address专门标识AI Passport；更换真实OBD地址后日志 simulated_source 自动为false。
之前保存的地址 `[BT-ADDRESS]` 蓝牙名称为SkyGauge-4CAC，**不能擅自当作Vgate地址**；保存在previous_obd_address及完整配置备份中。

## 架构 / 互斥

```
Sky 主表（ELM查询唯一发起者）
    ↕ BLE FFF0 / FFF1 write / FFF2 notify
root服务 elm327_ble_bridge --ipc（只提供手机本地外设，不连OBD）
    ↕ 有界、本地Unix socket /run/mi4-elm/bridge.sock
手机已有SettingsBleSource的单一BLE线程（转发 或 主动轮询二选一）
    ↕ BLE ELM UART（FFE0/FFE1等明确支持布局）
OBDII SIM / 实车Vgate
```

无需把仪表停掉才能转发，也没有第二个并发ELM控制者。
IPC校验SO_PEERCRED，仅umeko UID可作为上游，单一活动上游；socket root:umeko 0660。
Sky写入固定绑定BLE地址 `[BT-ADDRESS]`（SkyGauge-7730）；更换主表需要改service的sky-address并重启服务。

- GATT仍为用户已验证能扫描的传统广播：完整名称放主ADV包。
- 原始UART回复不修改，按20字节ATT分片；不凭缓存几项数值拼造实车应答。
- Sky命令按CR重组，保留原有空格与CR，忽略冗余LF；单请求等待ELM提示符后才发下一请求。
- 只读指令边界：适配器AT配置、Mode01/22/09/03/07/0A；拒绝清码/写入/复位ECU等请求。
- 支持ATMA监听，单独处理Sky发出的CR中断，避免等待提示符时死锁；监听回复缓冲有界。
- 原始ISO-TP只读请求必须先看到ATCAF0真实OK，才允许验证过的single-frame只读载荷（含BMW扩展寻址）。非只读载荷即使CAF0也禁止。
- 下游取消订阅会关闭上游IPC，手机关闭BLE、清值，建立新会话。上游丢失会断开指定Sky并清队列，不回放旧数据。
- 注册本地GATT后主动断开指定Sky旧链路，避免旧CCCD/句柄缓存导致“已连但没有StartNotify”。

这是普通未加密BLE，不要当作具备抗窃听认证的安全网关。写入固定Sky地址只是本机授权限制，不等于无线加密。
不支持任意车载写入、任意CAN发送或宣称完整ELM327所有扩展命令。遇到未允许命令会拒绝并断开，日志留下原因。

## 手机同步显示

`elm_passive.py`仅被动解析：标准PID、所选原生包的可支持RPN、显式expect的原始请求；普通ELM、带头single-frame、带头ISO-TP分帧。
多个ECU返回不同值时不猜测。缺失、未知、无法可靠解码的字段保持无效。
RPM/速度/节气门/负荷3秒失效，其余已解析PID15秒失效；断线全部清空。
**并非完整复制原车型引擎的每种派生/滤波/CAN监控解码能力**，不影响Sky接收到原始回复后按原固件自行解析。
手机不从UI扫针/插值生成转发数据。仪表LOG依然记录原始快照，context附sky_forward和simulated_source。

## AI Passport 固件

- 已确认COM6、ESP32-C3、8MiB XMC flash、基础MAC4C:11:AE:30:FA:08，BLE为...:0A。
- 用户确认就是AI Passport，并明确说不用备份固件；停止备份后刷写。
- 源码 `[LOCAL-PATH]`。
- 工具arduino-cli，esp32:esp32:esp32c3，Arduino ESP32 3.3.12，Bluedroid而非之前会崩溃的NimBLE。
- ST7789 240×320屏保留，倒装rotation2、反色保留；标题SIM BMW G。
- 广播OBDII SIM / FFE0、FFE1+BLE2902；转速/车速/温度等为动态模拟，支持标准OBD-II及已有部分BMW私有PID，不存在真实CAN输出。
- 为消除编译器中文输出路径链接错误，构建目录改用ASCII：`[LOCAL-PATH]`。
- 应用bin693616字节，SHA256 `1469b608004255fd9e737f942edf160c1d57223db4de59704a4581afaa9a7188`。
- esptool5.3.1仅写0x10000的app0，旧分区表app0容量1310720，bootloader/NVS/分区表未写。
- `ai-passport-sim-flash-20261020.log`有Hash of data verified。
- 先前几次整片/分块备份失败，`esp32-c3-before-relay-sim-*`产物**不得当作有效完整恢复镜像**；分区表4096字节读取成功，仅用于核对app边界。

## 服务、文件、日志

手机：`/home/umeko/desktop-offline/`

- gauge_settings.py：6da92399a98645789749a3964c8840cd58697e287361b568a1639e41b8ecee03
- elm327_ble_bridge.py：3791efe600713758b8bb76e77507541c473ec11491b6eb2124ce68378286cca4
- elm_bridge_ipc.py：a0ea91542482bfb13c3a0279e8fe4ac093ea29fe7052bc33764c451c95bf78f7
- gauge_elm_forward.py：195860d45d288e2e33315812df9b66c5a87871545f7ccfc6933243c9b03017ee
- elm_passive.py：544d8c918d6654aaf6cfc9a5591e2187ec9c52ccbe2c9e612de56d98378c961b

服务 `/etc/systemd/system/mi4-elm-advertiser.service` enabled，`--ipc --legacy-advertising --seconds 0`，失败自动重启。
`obd-gauge-kiosk.service` active。台架确认时两服务NRestarts均0。

```
sudo journalctl -u mi4-elm-advertiser --since today --no-pager
tail -n 20 ~/.local/state/obd-gauge/diagnostics/bluetooth.jsonl
```

服务日志记录GATT订阅/初始化/转发包计数，逐包日志5秒合并；系统journal存在持久目录。
手机diagnostics为蓝牙JSONL，1MiB×5循环。车辆曲线日志另在`~/.local/state/obd-gauge/telemetry/`，原GPS轨迹目录没变。
可用证据：elm-gateway-install-20261020.log、elm-gateway-final-update-20261020.log、elm-gateway-live-route-proof-20261020.log、elm-gateway-final-device-tests-20261020.log。
首次手机单元测试曾把AA:BB:CC:DD:EE:01假地址的测试计数写入diagnostics（PID3365）；不是实车，不要引用它们作链路证据。后续测试已mock日志输出避免污染。

## 验证与边界

- 桌面相关61项回归：60通过、1跳过；不代表全仓测试全绿。
- 手机上执行15项转发/命令/IPC测试通过；含防第二上游、非只读不出车、分包、监控CR中断、解析/失效。
- 用户视觉确认最终两端有数据；实际Sky请求/ESP回复/手机被动显示闭环已取得递增计数。
- 受控重启AI Passport后也自动恢复：单调时钟6385.913上游断开、6388.077 Sky取消订阅、6390.434上游重新就绪、6397.220 Sky重新订阅、6397.920重新ATZ，约12秒恢复。证据elm-gateway-recovery-events-20261020.log、elm-gateway-reconnect-proof-20261020.log。恢复后新会话累计252条命令，非旧计数继续显示。
- 最新真实遥测快照包含RPM2135、车速8、节气门23.137%、水温86、油温80，context为sky_forward=true、simulated_source=true；profile由用户在UI改回bmw.fg，未强制覆盖其选择。这些数值是各PID最近读数，不是同时刻ECU采样。
- 实车Vgate双角色链路、车辆特殊PID、长时电源/射频干扰仍需现场测试，不能用台架通过替代实车验证。

## 备份与回退

网关部署前完整应用配置和旧service：
`/home/umeko/desktop-offline/backups/elm-gateway-before-20261020-012754`

最终兼容补丁前：
`/home/umeko/desktop-offline/backups/elm-gateway-final-before-20261020-013508`

最简单停用转发：手机蓝牙页关闭向Sky转发，保留原有直连功能。
不要为此刷手机boot、修改Sky固件或恢复未知boot.img。电池OCV、WLED、音频、IMU/GPS、开机视频和电源倒计时本轮均未修改。
