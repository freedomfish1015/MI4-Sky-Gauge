# mi4-sky：LOG 直传与 RaceChrono CSV v3 交接

更新时间：2026-10-21，Asia/Shanghai。

## 命名与当前状态

- 小米 4 手机仪表端今后统一叫 **mi4-sky**。
- ESP32 的 SkyGauge 主表是另一台设备，本轮没有修改它的固件。
- 手机的“G值 / GPS”设置标签已换为“LOG 数据传输”。G 值算法、GPS、轨迹记录和行程联动保留；原自动回中选项此前已移除。
- 手机当前是单个 **小程序内部扫描**二维码，不是微信小程序启动码，也不是系统相机通用 Wi-Fi 二维码。
- 微信小程序源码仅为草稿，未配置正式 AppID，未真机验证、未发布。用户要求先完成 mi4-sky 端，不继续推进小程序端。
- 当前热点 SSID：`mi4-sky`；密码沿用原随机密码，显示于仪表，不在本文记录。

## 手机已部署

应用文件：`/home/umeko/desktop-offline/gauge_settings.py`、`gauge_log_transfer.py`。

后台：`/usr/local/lib/obd-log-transfer/` 下的 `log_hotspot.py`、`log_download.py`、`racechrono_export.py`、`control.py`、`download.html`、`download.js`。

服务：`obd-log-transfer.service`（root 按需热点）、`obd-log-download.service`（umeko 非特权只读下载）。均没有开机 enable；开启 15 分钟后自动关闭。只赋予 UI 精确 helper start/stop 的 sudo 权限，不允许任意 root 命令。

NetworkManager 保持原有 masked 状态，不启用全局 DHCP/DNS，不改路由/NAT，不替换 Wi-Fi 固件。hostapd、dnsmasq、iw 和必需动态库由国内清华 Ubuntu 镜像下载的 ARMhf deb 解包在后台 tools/，没有全局安装软件包或运行其 postinst。

热点：2.4GHz channel 6、WPA2、地址 `[IP-ADDRESS]/24`，DHCP `[IP-ADDRESS]–60`。不提供互联网；不采用 captive portal、不监听 80 端口、不劫持 DNS。现有其他 Wi-Fi 连接被检测到时拒绝抢占。

二维码 JSON 协议（以下全是示例，不是真实密钥）：

```json
{"kind":"skygauge-log","v":1,"ssid":"[REDACTED]","password":"[REDACTED]","host":"[IP-ADDRESS]","port":8787,"token":"[REDACTED]"}
```

`kind` 的旧协议字符串为兼容而保留，不是产品名称。token 每次开启共享重新生成，关闭共享即失效。小程序必须先打开，再用 wx.scanCode 读取，确认 Wi-Fi 连接后调用局域网接口。不要宣称普通微信扫一扫能启动尚未发布的小程序。

## API 与只读安全

- 监听仅 AP 地址 `[IP-ADDRESS]:8787`，不是 [IP-ADDRESS]。
- `/s/<token>/`：离线浏览器备用页。
- `/s/<token>/api/files`：schema `skygauge.log-transfer/1`。
- `/s/<token>/file/log/<telemetry-*.jsonl>`：原始 LOG 完整行快照。
- `/s/<token>/file/track/<允许的 csv/gpx/gnss.jsonl 文件名>`：GPS 原文件。
- `/s/<token>/file/racechrono/<telemetry-*.racechrono.csv>`：按需转换 RaceChrono CSV v3。

路径与文件名白名单、O_NOFOLLOW、防目录穿越、Host 与 token 校验、128 MiB 文件上限、HEAD/单段 Range 均已实现；不记录含 bearer token 的访问 URL。不提供删除、上传或任意路径浏览接口。未关闭的 GPS 行程及关联 CSV 导出返回 409。

导出列表中的 `kind=racechrono` 为虚拟文件，`generated=true`、`size=0` 表示尚未转换，**不是零字节文件**。界面应显示“按需生成 CSV”，实际下载 Content-Length 才是输出字节数。`source_name/source_size` 指向原始 JSONL。保留原始 LOG 的同时新增 CSV 导出，不改变原有记录器与轮转策略。

## RaceChrono CSV v3 的语义

用户明确选择：与 RaceChrono CSV v3 格式一致，供电脑或其他分析软件使用；**不是为了导回 RaceChrono App**。

格式有 `Format,3`、会话元数据、空行、通道名、单位、数据来源三行；数据行基于 UTC Unix 秒。OBD km/h 转 m/s，温度单位使用 `.C`，GPS/OBD speed 通过不同 source 区分。标题如实写明 mi4-sky 兼容导出，不冒充 RaceChrono 官方生成。

