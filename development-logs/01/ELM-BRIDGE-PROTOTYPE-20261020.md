# 手机作为 SkyGauge 的 BLE ELM327 桥接器（原型，未完成整链路验证）

> 此文以下是早期阶段记录。**最新已实现并通过 AI Passport → 小米4 → Sky 的真实双BLE台架转发和断线恢复测试**，部署/源码/日志/实车切换说明见同目录 `ELM-GATEWAY-HANDOFF-20261020.md`。实际车况仍为ESP模拟数据，真实Vgate实车未验证。不要再按旧的advertise-only部署结论操作。

## 2026-10-20 更新：常驻发现服务已部署，不是正式数据桥接

用户说 Sky 又扫描不到 Mi4；检查时临时模拟/发现服务均已结束，没有桥接进程。
用户随后要求先部署、每天带设备检查。已安装并 enable：
`/etc/systemd/system/mi4-elm-advertiser.service`。

- 运行 `--advertise-only --legacy-advertising --seconds 0`，不再是几分钟测试，到显式停止为止；故障5秒后自动重启。
- 开机随 bluetooth.service 启动；不恢复旧 Sky 从机模式，不改直连设置，不停仪表。
- **只广播和记录发现/订阅/写入，不返回模拟车况，也尚未转发真实 OBD。** Sky 可能搜到并发起连接，但ELM初始化没有上游时不能成功，绝不可向用户称为整链路已经修好。
- `journalctl -u mi4-elm-advertiser.service` 查看日志，/var/log/journal 已存在；服务输出限速100条/30秒，日志保留受系统journal总量控制。
- 当前验证 enabled、active/running、NRestarts=0，应用仪表active。尚待用户验证Sky真实扫描。
- 源码增加 seconds=0 常驻语义。14项参数/转发/模拟核心测试通过，无自动开启模拟源。

排查发现：`btmgmt advinfo`/BlueZ ActiveInstances 可能返回0，同时 btmon 看到 Add Advertising Success、LE Set Advertising Parameters Success、LE Set Advertise Enable Enabled Success。**不能只用实例数0认定广播已被清理**。尝试保持btmgmt交互进程也仍是0，未据此修改底层或反复重启蓝牙。
证据 adv-controller-probe-20261020.log；部署和验证 elm-advertiser-deploy-20261020.log、elm-advertiser-verify-20261020.log。

源码SHA256 `8c00030b4915d34dabd6dc8a66025874a447b713aa49a27909502ed9fbe4ee9d`。
备份 `/home/umeko/desktop-offline/backups/elm-advertiser-before-20261020-011153/elm327_ble_bridge.py`。
停止并取消自启：`sudo systemctl disable --now mi4-elm-advertiser.service`。
恢复源码需停服务后从上述备份sudo复制，并保留umeko文件所有权；不必为停广播刷手机或Sky。

每日现场可验证的是“是否搜到 OBDII Mi4／是否发起订阅与写入”，不是实车数据联动。
真实转发仍需要本机与Sky对上游ELM的独占协调、被动解析同步仪表和断线generation隔离；原型 --upstream 仍拒绝在仪表BLE轮询启用时运行。不要为了部署就删掉这条互斥保护。

## 最新验证：模拟联动成功

用户已先确认Sky“显示已连接”，手机日志收到Sky的真实写入，包括ATZ和5字节PID请求。后续用户明确要求手机发送模拟数据，已新增 **--simulate** 独立台架模式（与--upstream互斥）。

2026-10-20约00:56:38启动限时300秒 `mi4-elm-demo.service`，原模拟数据发生器elm327_demo.py按ELM指令应答，并随时间使RPM在900–4500、速度15–85循环，水温约90、油温约100、电压约13.8。所有这些是**模拟值，不是汽车数据**。未知私有PID返回NO DATA，没有全面编造任意PID。

**用户实机确认“转速和车速都在变化”。** 这是手机本地GATT/CCCD/ELM请求响应/分包到Sky解析显示的真实闭环验证。模拟核心加转发共12项测试通过。

模拟源不开机自启，不连接Vgate、不向车发送命令。完成验证后主动停止模拟，避免留下测试值。日志 elm-demo-linked-verification-20261020.log。

尚未完成的关键部分仍是 **真实Vgate → 手机 → Sky**；也未完成手机仪表在该模式下的被动同步显示与正式设置入口。不能把本轮成功写成“真实车况桥接已经完成”。

## 新目标

