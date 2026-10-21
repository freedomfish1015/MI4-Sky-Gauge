# SkyGauge 主机 ↔ 手机 BLE 故障取证记录

时间：2026-10-19 21:20–21:40 Asia/Shanghai
对象：主机 SkyGauge-7730 `[BT-ADDRESS]`（COM8），手机 COM10

## 1. 结论摘要

手机侧完全正常；故障在**主机侧 ATT 层不响应**。但历史上主机曾多次正常提供
1FF8 并可被订阅，说明不是硬件损坏，而是**主机运行态/配置在变化**。

## 2. 决定性证据

### 2.1 HCI 抓包（手机侧，btmon）

一次完整重连周期内，手机只发出：

```
ATT: Exchange MTU Request (0x02) len 2
      Client RX MTU: 517
```

之后**没有任何 ATT 响应**（无 MTU Response、无 Read By Group Type）。
每轮约 25 秒后由 BlueZ 主动断开：

```
@ MGMT Command: Disconnect (0x0014)
      Reason: Remote User Terminated Connection (0x13)
> HCI Event: Disconnect Complete
      Reason: Connection Terminated By Local Host (0x16)
```

→ **是手机侧超时后主动断，不是主机踢人**。三轮循环行为完全一致。

### 2.2 主机串口（COM8，复位后启动日志）

```
I (1593) espnow_link: ESP-NOW MASTER up (broadcast 100ms, ch1)
I (1633) wifi:Coexist!!! Wi-Fi station would only keep waked when available
I (1870) obd_dsp: Device role: MASTER (BLE/OBD + ESP-NOW broadcast)
I (1967) racechrono_diy: Advertising started (name=SkyGauge-7730, ota_mode=0)
I (4086) racechrono_diy: GATT client connected: [BT-ADDRESS] conn_id=0x0000
```

- `[BT-ADDRESS]` 是手机 BLE MAC，主机**确实收到连接并分配 conn_id=0**
- 复位前还出现 `BT_APPL: gattc_conn_cb: if=3 st=0 id=259 rsn=0`，说明主机同时在当
  **GATT Client**（去连 OBD 适配器）
- 40 秒稳定观察：串口只有 `brake_temp: RS485 RX timeout` 刷屏，**无任何 BLE 事件**

### 2.3 手机诊断日志（`~/.local/state/obd-gauge/diagnostics/bluetooth.jsonl`）

事件计数（累计）：

| event | 次数 |
|---|---|
| connect_begin | 268 |
| session_error | 231 |
| **skygauge_rx** | **183** |
| gatt_service | 157 |
| packet | 156 |

**曾经成功接收过 183 次遥测**，例如：

```
12:53:16 skygauge_rx length=8 hex=02f1000000000000 values={"obd.speed": 0}
```

### 2.4 关键矛盾：主机暴露的服务在不同时刻不同

10:37:02 实际发现的服务**只有两个**：

```
1ff9 (Pair)  characteristics: 0003 read  handle=41
1ffa (Info)  characteristics: 0001 read  handle=44
```

→ 当时 **没有 1ff8**，手机抛
`UnsupportedBleProtocol('SkyGauge 无 BLE 遥测服务，需兼容主机固件')`。

而 12:53 和 21:04 又收到了 F101 数据（即 1FF8 存在）。

## 3. 源码依据（104 提交 9c3fa1b，`racechrono_ble_diy.c`）

```c
static bool s_rc_enabled = true;   // false = skip RC(1FF8)+Pair(1FF9)

case ESP_GATTS_REG_EVT:
    bool is_master = (nvs_cfg_get()->device_role == ESPNOW_ROLE_MASTER);
    if (s_rc_enabled) {
        // Full mode: RC → Pair → Info → OTA
        esp_ble_gatts_create_attr_tab(s_gatt_db, gatts_if, IDX_NB, 0);
    } else if (is_master) {
        // Master minimal: 只建 Pair 服务 + 广播
        esp_ble_gatts_create_attr_tab(s_gatt_db_pair, gatts_if, IDX_PAIR_NB, 1);
        ESP_LOGI(RC_TAG, "GATTS registered (Master mode: Pair+Info+OTA ...)");
    } else {
        // 不广播，只建 Info
    }
```

`rc_enabled` 来自 NVS（`nvs_user_cfg_t.rc_enabled`，0=minimal / 1=full），
且编译期若定义 `CONFIG_OBD_DEDICATED_G_METER_MASTER` 会**强制传 false**：

```c
racechrono_ble_diy_start(
#if CONFIG_OBD_DEDICATED_G_METER_MASTER
    false
#else
    user_cfg->rc_enabled
#endif
);
```

## 4. 当前未解的矛盾

- 主机日志**没有** `GATTS registered (Master mode: ...)`（LOGI），也**没有**
  `RaceChrono BLE DIY started (minimal: Info+OTA only)`（LOGI）
- 若走 full 分支日志为 LOGD（默认不输出），与现象一致 → 推断 `s_rc_enabled = true`
- 但 `s_rc_enabled = true` 时理应创建 1FF8 并正常响应 ATT，实际 ATT 完全无响应

→ 怀疑 **GATT attr table 创建失败**（内存不足）或协议栈半死。
   待主机完整启动日志确认 `Create attr table failed` 是否存在。

主机内部 RAM 仅约 185+21+32 KiB，而同时运行 LVGL 界面、主题引擎（theme_0 解析
失败）、启动视频、Wi-Fi/ESP-NOW（10Hz 广播）、BLE(GATT server + client)、
RS485 轮询 —— 内存压力是首要嫌疑。

## 5. Flash 备份

`[LOCAL-PATH]`（16 MiB，进行中）

esptool 4.12.0，COM8 为 **USB-Serial/JTAG**：

- `--baud 921600`：约 38% 处 `Corrupt data, expected 0x1000 bytes but received 0xd89 bytes`
- `--baud 460800`：约 1% 处同样 `Corrupt data`
- 最终改用 `--no-stub --baud 115200`（ROM 协议，约 25 分钟）

**注意**：参数必须用下划线旧语法（`--after hard_reset`），连字符会被拒绝。

## 6. 建议下一步

1. 备份完成后重扫广播，确认当前是否声明 1FF8（`scan_adv.py`）
2. 读取主机完整启动日志，找 `Create attr table failed` / `gatt` 相关 LOGE
3. 若确认协议栈异常：编译最小 BLE 测试固件（只开 GATT server，不启 Wi-Fi）
   刷入验证，区分「硬件/共存」与「app 内存/逻辑」
4. 若只是 `rc_enabled=0`：让主机 UI 重新开启 RaceChrono 服务即可，无需刷写