导出实际存在的 GPS 经纬度/精度/速度、OBD 转速/车速/节气门/档位/水温/油温/电压/负荷，以及加速度。缺失或无效数据留空，不导出 UI 默认值、虚构 GPS、推算圈号或假装有刹车踏板。

- `x_acc/y_acc/z_acc`：原记录的原始传感器轴，可能含重力；不是车辆坐标标定结果。
- `acceleration_1/2`：过滤后的显示 X/Y G；不是 RaceChrono 的 vehicle lateral/longitudinal G，不伪装成这两列。
- `digital_1=1`：源记录明确标为模拟器；`0` 仅代表未标记为模拟，不保证是实车。
- 原日志是约 10 Hz 快照，OBD 低频值可能重复；不插值、不声称独立 ECU 更新率 10 Hz。
- UTC 或单调时间回退会切换 fragment；保留真实时间，不伪造连续 GPS 时钟。

按需转换在非特权下载服务中运行，不在仪表渲染线程中运行。一次只转换一个 CSV，其他请求返回 429。临时文件匿名、关闭即释放；源文件不改写。30 秒转换期限、256 KiB 单行上限、128 MiB 输出上限。

参考依据：

- RaceChrono 作者说明 CSV v3 是导出用途：[URL REDACTED]
- 官方通道 / 设备标识：[URL REDACTED]
- 实际 v3 文件的元数据/表头结构参考（未复制其实现）：https://github.com/ClassicMiniDIY/UltraLog/blob/main/exampleLogs/racechrono/session_massa_finalese_v3_excerpt.csv

## 实测与限制

- PC 32 项自动测试通过：原下载安全、UI 路由隔离、单二维码协议、CSV 单位与缺失值、模拟标识、Range/HEAD、记录中拒绝与并发限制。
- 手机实测：8 个原始 LOG 对应 8 个虚拟 CSV；一份原始 LOG 转为 **4,772 行、528,538 字节、耗时 3.130 秒**。
- 原始源文件 SHA256 转换前后一致；仪表服务恢复到 active，PID 当时 1452。
- 尚未在实际电脑分析软件中导入验证，不承诺所有第三方软件都支持全部自定义通道。
- 尚未用微信真机完成扫码连 Wi-Fi / 下载全链路；需要 AppID。不要将草稿宣称成已上线小程序。
- 本轮不重启、不刷分区，OCV/WLED/音频/触摸/GPS/蓝牙/原生 1080p 渲染和启动逻辑未改。

## 校验与回退

原 LOG 页面安装前备份：`/home/umeko/desktop-offline/backups/log-transfer-before-9v8tuf1o`。

单二维码更新前：`/home/umeko/desktop-offline/backups/mi4-sky-pairing-before-atjnr0i2`。

CSV 更新前：`/home/umeko/desktop-offline/backups/mi4-sky-racechrono-before-xx9fv8l0`。

各备份均有 installed/protected JSON 与源码。回退需核对当前 hash，先停热点/下载服务，再恢复对应备份文件，最后重载仪表；不要删用户 LOG，不要回刷旧 boot 镜像。安装脚本是一次性 hash-guarded updater，不应直接重复运行。

当前关键 SHA256：

```text
gauge_sdl.py         a541e6c531255652d42a9f49c8bb255b6b34e2df5d1e1e0d04074ae1acfe1dfc
gauge_settings.py    74406f4bce2646cb30f1a2a128fc9fe05a0594ff54520923ad99ce4f4c815664
gauge_log_transfer.py a83b6f0ab4d39b91633c62ba63e66b89899b52710229d9589a7a4c080afa3f4a
log_hotspot.py      295bf44c1139d3de73357154a4d63ecb0b5cdc81ba38962c76f20a749d2952e5
log_download.py     d163a70b19a1753d9e0d6cd57b52d5670af89e2249c925e7d92dcd28e470cfbc
racechrono_export.py 5df16260ec28ea5f5e20ce47dd5526a2e41472b04320ba863b114d6b53ff8e64
download.js         1eb0c7087c3c6f76e6a468b9f56cbbdd6fb9af8dc03de387de2e230c2a4fe501
```

PC 实际项目：`[LOCAL-PATH]`。**不要把 PC 根目录的 gauge_sdl.py/gauge_settings.py 整体覆盖手机**，那里有另一项未部署的调试待机修改。本目录 settings 为验证过的基线定点修改版。

后续顺序：先确认仪表 LOG 页面单二维码显示；电脑分析软件验证 CSV 样例；用户拿到 AppID 后继续小程序真机验证与发布。不要擅自创建小程序账号或索要 AppSecret。