真实OBD适配器 → 手机BLE central → 原始UART转发 → 手机BLE peripheral → SkyGauge主机。
手机不再模仿ESP-NOW从表，也不靠缓存的几项仪表数值伪造ELM327应答。

SkyGauge仍使用自己的车型PID轮询/AT配置。**上游ELM只能有一个指令控制者**：桥接时必须暂停手机原有轮询，将来手机仪表通过被动解析同一真实数据流显示数值。

## 当前实现

- elm_bridge_core.py：有界双向队列、原始字节保留、20字节ATT分片，不增加/删改CR、回显、CAN头或`>`。无连接不生成假回复、无订阅不回放旧数据。
- elm327_ble_bridge.py：BlueZ本地GATT，FFF0服务、FFF1 write/write-without-response、FFF2 notify；广播名OBDII Mi4。
- --advertise-only：只有发现/订阅/写入诊断，**不模拟ATZ成功，不返回假RPM**。Sky若发指令会记录尝试，然后报上游未就绪，这是预期。
- --upstream MAC：原型真实字节转发分支；为避免竞争，若obd-gauge-kiosk active直接拒绝运行，不会偷偷停用户仪表。
- --sky-address固定允许发指令的Sky BLE地址，当前7C:0C:5F:56:77:32。通知通道仍是常见未加密BLE形式，尚未完成多客户端授权隔离，不要当安全成品。
- 默认限时180秒，不开机自启，不改手机settings.json、不刷Sky/从表/手机boot。

## 已验证和未验证

- 手机hci0支持central/peripheral，BlueZ有GattManager/LEAdvertisingManager。
- 6项转发核心测试通过：字节流一致、断开不造数、不回放、队列溢出拒绝、分片一致。
- 手机BlueZ普通广播注册成功；btmon确认LE Set Advertising Data、Parameters、Enable均Success。FFF0主包+Flags0x06；LocalName在scan response；初次默认间隔1280ms。
- 用户**扫描不到OBDII Mi4**。所以不能称Sky→手机连通。
- 加入Discoverable=True和100–150ms间隔属性后注册成功，但尚未实测证明Sky已发现。
- 尝试通过BlueZ Data属性把名称放主包，被BlueZ拒绝“Failed to parse advertisement”，已回退LocalName；这不是可用修复。
- 随后增加--legacy-advertising：用btmgmt实例2设置包含FFF0+完整名称的传统ADV包，kernel timeout与进程退出负责清理。
- **最新：用户确认“现在能看到”。** 传统ADV主包名称路径已解决本轮发现问题，但还未证明GATT连接/初始化/上游数据转发成功。
- systemd下btmgmt stdin=/dev/null会在异步回调前退出；必须用临时PTY保持stdin打开，外加timeout限制。00:52:54实机日志Instance added:2、bridge_advertising成功，用户随后确认发现。
- 当前用户说**只有SkyGauge在场，Vgate不在**，因此尚未验证上游双角色并发、初始化或真实车辆数据。

## 临时单元与后续

手机代码在/home/umeko/desktop-offline；PC本目录同名源码。

- mi4-elm-bridge-discovery.service：最初D-Bus广播，之后已停止。
- mi4-elm-bridge-legacy.service：限时传统广播验证，180秒后退出，RuntimeMaxSec=200。
- 手动停止只需 `sudo systemctl stop mi4-elm-bridge-legacy`；若异常，先查journal/实例归属再清理实例2，不要全局清空其它广播。

已有观察：手机还通过central链路连着SkyGauge，可能影响扫描/双角色时序，但未证明因果。不随意全局重置蓝牙或更改Sky配对/NVS。

下一步先证明Sky扫描发现→GATT订阅→真实初始化写入。在此之前不用实车、不发车型请求。Vgate到场后才验证真正转发。

生产化前还需要：

1. 让UI工作但暂停本机轮询的正式桥接模式与互斥；恢复机制不可覆盖用户原设置。
2. Sky断开/重新订阅的generation隔离、上游断开撤销广播并断开下游，不能漏发旧包。
3. 只读车辆诊断命令边界检查，避免代理无关写入/清码；不能把原始透传等同无限授权写车。
4. MTU、长流/ATMA中断、背压、重连与两侧BLE同时工作的真机测试。
5. 手机仪表被动解析，不引入第二个并发ELM轮询器。

这份代码是可验证的第一阶段原型，**不是“已修好通讯/完全复现327”的结论**。
