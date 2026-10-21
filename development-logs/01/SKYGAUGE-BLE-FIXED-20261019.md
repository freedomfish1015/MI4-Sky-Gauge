# SkyGauge 主机 ↔ 手机 BLE 通讯：故障定位与修复

时间：2026-10-19 21:20–21:50 Asia/Shanghai
对象：主机 SkyGauge-7730 `[BT-ADDRESS]`（COM8），手机 COM10

## 1. 最终结论

**故障不在 ESP32 主机，也不在 BLE 协议栈，而在手机侧 BlueZ 的陈旧连接条目。**

主机一侧从头到尾都是正常的。用 `bluetoothctl` 直连同一台主机，ATT 层完整应答：

```
ATT: Exchange MTU Request          ->  Exchange MTU Response
ATT: Read By Group Type Request    ->  Response (37 bytes)
ATT: Find Information Request      ->  Response
```

之前记录的"主机 ATT 层装死"是误判——真实原因见第 3 节。

## 2. 根因

`gauge_sky_slave.py` 里原先的 `resolve_connected_sky()` 会去 BlueZ 的
`GetManagedObjects` 里找标记为 `Connected: true` 的设备，然后**直接把它的
D-Bus 对象路径当成 `BLEDevice` 交给 Bleak**，注释写的理由是"主机连上后就不再广播"。

这个"省事"的做法制造了两个连环问题：

1. **对死链路发请求**。BlueZ 认为连接还在（`Connected: yes`），但底层 ACL 已经没了。
   Bleak 拿到这个路径后不会重新建链，`client.services` 等 `ServicesResolved`
   永远等不到，最终报"连接已断开"。
2. **扫不到设备**。主机在**任何连接存在期间都停止广播**（实测 `BleakScanner`
   报 `NOT_FOUND`），所以陈旧条目还会让新建连接这条路也走不通。

两者叠加 → 每 25 秒一轮重试、永不成功。

## 3. 修复

`gauge_sky_slave.py`：删除路径复用，改为**连接前先清理**。

```python
async def reset_bluez_sky(address):
    # 若 BlueZ 认为已连接 -> Device1.Disconnect，轮询等待 Connected 变 false
    # 然后 Adapter1.RemoveDevice 删掉该条目（连带清掉陈旧的 GATT 缓存）
    # 最后留 0.5s 让主机恢复广播
```

`run_sky_slave()` 改为 `target = await reset_bluez_sky(address)`。
代价是每次建链多一次重新发现（约 1 秒），换来的是每次都是干净链路。

## 4. 验证

```
13:43:09  skygauge_bluez_disconnected  path=/org/bluez/hci0/dev_7C_0C_5F_56_77_32
13:43:09  skygauge_bluez_removed
13:43:09  gatt_service × 5   (1ffb / 1801 / 1ff8 / 1ffa / 1ff9)
13:43:09  protocol_selected  skygauge
13:43:09  skygauge_subscription  interval_ms=100  channels=all_stock_9
13:43:34  packets=600   malformed=0
13:44:30  packets=1044  malformed=0
13:49:29  packets 持续增长，0 次 BLE error
```

测试 `test_sky_reset.py`（13 项，全部通过）：地址查找、对端隔离、
adapter 路径映射、禁止路径复用、接线方向。

## 5. 数据说明（不是故障）

主机当前回传的是占位值：

```
02f1 000000000000  ->  obd.speed=0
coolant_temp=-40, intake_temp=-40
```

`-40` 是"传感器读数为 0"的标准表示。主机自己没有数据源：
RS485 一直在刷 `brake_temp: RS485 RX timeout`，也没有配对的 OBD 适配器。
接上真实车况源后这些值才会变化。

## 6. 主机固件确认（读取自串口启动日志）

```
app_init: Project name: obd_brz_gauge
app_init: App version:  9c3fa1b-dirty      <- 你工作区那版含 G 表改动
octal_psram: density 64 Mbit               <- 8MB PSRAM 正常
boot: Loaded app from partition at offset 0x20000
```

分区表：`nvs / otadata / phy_init / ota_0(3M) / ota_1(3M) / theme_0(4M) / bootmedia(6M)`

另有一个独立问题：`E (1687) theme_engine: Failed to parse theme manifest JSON`
—— `theme_0` 分区里的主题是坏的，引擎回退到内置默认主题。与 BLE 无关。

## 7. 关于 Flash 备份（已取消）

读分区表后发现 16 MiB 里 10 MiB 是静态素材（`theme_0` 4M + `bootmedia` 6M），
只有约 3.1 MiB 会被固件升级触及。而且主机固件与源码用户手上都有，
**不需要备份**，已终止。

附带结论：COM8 是 ESP32-S3 的 USB-Serial/JTAG 口，`--baud 921600` 和 `460800`
都会在传输中报 `Corrupt data`，`--no-stub --baud 115200` 虽可靠但 16MB 要 25 分钟。
单纯读 4 KiB 分区表用默认 stub + 115200 只需 0.4 秒。

## 8. 待处理：弧线重绘导致帧率下降

连接修好后暴露一个渲染问题（与 BLE 无关，停掉蓝牙后依旧）：

| 场景 | paint | FPS |
|---|---|---|
| 无脏区域（离线、数值不变） | 3.4 ms | 59 |
| 有脏区域（弧线更新） | 55–60 ms | 18–30 |

`bench_regions.py` 实测：一次弧线重绘覆盖 **294,408 像素（全屏 14%）**，
耗时约 55 ms。之前看到的 59 fps 是因为离线时数值从不变化、底盘一次都不用重画。

