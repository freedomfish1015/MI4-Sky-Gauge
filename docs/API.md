# 数据与小程序接口

本文件描述现有实现，不是新增远程管理协议。接口事实源为services/log_transfer，行为改动时同步测试和文档。

## 单二维码

UTF-8紧凑JSON示意（占位符不能用于登录）：

```json
{"kind":"skygauge-log","v":1,"ssid":"mi4-sky","password":"<device-generated>","host":"192.168.73.1","port":8787,"token":"<session-token>"}
```

SSID/PSK用于本机热点；token用于本次共享。PSK安装后随机生成并持久保存，token每次共享变化；约900秒自动结束，可手动关闭。二维码含网络访问凭据，不上传公共识别网站，不把PSK/token写入公开日志。kind/schema沿用旧字符串是兼容协议，不因产品改名随意替换。

小程序：校验kind/v与预期本地host/port → 平台授权后连接热点 → 请求下列带token的接口。无已发布AppID；微信平台的域名、局域网、下载保存和iOS/Android差异需开发者真机处理，不承诺当前JSON能被微信扫一扫直接打开。

## HTTP（只读）

基址 `http://192.168.73.1:8787/s/<token>/`；端口根路径不开放，错误/过期token返回403；Host也校验，不是任意域名代理。支持GET/HEAD，无删除/上传/执行API。

| 相对路径 | 作用 |
|---|---|
| 空路径 | 离线HTML下载页 |
| app.js | 本地JS，无CDN |
| api/files | JSON目录：schema=skygauge.log-transfer/1，files数组 |
| file/log/NAME | 原始telemetry-*.jsonl，按完整换行快照下载 |
| file/track/NAME | 合法命名的CSV/GPX/gnss.jsonl轨迹附件 |
| file/racechrono/NAME | 按需生成*.racechrono.csv，不修改源JSONL |

目录字段包括kind、name、size、modified（UTC ISO8601）、recording、url。虚拟CSV另有generated、source_name、source_size、format；size=0不代表下载是空文件，应发请求获取真实长度。

文件下载支持单段Range和HEAD；200完整、206分段、416范围无效，404文件不存在，409活动行程暂不可导出。RaceChrono转换有源大小/行长/输出/并发上限。前端使用返回的url，不接受用户提供任意系统路径。

## 本机状态/控制（不是HTTP管理接口）

- `/run/obd-motion/state.json`：IMU、GPS、卫星与记录状态。
- `/home/umeko/.config/obd-gauge/motion-control.json`：本机受限运动/记录控制，由已有客户端与daemon处理。
- `/run/obd-log-transfer/state.json`：共享阶段与显示状态；`session.json`为当前会话。
- `/usr/local/lib/obd-log-transfer/control.py start|stop`：本机sudo白名单操作，不直接开放给网页。
- LOG：`~/.local/state/obd-gauge/telemetry`；轨迹：`/var/lib/obd-motion/tracks`。
- 配对：`/etc/mi4-sky/sky-peer.conf`，仅root维护。不能从二维码传入shell、设备路径或任意主表地址修改命令。

## RaceChrono CSV v3兼容输出

见racechrono_export.py的COLUMNS。统一区分GPS速度和OBD速度，速度导出m/s，原始加速度通道与动态显示通道不冒充车辆标定轴。无GPS不编造位置/圈数，无刹车油门信号不补估计值，模拟源按行标记。目标是电脑/分析软件兼容，不保证直接导回RaceChrono App。
