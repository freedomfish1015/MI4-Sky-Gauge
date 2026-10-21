# 小米 4 蓝牙诊断及手机端兼容补丁（2026-10-19）

## 边界

仅修改手机 Python 蓝牙协议选择。未修改 SkyGauge 固件、boot、电量、背光、音频、GPS、IMU 或主题。未确认实际车载适配器连接成功。

## 源码来源

用户提供 https://github.com/steveEcode/obd_brz_gauge 。在线读取失败，不能声称核验了远端最新版。

本机已有同仓库：
- `[LOCAL-PATH]`，HEAD `1c8ebe9d555f6e7b2b923ccc0cabed427365e5dd`。
- `[LOCAL-PATH]`，HEAD `826a5071c842558771498507aa3335e906405d71`。本地可能包含移植修改；版本不保证等于用户 SkyGauge v104。

依据 `main/bsp_obd_dsp/elm327_ble_client.c` 的 UUID 注释及特征枚举逻辑，修复手机只支持 FFE1 的限制。

## 两种不同连接

1. 手机直接连接 BLE ELM327：已支持 service / RX / TX：FFE0/FFE1/FFE1、FFF0/FFF2/FFF1、18F0/2AF0/2AF1、FF12/FF14/FF15。根据实际属性选择有响应或无响应写入，RX 必须 notify/indicate；禁止跨服务拼接及未知服务猜测。经典蓝牙 SPP 仍未实现。
2. 手机连接 SkyGauge 主机：实机 [BT-ADDRESS]（SkyGauge-7730）发现 1800/1801/1FF9/1FFA/1FFB，无 1FF8 遥测服务。配对 1FF9 仅提供 ESP-NOW MAC，1FFA 只读设备信息，1FFB 为 OTA；不能当作 ELM 串口。主从仪表数据由 ESP-NOW 转发，不是这条 BLE 配对服务。

用户确认 v104、MASTER、无 RACECHRONO 菜单。源码存在 rc_enabled 控制 1FF8 创建，但未找到通过现有 BLE 服务修改该配置的接口。不能仅因广播存在就认定可读车况，也不能把源码版本完全等同于该二进制。若确有 1FF8，手机现支持通知解析 F101–F109，小端 uint32 PID + int32 数据；此路径不发送 AT、过滤器或 OTA 写入。

## 设备及部署

手机 COM10；COM8 身份未核验，禁止假定为目标主机或刷写。
运行目录 `/home/umeko/desktop-offline`，服务 `obd-gauge-kiosk.service`。
首轮补丁：`gauge_ble_protocol.py`、`obd_ble.py`、`gauge_compat_ble.py`、`gauge_settings.py`。
首轮手机备份 `/home/umeko/desktop-offline/ble-before-skygauge-DucQOe`。
本轮仅更新 `gauge_ble_protocol.py`，SHA256 `febf9cabcebaf26c19a895ad70db568c76f98594777aa0b743004ee755d5c956`，原模块 SHA256 `d8720fb952ee60fcc0b07321e2f311c24e09e80e1874e786dc249850994e7c62`。
执行前核验原哈希，mktemp 创建 `ble-before-multi-uart-*` 备份后覆盖并重启服务。

测试：`python3 -m unittest test_gauge_ble_protocol test_gauge_settings test_gauge_compat`，34 tests，OK，1 skipped。覆盖分离收发通道、有/无响应写、阻止跨服务及未知 OTA 写、遥测解析与取消。

BlueZ ExchangeMTU=23 曾短暂试验，无改善证据，已恢复原配置（`#ExchangeMTU = 517`）；原文件 `/root/mi4-bluetooth-backup-20261019/main.conf`。不要把该临时实验当作已生效修复。

## 下一步

