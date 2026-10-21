# 小米 4 GPS：日志诊断、兼容修正版与辅助数据实测

2026-10-20，手机通过 COM10 连接。本轮没有修改 boot、内核、充电策略、蓝牙或仪表界面。

## 已确认的事实

- 按北京时间筛选今天的 `.gnss.jsonl`（不能只按文件名的 UTC 日期），首轮统计 14,428 个采样，0 次有效定位，所有相关 CSV 均无坐标点。
- 07:30 左右偶见 GPS，07:39–07:40 偶见 GLONASS。记录中同一时刻最多一颗，GPS 最强约 27.5、GLONASS 31.6 dBHz；没有北斗报告。这不等于北斗被禁用。
- 14:04:17–15:20:54 连续约 76 分钟，无卫星报告，持续产生无定位的 GPGSA。不能把一切解释为正常冷启动，也不能仅凭这些日志断定天线损坏。
- systemd 日志证明定位进程多次 SIGSEGV。07:30:53 有卫星，07:30:54 崩溃；07:47:06 有卫星，07:47:07 崩溃。相关性明显，但尚无 native backtrace 能证明具体故障函数。
- 当前 remoteproc 三个均 running，LOC 正在发 NMEA/位置状态；不是服务完全没启动。当前室内依然 0 星、无定位。

## 部署的第一轮兼容修正版（不是已完成的搜星修复）

手机目录 `/usr/local/lib/obd-motion/`：

- `mi4_gnss.py` SHA256 `6a525d35b65c2f96901b2aa01c11ec4b5c7d6325bbc7eceee1172b004506c82a`
- `mi4_qmi_sv.py` SHA256 `93c91c5be3cbe21024c7acf8705031e577980e9ff565b34e3a2a357398c479bb`

不再调用卫星 `output.get_list()` 转换 GI 结构体数组。通过公开 libqmi C getter 借用 GArray，核验当前 GI 的结构体大小和所有偏移后复制最多 255 条记录；不修改所有权、不释放借用数组。检查 PyGBoxed hash 与 native repr 地址一致，不依赖 Python 对象内部偏移。若运行时接口不匹配则报告错误，不猜测 ABI。

新增 `faulthandler`，再次发生 native fault 时将 Python 栈写入 service journal；新增 `sv_indication_count`，并记录有效掩码允许的导航数据/仰角/方位信息。

重要限制：旧路径的 10,000 次合成信号测试也通过了，所以不能宣称已独立复现或完全根治旧版 GI 故障。兼容路径旨在绕开疑点并增加取证，需要真实卫星报告现场验证。

已验证：

- 8 项 GNSS/结构体测试，电脑与手机通过。
- 新 reader 在手机 10,000 次合成报告测试通过，含 GPS/COMPASS、多条与空数组。
- 21:23:58 重启 `mi4-motion.service` 部署；截至后续检查 active、NRestarts=0。没有真实卫星输入时不算证明已修复。
- 原文件备份：`/home/umeko/desktop-offline/backups/gnss-compat-before-pmawsqu3/mi4_gnss.py`
- 原 GNSS 文件 SHA256 `c4eeb6b9fb0621d4ad48caaae008b73edc5376b43afda0239fc5a30d302e7c0d`

回退：停止 mi4-motion，使用上述备份覆盖目标 mi4_gnss.py，再启动 mi4-motion。适配器可保留但不被旧脚本导入。不要回退其它 AI 的电池、屏幕或电源改动。

## 联网更新星历/XTRA 方案：有接口，尚未成功更新

只读查询 LOC 0x0036 返回实际服务器：

`[URL REDACTED]

电脑改用同域 HTTPS（正常证书验证）下载，文件 34,335 字节：

- `xtra3grc-20261020.bin`
- SHA256 `6c5d853bbf4899878b05ac1b28b712c7e8fa9c7875d42c35b55fa9cbb26cd062`
- HEAD Last-Modified：2026-10-20 13:28:15 UTC。后续文件会变，不得将这个 hash 当作永久版本。

首次只读 LOC 0x0037 返回有效期 TLV：`d015ee6700000000a800`。
依公开协议 `<uint64 UTC秒, uint16小时>`，是 **2025-04-03 05:00 UTC 开始，168 小时**，早已过期。
这也说明“每次 poweroff 一定抹掉全部辅助数据”的旧说法不成立，至少 modem 仍能报告一份旧数据的有效期。

`gnss_xtra.py` 为显式命令行工具：只允许 0x35/36/37/38，不会写猜测的 NV、不重置 modem、不删除辅助数据、不注入位置。注入必须提供文件 SHA256，每段最多 1024 字节、逐段验证响应和 indication，最后失败即停止。3 项 wire/status/time 测试在手机通过。

实测结果必须完整保留：

1. 34 段的第 1–33 段接受，第 34 段返回 GENERAL_FAILURE(1)，**未成功更新**。
2. 此后有效期变为 2026-10-20 13:00 UTC、0 小时；这不是有效辅助数据，失败注入改变了引擎报告，不能宣称缓存未变。
3. 标准 LOC 0x38 粗 UTC 注入接受，时间来自与 HTTPS 服务器日期相符的电脑时钟，不确定度明确设为 300,000 ms（不冒充 NTP 精度）。
4. 补时间后同文件重试一次，前 33 段接受，最后 INVALID_PARAMETER(3)。停止尝试；没有开启周期性重试或自动注入。

后续优先核对数据格式/固件兼容和最后分片校验，并取得具体失败原因。不要换成任意星历、不要强行跳过校验、不要通过修改固件版本检查掩盖失败。

## 对用户截图方案的建议

- 可在辅助数据过期或超过 7 天未成功更新时提醒连接 Wi-Fi/热点，但不要将“最后联网”当作“成功注入”。
- 应分别显示下载成功、modem 接受、有效期和真实定位状态；当前没有成功注入，不能显示已更新。
- 不默认强制禁用仪表；没有辅助数据仍应保留尝试自主定位的能力。
- 当前无 IP 定位、无坐标上传、无强制联网限制、无自动更新 timer。IP 粗位置不能替代真实 GPS 轨迹。
- 在数据注入尚未成功之前，不部署开机自动注入及硬性 7 天锁定。

## 下一轮取证

真实开阔处测试 5–10 分钟，观察 `sv_indication_count`、卫星详情、是否 fix 和 NRestarts。若再次崩溃，先读取含 faulthandler 的 journal，不应直接归因于“信号弱”。当前没有要求用户再次外出，也没有把室内零星结果当作天线故障。

日志在本目录：`gps-log-diagnosis-20261020.log`、`gps-crash-diagnosis-20261020.log`、`gps-native-stress-20261020.log`、`gps-compat-install-20261020.log`、`gps-xtra-injection-20261020.log`、`gps-xtra-time-trial-20261020.log`、`gps-compat-live-verify-20261020.log`。

## 协议依据

- [libqmi 上游 GArray 类型标注修复（相关线索，非本机故障证明）]([URL REDACTED])
- [AOSP Qualcomm LOC 协议：辅助数据、UTC、有效期]([URL REDACTED])
- 本轮下载官方 Ubuntu libqmi 1.35.2 源码核对 wire schema：`[URL REDACTED] `/root/mi4-gnss-fix/`。没有 GitHub 直接文件下载。
