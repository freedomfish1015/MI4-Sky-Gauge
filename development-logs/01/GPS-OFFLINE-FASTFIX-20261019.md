# 完全离线 GPS 快速定位方案

日期：2026-10-19
设备：Xiaomi Mi 4 (cancro, MSM8974)，Ubuntu 24.04.5，内核 6.15.11-mi4-audio1

> **状态（2026-10-20 更新）：本方案已回退，代码已改回 `poweroff`。**
> 现场实测：拔线挂起一夜后电池被抽干。`s2idle` 在这台机器上省不下电，
> 而保住星历的前提就是给 modem 供电——两者不可兼得。
> 回退细节与事后分析见文末第 9 节。**不要再部署本文第 3–6 节的挂起改动。**

---

## 1. 根因：不是 GPS 慢，是每次熄火都把 GPS 的记忆清掉了

排查发现真正的问题不在 GNSS 硬件，而在电源策略。

`gauge_power_service.py` 的原逻辑：

```python
elif time.monotonic() - self.policy.last_ui < 3:
    self.poweroff('cable')          # 拔线 20 秒后 -> systemctl poweroff
```

`poweroff` 会让 **modem（remoteproc fc880000）彻底断电**。Qualcomm 的架构里，
GNSS 引擎跑在 modem 内，星历（ephemeris）、历书（almanac）、卫星轨道表都存在
**modem 的内存**中，Linux 侧不持有。

所以每次熄火 = 星历清零 = 下次上车从零开始搜星：

- 收齐一颗卫星的完整星历（子帧 1–3）：约 30 秒连续接收
- 时间同步（子帧）：约 6 秒
- 合计冷启动 TTFF：**30–60 秒**

这正是"搜星慢"和"掉星后很久不回来"的真实原因。

---

## 2. 实测证据：suspend 能保住 modem

用 PMIC 硬件闹钟挂起 20 秒后自动唤醒：

```bash
rtcwake -m mem -s 20
```

结果：

```
=== BEFORE ===
uptime=15145.33
rp0=running  rp1=running  rp2=running
qrtr=0-1 0-10 0-11 ... 7-1 7-2        （51 个节点）

[15146.480962] PM: suspend entry (s2idle)
[15152.508144] Restarting tasks ... done.
[15152.549982] PM: suspend exit

=== AFTER ===
uptime=15173.89
rp0=running  rp1=running  rp2=running
qrtr=0-1 0-10 0-11 ... 7-1 7-2        （完全一致的 51 个节点）
```

三个判据同时成立：

1. **uptime 从 15145 连续到 15173，没有归零** → 没有重启，是真正的挂起/恢复
2. **三个 remoteproc 全程 running**，dmesg 里没有 `MBA booted` / `loading mpss`
   → modem 没有重新初始化
3. **51 个 QRTR 服务节点前后完全一致**（含 `0-16` = LOC 定位服务）
   → QMI 会话与引擎状态原样保留

结论：**s2idle 期间 modem 不掉电，星历必然保留。**

### 画面恢复

resume 后 `obd-gauge-kiosk`（PID 4032）持续输出 FPS 到恢复之后，
`present` 正常，无需重启仪表进程。仅出现两条一次性的：

```
msm_mdp fd900100.display-controller: pp done time out, lm=0
```

之后不再出现，属于 resume 瞬间的显示控制器时序抖动，不影响后续渲染。

---

## 3. 改造内容

文件：`gauge_power_service.py` → 部署至 `/usr/local/lib/obd-power/gauge_power_service.py`

| 项目 | 原行为 | 新行为 |
|---|---|---|
| 拔线 20 秒后 | `systemctl poweroff` | `systemctl suspend`（s2idle） |
| 手动关机（UI 按钮） | poweroff | **保持 poweroff** |
| 电量 < 15% | — | **回退 poweroff**（防锂电池过放永久损坏） |
| suspend 失败 | — | 回退 poweroff |
| 唤醒后仍无外部电源 | — | 再次挂起，最多 48 轮（约 8 天） |
| 保险机制 | — | 每次挂起前设 RTC 4 小时硬件闹钟 |

### 关键实现

```python
def suspend_cable(self):
    for _ in range(MAX_SUSPEND_ROUNDS):
        capacity = battery_capacity()
        if capacity is not None and capacity < LOW_BATTERY_PERCENT:
            self.poweroff('low-battery')     # 过放保护
            return
        armed = arm_rtc_alarm(RTC_SAFETY_WAKE_SECONDS)
        if not self.suspend():               # 失败则回退真关机
            self.poweroff('suspend-failed')
            return
        if external_online(self.supply_root) is not False:
            break                            # 已插线，正常返回
        time.sleep(SUSPEND_POLL_SECONDS)
```