修复方向（未实施，需确认）：给弧线加重绘阈值——角度变化小于约 0.4°
（转速约 25 rpm / 时速约 1.3 km/h）时不重画，可把重绘频率降到个位数 Hz。

## 9. 从机规则落地（按原作者 `gauge_pair_ble_client.c`）

作者指出"要识别并绑定 MAC、名称有要求"。源码核实后按规则改造：

| 规则 | 源码依据 | 实现 |
|---|---|---|
| 名字前缀必须是 `SkyGauge` | `strncmp(dev_name,"SkyGauge",8)` | `SKY_NAME_PREFIX` + `name_matches_master()` |
| 读 1FF9 / 0x0003 的 6 字节 | `ESP_GATTC_READ_CHAR_EVT`，`value_len>=6` | `read_master_mac()` |
| 读到即绑定持久化 | 从机侧 NVS 保存 MAC | `store_binding()` → `~/.config/obd-gauge/skygauge-binding.json` |
| 拒绝无效 MAC | 全零/组播位 | `mac==b'\0'*6 or mac[0]&1` |

实测绑定结果：

```json
{"ble_address":"[BT-ADDRESS]","wifi_mac":"[BT-ADDRESS]","channel":1}
```

`[BT-ADDRESS]` 就是主机 WiFi STA MAC（BLE 侧是 `...:32`），与
`build_adv_identity()` 里 `esp_read_mac(mac, ESP_MAC_WIFI_STA)` 的取值一致。

## 10. 两个导致连接不稳的真正原因

### 10.1 100ms 推送把 BLE 发送缓冲耗尽

主机按手机写入的间隔推所有 PID。100ms 时约 30 包/秒，会话稳定在
**3.5–4.3 分钟**后静默，`run_skygauge` 的 6 秒看门狗触发重连。

把过滤报文从 `01 00 64`（100ms）改成 `01 00 FA`（250ms）后，
连续观测 **5.4 分钟无静默**。250ms 仍有 4 次/秒，对仪表足够。

### 10.2 反复 RemoveDevice 会让 bluetoothd 彻底无法解析服务

`Adapter1.RemoveDevice` 是用来清陈旧条目的，但连续调用若干次之后，
**每次重连都报 `failed to discover services`**，直到重启 bluetoothd 才恢复：
`systemctl restart bluetooth` 后立刻 `Connected: yes` 且 1FF8 可见。

所以策略改为**只 Disconnect、不 Remove**：陈旧 `Connected: yes` 条目
断开后主机就会恢复广播，Bleak 也能重新建链，不需要删除缓存数据库。

改造后连续观测 **4.5 分钟无重连、无错误**。

## 11. 当前状态

- `gauge_sky_slave.py`：名字校验 → 只断开不删除 → 按地址建链 → 读并绑定 MAC → 订阅遥测
- `gauge_ble_protocol.py`：订阅间隔 250ms（已备份为 `.before-interval`）
- 测试：`test_sky_reset.py` 13 项 + `test_sky_binding.py` 14 项，全部通过
- 数据仍为占位值（speed 0 / coolant -40），因为主机侧没有 OBD 数据源

## 12. 澄清：BLE 单连接 ≠ 主机只能带一台从机

主机有两个互不干扰的出口，"1 主带 N 从"指的是 ESP-NOW 那一路，不是 BLE。

**ESP-NOW 出口（N 从）** — `main/bsp_obd_dsp/espnow_link.c`

```c
static const uint8_t s_broadcast_mac[6] = {0xFF,0xFF,0xFF,0xFF,0xFF,0xFF};
esp_now_send(s_broadcast_mac, (const uint8_t *)&pkt, sizeof(pkt));   // master_task
```

无连接、纯广播，所有从表同时接收，数量只受射频占用和从表自身策略限制。
从表通过 `1FF9/0x0003` 读到的六字节 WiFi MAC 就是为这条链路做身份识别用的。

**BLE 出口（单手机）** — `main/bsp_obd_dsp/racechrono_ble_diy.c`

```c
static uint16_t s_conn_id = 0;
static bool s_connected = false;
static bool s_notify_enabled = false;

case ESP_GATTS_CONNECT_EVT:      s_connected = true; s_conn_id = param->connect.conn_id;  // 直接覆盖
case ESP_GATTS_DISCONNECT_EVT:   s_connected = false; start_advertising_if_ready();       // 仅此时恢复广播
```

只有一组全局状态，`CONNECT` 不重启广播，`send_can_packet()` 也只按
`s_gatts_if + s_conn_id` 单目标发通知。所以一台主机同一时刻只能被一台
BLE 客户端（手机）读取；再连第二台，扫描阶段就发现不了主机。

**结论**：手机上仪表（BLE）和车上从表（ESP-NOW）可以同时工作，
但两台手机不能同时读同一台主机。

**若要 BLE 也支持多手机**，控制器容量是够的（`sdkconfig.defaults`：
`CONFIG_BTDM_CTRL_BLE_MAX_CONN=3`），要改三处：

1. `s_conn_id / s_connected / s_notify_enabled` 改成按 conn_id 索引的数组
2. `ESP_GATTS_CONNECT_EVT` 里补 `start_advertising_if_ready()`，让主机连上后继续可发现
3. `send_can_packet()` 遍历所有已订阅连接分别发通知

改完需重新编译并烧写主机固件；手机端不用动。
