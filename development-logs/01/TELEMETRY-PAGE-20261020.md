# 小米4：直连 OBD + 实时遥测 LOG

2026-10-20 已部署，用户确认「页面、曲线和返回都正常」。

## 本轮改动

- 删除蓝牙设置中的旧 SkyGauge 从机模式入口及该模式工作线程分支。
- 设置只接受 direct。旧配置若选择 sky，优先恢复 connections.direct；无已保存直连地址时禁用连接，绝不把 Sky 主机 MAC 当成 OBD 适配器。
- 已保留手机的 bmw.fg 车型、[BT-ADDRESS] 直连目标、四角窗口配置及 41% 亮度。
- 仪表向下滑进入 LOG；上滑或左上返回回仪表。
- GT7 分轨时间图风格，沿用当前浅色主题。最近30秒，转速、车速、节气门、X/Y 加速度，G范围±2.2。
- 暂停曲线是复制当前窗口；后台仍采集/记录。开始/停止记录按钮独立控制文件，不影响实时曲线。
- 原生1920×1080横屏绘制。图表约10Hz刷新，与仪表原有垂直同步渲染路径分开；没有改内核/boot、音频、电池、GPS或启动视频。

## 日志

手机目录 `/home/umeko/.local/state/obd-gauge/telemetry/`

`telemetry-<UTC时间>-<随机后缀>.jsonl`，schema `mi4.telemetry/1`。

默认启动应用自动记录；10Hz目标快照率（繁忙时会低于10Hz），不是ECU采样率。
只记录原始 source 快照，不记录启动扫针或动画插值。
每条包含UTC、单调时钟、五路曲线值、其他已采集 PID、蓝牙连接状态和车型/地址上下文。
G使用已校准安装坐标 display_g；传感器未就绪/未归零时为null。
缺失/非有限数值严格写null。断线没有模拟值。相邻OBD快照可重复同一条较低频ECU读数，header明确说明。
节气门只有数据源实际提供 obd.throttle 时有曲线；未因画图额外查询不受车型支持的PID。

后台有界队列256项，写入异常/丢弃计数显示在页面底部；内存历史620项。
文件每个最大5MiB，最多8个（约40MiB），循环淘汰最旧的自有telemetry文件。
1秒左右刷新缓冲，正常退出关闭文件；突然掉电可能丢失末尾缓冲，不是安全关键数据记录器。
GPS轨迹 `/var/lib/obd-motion/tracks/` 完全独立，本轮未修改、未删除。
无上传网络功能，也未接入/更改用户之前验证的 BLE ELM 桥接模拟程序。

## 文件与验证

电脑源目录 `[LOCAL-PATH]`。
手机应用目录 `/home/umeko/desktop-offline`。

- gauge_settings.py：40c0ee13de73023dbbc632547eefa0db4b39702628224319fb6fb9a98911e04f
- gauge_sdl.py：de2981736a26aacccdcae822b98d505ad5b5f59455911fdf2a7200442352ba64
- gauge_telemetry.py：6dcdb5de73ef6726485205bdb1a9a6a12027ae0500daae5eef7ab1421c79b19a
- test_gauge_telemetry.py：新增7项，通过手机Python真实执行。
- 桌面相关回归两组共96项，94通过、2跳过；非全仓全量测试声明。
- telemetry-preview.png：仅桌面合成数据视觉检查图，未写入手机日志。
- telemetry-install-20261020.log、telemetry-device-tests-20261020.log、telemetry-verification-20261020.log。

应用服务 active，验证时 NRestarts=0。手机真实日志包含 G 值，OBD不在场则rpm/speed/throttle为null。
启动后实测仪表FPS有约17–59波动，不应把本轮实现描述为稳定60FPS；没有做隔离性能归因。
用户已实测确认页面/曲线/返回正常。真实OBD车况曲线须下次有适配器时验证，不等同于台架G值通过。

## 备份 / 回退

应用和原始设置完整备份：
`/home/umeko/desktop-offline/backups/telemetry-before-20261020-010541`

只在需要回退且确认后执行：

```sh
sudo systemctl stop obd-gauge-kiosk.service
cp /home/umeko/desktop-offline/backups/telemetry-before-20261020-010541/gauge_settings.py /home/umeko/desktop-offline/gauge_settings.py
cp /home/umeko/desktop-offline/backups/telemetry-before-20261020-010541/gauge_sdl.py /home/umeko/desktop-offline/gauge_sdl.py
cp /home/umeko/desktop-offline/backups/telemetry-before-20261020-010541/settings.json /home/umeko/.config/obd-gauge/settings.json
sudo systemctl start obd-gauge-kiosk.service
```

恢复后新gauge_telemetry.py留在磁盘但不会被旧版本加载；不要删除已有日志，除非用户要求。