### 踩坑：`systemctl suspend` 在这台机器上不可用

第一版用的是 `systemctl suspend`，实测失败并**静默回退成了真关机**（所以表面看"能用"，
实际每次拔线都还是关机）。日志证据：

```
systemctl[5553]: Call to Suspend failed: Sleep verb 'suspend' is disabled by config
python3[5410]: SUSPEND_ERROR CalledProcessError(1, ['/usr/bin/systemctl', 'suspend'])
python3[5410]: SUSPEND_ERROR OSError(22, 'Invalid argument')      ← Python 直写 sysfs 被拒
CABLE_STATE {"phase": "shutdown", "reason": "suspend-failed"}
```

原因：早先裁剪系统时 `sleep.conf` / `logind.conf` 被清空（只剩节名），
systemd 因此拒绝执行睡眠动作；而 Python 以文本模式写 `/sys/power/state` 被内核回 EINVAL。

**最终方案：以 `rtcwake -m mem -s N` 为主入口。**
它从 C 层直接写同一个 sysfs 节点，并把"设置 PMIC 闹钟 + 进入挂起"一步完成，
正是实测走通的那条路径。`systemctl suspend` 与 `sh -c 'echo mem > ...'` 作为兜底。

```python
attempts = (
    ['/usr/sbin/rtcwake', '-m', 'mem', '-s', str(RTC_SAFETY_WAKE_SECONDS)],
    ['/usr/bin/systemctl', 'suspend'],
)
```

### 唤醒源（已确认 enabled）

```
smbb-usbin   enabled   USB 插入
smbb-dcin    enabled   DC 插入
usb-detect   enabled   USB 检测
rtc@6000     enabled   RTC 闹钟
pwrkey       enabled   电源键
```

---

## 4. 收益

| | 改前（poweroff） | 改后（suspend） |
|---|---|---|
| modem 供电 | 断 | 保持 |
| 星历 | 清零 | 保留 |
| 下次定位 | 冷启动 30–60 s | 温启动 **5–15 s** |
| 需要网络 | 否 | 否 |
| 需要星历文件 | 否 | 否 |

**完全满足"设备始终无法联网、也无法获取星历"的约束**——设备自己记住就够了。

### 物理下限（必须知道）

如果电池被拔掉、或设备被强制关机，星历仍然会丢。此时冷启动的
**30–40 秒是不可突破的物理下限**：GPS 必须从卫星播发中收齐一份完整星历
（子帧 1–3，约 30 秒）+ 时间同步（约 6 秒）。这不是软件能优化的部分。

---

## 5. 北斗：固件支持已确认，开关状态待室外验证

### 固件证据

搜索 `/lib/firmware/modem.b*`（43 MB）中的字符串：

```
Bds_MeasBlk(%d) - %d SVs, FC %l          ← 北斗测量块（有实际测量逻辑）
BDS StrategyState - Event %d, %s         ← 北斗策略状态机
GPSGLOBDS                                ← GPS+GLONASS+BDS 组合标识
BDS request disabled. MEM %d LTE B13 %d ExtCmd %d Req %d
LUCKY_BDS
```

说明：**modem 固件完整实现了北斗**，并且存在 `ExtCmd`（外部命令）接口。
但 `BDS request disabled.` 表明北斗在某种条件下被关闭，默认状态尚未确认。

### 工具链限制

| 能力 | libqmi 1.35.2（设备） | libqmi 1.38.0 |
|---|---|---|
| `inject_xtra_data` | 有 | 有 |
| `inject_predicted_orbits_data` | 有 | 有 |
| **`inject_time`（UTC 时间辅助）** | **无** | 有 |
| **`inject_position`（位置辅助）** | **无** | 有 |
| `SET_GNSS_CONSTELLATION_CONFIG`（星座开关） | 无 | **仍然无** |
| `get_predicted_orbits_data_validity` | 无 | 有 |

`Qmi.ClientLoc` 的设置类方法只有：

```
set_engine_lock  set_nmea_types  set_operation_mode  set_server
```

**没有任何星座配置方法。** 要开北斗只能：
1. 手发 Qualcomm 私有 QMI 消息（`SET_GNSS_CONSTELLATION_CONFIG`），
   或
2. 直接写 modem NV 项

两条路都需要自己实现原始 QMI（AF_QIPCRTR socket + QMUX 封装），
且消息 ID 与 TLV 格式没有公开的可靠文档，属于盲试范畴。

### 检测方法（无需改动）

脚本：`gnss_beidou_check.sh`（已上传至 `/home/umeko/desktop-offline/`）