先取得车载 OBD 发射端名称/型号，确认是 BLE 还是经典 SPP；让它通电并断开其他客户端，再在手机选择。不要静默改为模拟器或更换用户 PID。
若 BLE 服务是上述已支持布局，采集连接及 ELM 初始化日志验证；若不同，先只读列服务/特征，再按型号证据加布局，禁止遍历未知可写句柄发送 AT。
适配器可能只允许单客户端，SkyGauge 主机占用时手机可能无法同时连接。
主机 1FF8 缺失无法通过手机协议选择补出；任何主机固件修改/刷写需用户另行明确授权，并先核验型号和备份。

状态：手机补丁已部署，蓝牙及仪表服务 active；真实车载适配器尚待实测，不得宣称全部修复。

## 再次实机只读核验

用户补充车载发射端型号为 Vgate iCar Pro 2（可能是 2S，尚待铭牌确认），当前不在身边。用户要求不修改 SkyGauge。

`probe_skygauge_readonly.py` 再次连接 SkyGauge，成功列出实际特征：1FFB 下 0003 read/notify、0002 write-without-response、0001 write（均为 OTA 服务）；1FF9 下 0003 read；1FFA 下 0001 read。无 1FF8。只读身份 manifest 请求等待 4 秒超时，不能宣称读取到了固件身份。探测结束自动恢复仪表服务；未写任何 GATT 数据、未改主机配置。

源码 `racechrono_ble_diy.c` 的遥测服务需启动时 rc_enabled 为真才创建；现有 GATT 写处理只有遥测 CCCD/过滤器及转交 OTA，无远程开启 rc_enabled 的接口。每条新连接默认 allow_all=true、间隔 100ms，因此存在 1FF8 时手机订阅即可，无需猜测发送启动命令。

## 用户实车测试日志

已安装 `gauge_ble_diagnostics.py`，并在配置/扫描、legacy ELM、native PID、SkyGauge RX 路径插桩，不主动改变连接或发送额外 PID。
手机日志 `/home/umeko/.local/state/obd-gauge/diagnostics/bluetooth.jsonl` 及 `.1` 至 `.4`；每份 1 MiB，总计约 5 MiB，轮转删除最旧日志。不是无限保留，回来应尽快导出。
记录 UTC、monotonic、PID、连接会话ID、所选地址/PID包、扫描设备名和地址、GATT服务/特征/属性、协议及写模式、初始每方向60包（每包前256字节）、之后每方向5秒采样、引擎状态/信号摘要（5秒采样）、错误堆栈。日志不采集 GPS 或轨迹，也不全程抓取周围蓝牙流量。若系统突然断电，最近未落盘数据可能丢失。
测试 37 项通过，1 skipped；磁盘失败不影响仪表，轮转及限频已测试。
部署包 `ble-diagnostics-20261019.tar.gz`，SHA256 `adeefa2bc9532c5c3b749bcdd0f14e47a4a910f8a69128e309ded8e280e97aa2`。
手机回退备份 `/home/umeko/desktop-offline/ble-before-diagnostics-EKEkOM`（4个修改前模块）；新日志模块可保留。
待用户下车测试 Vgate 后，先导出上述全部5份日志，再结合 `journalctl -u bluetooth -u obd-gauge-kiosk`；不要只取当前日志而忽略轮转文件。确保设备未被其他客户端占用，不在驾驶中操作。

## 主从模式验证（同日后续）

用户实测 Vgate OBD 可连接，现要求手机作为 SkyGauge 从机，不更改 SkyGauge。
源码 `gauge_pair_ble_client.c` 读取服务 1FF9 / 特征 0003 的 6 字节 ESP-NOW Wi-Fi MAC 后关闭 BLE；`ui_ScreenPageBLEScan.c` 的 on_pair_result 调用 espnow_link_bind_master(mac)。从机数据通过 `espnow_link.c` Wi-Fi channel 1（2412MHz）ESP-NOW 广播接收，不依赖 1FF8。主机 peer.encrypt=false，100ms 广播，联动测试时20ms；从机500ms广播presence，主机只做在线统计。仅被动接收尚不等于完整从机握手。

