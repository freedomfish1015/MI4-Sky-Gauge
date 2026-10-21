# SkyGauge 主机 BLE 多客户端改造

时间：2026-10-19 22:20–23:10 Asia/Shanghai
目标：让一台主机同时被多台手机读取遥测，而不牺牲 ESP-NOW 的 1 主 N 从
基线：`steveEcode/obd_brz_gauge` @ `9c3fa1b27e9d`（与设备 `main-104-9c3fa1b27e9d` 完全一致）

## 1. 为什么改

原固件只有一组全局状态：

```c
static uint16_t s_conn_id = 0;
static bool s_connected = false;
static bool s_notify_enabled = false;
```

- `ESP_GATTS_CONNECT_EVT` 直接覆盖 `s_conn_id`，第二台手机连上就把第一台顶掉；
- `CONNECT_EVT` 里没有重启广播，控制器在链路建立后撤掉可连接广播，
  第二台手机扫描阶段根本看不到主机；
- `send_can_packet()` 只按一个 `s_gatts_if + s_conn_id` 发通知。

ESP-NOW 那条路（`espnow_link.c` 向 `[BT-ADDRESS]` 广播）不受影响，
车上从表照常工作。

## 2. 改动（`main/bsp_obd_dsp/racechrono_ble_diy.c`）

### 2.1 每客户端状态表

```c
#define RC_CONN_MAX 4          // 与 CONFIG_BT_ACL_CONNECTIONS=4 对齐

typedef struct {
    bool     used;
    bool     notify_enabled;
    bool     allow_all;
    uint16_t conn_id;
    uint16_t allow_all_interval_ms;
    uint8_t  rule_count;
    rc_pid_rule_t rules[RC_PID_RULE_MAX];
    int64_t  last_all_sent_us[RC_CH_MAX];
} rc_conn_t;

static rc_conn_t s_conns[RC_CONN_MAX];
static SemaphoreHandle_t s_conn_lock;
```

两个手机可以要不同的 PID 子集和不同频率，所以过滤规则必须按连接隔离——
这是原来 `s_allow_all / s_rules[] / s_last_all_sent_us[]` 的替代。

### 2.2 加锁

GATTS 回调跑在 BTC 任务，`stream_task` 是独立任务，两者都碰 `s_conns[]`。
`xSemaphoreCreateMutex()` 在 `racechrono_ble_diy_start()` 里创建。

发送时**不在锁内**调用 `esp_ble_gatts_send_indicate`：先在锁内把本轮该发的
帧快照成 `rc_due_frame_t[]`，出锁后再逐条发。否则一个慢客户端会卡住 GATTS 回调。

### 2.3 连接后重启广播

```c
case ESP_GATTS_CONNECT_EVT:
    conn_acquire(param->connect.conn_id);
    schedule_adv_restart();      // one-shot esp_timer, 150 ms
```

不直接调 `esp_ble_gap_start_advertising()`：控制器撤掉可连接广播是异步的，
在 CONNECT 回调里立刻重启有概率撞上 `already advertising / busy`，之后
就再也没有重试机会，主机保持不可见直到当前客户端断开。改成 150 ms 后一次性
重启，`ESP_ERR_INVALID_STATE` 视为成功（说明本来就在广播）。

### 2.4 断开时只回收该连接的槽位

```c
case ESP_GATTS_DISCONNECT_EVT:
    conn_release(param->disconnect.conn_id);
    schedule_adv_restart();      // 其余客户端不受影响
```

### 2.5 发送与订阅

- CCCD 写入按 `param->write.conn_id` 记到对应槽位的 `notify_enabled`；
- 过滤报文（`01 00 FA` 之类）按 conn_id 写进各自的 `rules[]`；
- `stream_task` 每轮采样一次九个通道，再按每个连接的规则决定发哪些，
  保证两台手机看到同一时刻的同一个值。

## 3. 容量

`build/sdkconfig` 实际生效值（ESP-IDF v5.5.3）：

```
CONFIG_BT_ACL_CONNECTIONS=4      // Bluedroid 侧上限
CONFIG_BT_CTRL_BLE_MAX_ACT=6     // 控制器侧上限
```

所以 `RC_CONN_MAX=4` 是可用上限，不是拍脑袋。`sdkconfig.defaults` 里的
`CONFIG_BTDM_CTRL_BLE_MAX_CONN=3` 是 ESP32(BTDM) 选项，对 ESP32-S3 无效，未改。

## 4. 构建

本机 `[LOCAL-PATH]` 有完整 ESP-IDF v5.5.3（eim 安装，工具链在
`[LOCAL-PATH]`）。两条坑：

1. `main/CMakeLists.txt` 里 `if(NOT DEFINED python) set(python "python3")`
   在 `component_get_requirements` 阶段会拿到 Windows 的 python3 别名并失败。
   与工作区 `obd` 的既有修复一致，改为优先 `${PYTHON}` + `find_program` 兜底。
2. **构建目录不能放在中文路径下**。`ccache` 处理
   `-fmacro-prefix-map=[LOCAL-PATH]` 时抛
   `std::filesystem::filesystem_error: Cannot convert character sequence`，
   编译在第 20/1885 步就中断。改用 `[LOCAL-PATH]` 后正常。

源码取自独立 worktree（`git worktree add --detach` 检出 `9c3fa1b`），
不触碰 `obd` 工作区里未提交的 G 表改动。

### 4.1 构建结果

```
ESP-IDF v5.5.3 / esp32s3 / 1885 steps / 19m09s / exit 0
match -- build/obd_brz_gauge.bin
  size   0x228220 (2,261,536 B)
  app 分区 0x300000，剩余 0xd7de0 (28%)
build/bootloader/bootloader.bin      0x51b0  (36% free)
build/partition_table/partition-table.bin
```

`racechrono_ble_diy.c.obj` 在 1852/1885 步编译通过，无 warning。

### 4.2 烧写范围

只烧两个区，不动其余：

| 偏移 | 内容 | 理由 |
|---|---|---|
| `0xf000` | `ota_data_initial.bin` | 全 `0xFF`，让 bootloader 回到 `ota_0` |
| `0x20000` | `obd_brz_gauge.bin` | 新固件 |

**不烧** `0xa20000 bootmedia.bin`（主题资源，会覆盖设备上现有主题），
**不烧** `0x0 bootloader.bin` / `0x8000 partition-table.bin`（版本未变）。
旧固件仍留在 `ota_1`，可回滚。


## 5. 待验证

- 两台手机同时连接，各自 `clients=2`、`conn_id` 不同
- 第一台断开后第二台继续收数，主机不重启广播
- 断开一台后另一台的间隔规则不被重置
- ESP-NOW 从表显示不受影响