```bash
chmod +x ~/desktop-offline/gnss_beidou_check.sh
~/desktop-offline/gnss_beidou_check.sh 60
```

到**室外空旷处**运行，采集 60 秒，输出两条独立证据：

- QMI SV info 的 `system:` 字段（`compass` = 北斗）
- NMEA `$..GSV` 的 talker（`$BD` / `$GB` = 北斗，`$GP` = GPS，`$GL` = GLONASS）

判定结果：

- `BEIDOU_ON` → 北斗本来就是开的，不需要任何改动
- `BEIDOU_OFF` 且 GPS/GLONASS 有星 → 才需要在 modem 侧强开
- 全无 → 位置不够开阔，换地方重试

### 对"掉星"的实际作用

北斗在中国上空有 GEO/IGSO 卫星（仰角高、抗遮挡），能补 2–4 颗，
对城市峡谷有帮助。但**补不了硬遮挡**——之前轨迹里那次 103 秒中断，
是精度从 37 m 一路恶化到 100 m 后完全失锁，属于物理遮挡导致的卫星数跌破解算门槛。

---

## 6. 回滚

```bash
sudo cp /usr/local/lib/obd-power/gauge_power_service.py.bak-20261019 \
        /usr/local/lib/obd-power/gauge_power_service.py
sudo systemctl restart obd-power
```

---

## 7. 验证清单

### 挂起是否真的生效（关键）

**不能只看"屏幕亮不亮"** —— 失败时会回退成真关机，重新开机屏幕也会亮，很容易误判。

```bash
journalctl -u obd-power --no-pager -n 20
```

必须看到这一对，且 **`uptime` 不归零**：

```
SUSPEND_ENTER rtc_alarm=True battery=80
SUSPEND_RESUME online=False battery=80
```

如果看到 `SUSPEND_ERROR` + `reason: suspend-failed`，说明又走了回退路径。
再确认一次 `uptime`：连续增长 = 挂起成功；从几十秒开始 = 其实是重启。

- [ ] 拔掉 USB，20 秒后屏幕熄灭，`journalctl` 出现 `SUSPEND_ENTER`
- [ ] 插回 USB，屏幕自动亮起，`journalctl` 出现 `SUSPEND_RESUME`
- [ ] `uptime` 跨越挂起前后连续增长（未归零）
- [ ] `systemctl is-active obd-gauge-kiosk` 仍为 active，FPS 日志未中断
- [ ] 长时间停放（>2 天）后确认电量未过放

### GPS 与北斗

星座统计已并入常驻服务，随时可查：

```bash
python3 -c "import json;d=json.load(open('/run/obd-motion/state.json'));print(json.dumps(d['gps'],ensure_ascii=False,indent=1))"
```

字段含义：

| 字段 | 说明 |
|---|---|
| `satellites` | QMI 报告的卫星总数 |
| `systems` | 各星座颗数，`compass` = 北斗 |
| `constellations` | 按 NMEA talker 统计，含每颗 SNR（`GP`/`GL`/`BD`/`GA`） |
| `nmea_count` | NMEA 语句累计条数（引擎在输出 ≠ 搜到了星） |

**注意 `nmea_count` 会一直增长，即使一颗星都搜不到**——它只说明引擎在说话，
不代表有卫星。判断有没有星要看 `satellites` 和 `constellations`。

- [ ] 露天（非窗边）跑一次，确认 `constellations` 出现 `GP` 等条目
- [ ] 看 `systems` 里有没有 `compass`，确认北斗是否已启用
- [ ] 冷启动到首次定位的秒数，对比改前的 30–60 秒

### 为什么窗边测不出来

窗户（尤其双层/镀膜玻璃）对 1575.42 MHz 的衰减可达 20–30 dB，加上墙体挡掉半边天，
窗边常常是 0 颗。实测记录：2026-10-19 23:59 窗边，`nmea_count=44/12s` 但
`satellites=0`、无 GSV 条目。而同日 17:53 室外轨迹为 348 个点、精度 17–30 m，
说明**射频与天线本身是好的**，差别只在视野。

---

## 9. 回退记录（2026-10-20）：挂起方案抽干电池

### 现象

2026-10-19 夜间拔线挂起，次日发现电池被抽干（device 完全无 USB 枚举）。

### 为什么这个方案从根上不成立

**保住星历 = 必须给 modem 持续供电。** Qualcomm 的 GNSS 引擎跑在 modem 内，
星历只存在 modem 内存里。只要断电星历就没了，不存在"断电但保数据"的中间态。
所以这条路线的功耗下限就是 modem 待机电流，几十 mA 起，与关机（0 mA）永远不可能持平。