手机驱动 wcn36xx + mac80211。`probe_wifi_capabilities.py` 通过只读 nl80211 GET_WIPHY 得到 phy0 supported_iftypes=[1,2,3,4,6]，monitor=true。
`probe_sky_espnow.py` 已实机成功创建 skymon0、设 channel1、监听10秒、删除接口，原 wlan0 保持 DOWN，仪表 active。未注入数据帧、未更改 SkyGauge、未刷内核。首轮匹配 V5 47字节车况包计数0，尚未确认 SkyGauge 当时是否在场，不能据此断言硬件不能接收，也不能宣称已实现纯手机从机。
后续需先确认主机通电在附近；增加接收总数、ESP-NOW帧计数、数据包版本及长度计数（不保存无关设备内容），区分主机不在场/版本不匹配/驱动过滤等情况；绑定主机MAC后严格过滤源地址。当前探测脚本只按V5解析，不是正式集成从机。
独立新文件：probe_wifi_capabilities.py、probe_sky_espnow.py、test_probe_sky_espnow.py。未改动 Vgate 已工作的应用逻辑、Wi-Fi持久配置或开机服务。

### 主机在场后的复测

用户确认主机通电在附近，但尚未连接 OBD。当前手机保存目标为 Vgate `[BT-ADDRESS]`、bmw.fg，保留未改。
新增区分 all_frames/action_frames/espnow_frames 及 SkyGauge magic版本长度的计数，不记录周边无关设备内容。channel1监听10秒：默认模式 all_frames=2、无ESP-NOW；加 CONTROL/OTHER_BSS 监听 flags 后 all_frames=0。另试先调channel1再临时UP无关联的wlan0提供station context，仍0帧。先UP station再设channel曾返回EBUSY，已调整顺序。每次已删除skymon0、恢复wlan0原DOWN状态，仪表active，无持久Wi-Fi改动。
这并未证明SkyGauge没有广播，也未证明手机硬件绝对不能收；驱动/固件过滤、实际信道或SkyGauge实际二进制行为仍需核验。不能宣称只差PID解码或已实现从机。
本地源码 master_task() 无论 ELM 是否连接均广播，flags bit0 反映 OBD 连接。用户实际固件可能不同；下一次让SkyGauge连接Vgate再复测，必须让小米/其他客户端先释放Vgate。若仍无802.11帧，不应通过改PID/扩大蓝牙UUID猜测解决，需进一步验证wcn36xx监听收帧能力。

## 独立双模式（手机作为 SkyGauge 从机）

已实现设置 → 蓝牙连接中的“直连 OBD / SkyGauge 从机”按钮，各模式分别保存地址与enabled，切换复用原revision机制先取消并清理前连接。配置兼容原address/enabled字段，保留PID、窗口、亮度等。
`gauge_sky_slave.py`：从机只读1FF9/0003获取6字节Wi-Fi MAC，保存 `~/.config/obd-gauge/skygauge-binding.json`，随后关闭BLE；不向主机发送ELM/OTA。若提供1FF8则可用已实现的只读BLE遥测接收。没有1FF8且配对成功时，诚实显示“主机已绑定 · ESP-NOW 接收尚未接通”，无伪造值。**ESP-NOW接收仍未集成，这是模式UI及配对路径，不是完整从机交付。**
主机缺少配对服务会报“此设备未开放 SkyGauge 从机配对服务”，不是ELM连接失败。读取失败仍记录诊断。
40项测试通过，1 skipped，包括老配置迁移、分别记忆设备、从机配对只读/关闭连接、不将ELM当主机。设置页面已渲染查看，无遮挡。
安装时当前选中SkyGauge，移入Sky模式；直连保留此前已验证Vgate `[BT-ADDRESS]`。不更改SkyGauge固件。
部署包 ble-two-modes-20261019.tar.gz SHA256 `efc623d74b08cd2dd1cb273a4a88d86f09e3ab0ead6d036e51cd6c28d90686ca`。
手机回退 `/home/umeko/desktop-offline/ble-before-modes-lXqNlf/` 内有原gauge_settings.py和原settings.json；新增模块可保留。回退前备份用户之后新配置，不覆盖用户后续选择。