### 实测证据：它真的睡进去了，然后用 600 mA 把自己睡死

`journalctl --list-boots` 显示这一夜设备反复启动：

```
-5  10-19 19:26 → 23:50
-4  10-19 23:50 → 10-20 01:52
-3  10-20 01:52 → 02:09
-2  10-20 03:50 → 05:04
-1  10-20 07:28 → 08:17:57
 0  10-20 13:13 → 现在
```

最后一次（`-b -1`）的日志是关键，三条兜底依次尝试、全军覆没：

```
08:17:57  SUSPEND_ENTER rtc_alarm=True battery=99
08:17:57  rtcwake: /dev/rtc0：找不到设备: 没有那个文件或目录
08:17:57  SUSPEND_ERROR CalledProcessError(1, ['/usr/sbin/rtcwake', '-m', 'mem', '-s', '14400'])
08:17:57  Call to Suspend failed: Sleep verb 'suspend' is disabled by config
08:17:57  SUSPEND_ERROR CalledProcessError(1, ['/usr/bin/systemctl', 'suspend'])
08:17:57  kernel: PM: suspend entry (s2idle)
```

注意最后一行：**第三条兜底 `echo mem > /sys/power/state` 成功了**，系统真的进了 s2idle。

然后就没有然后了：

| 计数（`-b -1`） | 值 |
|---|---|
| `SUSPEND_ENTER` | 1 |
| `SUSPEND_RESUME` | 0 |
| `PM: suspend exit` | **无** |

`rtcwake` 因为 `/dev/rtc0` 不存在而失败，等于**一个硬件闹钟都没设**；
`usb-detect` 是唯一的唤醒源，而线已经拔了。于是它从 08:17:57 一直睡到电池耗尽，
设备彻底断电，直到 13:13 插线才重新开机。

**99% → 0，约 5 小时，3080 mAh ⇒ 平均约 600 mA。**
这就是 s2idle 在这台 mainline MSM8974 上的真实功耗——比正常运行低不了多少，
因为显示、modem、DRAM 的电源域根本没真正关下去。所谓"轻睡眠"名不副实。

### 两个独立的设计错误

1. **没校验兜底链路**：`arm_rtc_alarm()` 写 `/sys/class/rtc/rtc0/wakealarm`
   返回 True，但 `/dev/rtc0` 不存在，`rtcwake` 随即失败。前者掩盖了后者，
   日志里 `rtc_alarm=True` 是个彻头彻尾的假信号。
2. **没有"醒来确认"机制**：进入 suspend 前记录 `CLOCK_BOOTTIME`，
   恢复后核对差值，就能发现"根本没醒"或"睡的时间不对"，进而立即关机。
   原实现完全依赖"subprocess 返回 0"当作成功，而第三级兜底返回 0 之后
   进程是阻塞在 suspend 里的，永远不会执行到检查代码。

结论：**不是某个参数没调好，是这条路线的前提本身有问题**——
想保住星历就得给 modem 供电，s2idle 又省不下电，两头都要电，电池必然被抽干。


### 回退内容（`gauge_power_service.py`）

| 项 | 处理 |
|---|---|
| `step()` 中 `self.suspend_cable()` | 改回 `self.poweroff('cable')` |
| `Service.suspend_cable()` | 删除 |
| `Service.suspend()`（rtcwake / systemctl / sysfs 三级） | 删除 |
| `arm_rtc_alarm()`、`battery_capacity()` | 删除 |
| `LOW_BATTERY_PERCENT` / `RTC_SAFETY_WAKE_SECONDS` / `SUSPEND_POLL_SECONDS` / `MAX_SUSPEND_ROUNDS` | 删除 |

文件从 289 行回到 194 行，行为等同改造前：**拔线 20 秒倒计时 → `systemctl poweroff`**。

测试同步更新：删除 4 项挂起相关测试，新增 2 项
`test_cable_powers_off_after_countdown`（必须 poweroff）与
`test_no_suspend_path_can_be_reintroduced`（`Service` 不得再有 `suspend` 方法）。
本地 14 项全过。

### 后续如果还想缩短冷启动

只有这三条，都不依赖"让设备不关机"：

1. **星历预置 + 开机注入**（需定期从电脑传文件，XTRA 有效 7 天）
2. **本地时间/位置辅助**（libqmi ≥ 1.38 的 `--loc-inject-time` /
[LOCATION-BEARING LINE REMOVED]
3. **什么都不做**，接受 30–60 秒冷启动

任何声称"熄火后保持星历又不耗电"的方案，都违反 modem 需要供电这个前提。
