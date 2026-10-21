# 轨迹卫星星座记录（已部署）

2026-10-20，Asia/Shanghai。只修改定位采集和轨迹文件格式，未更改北斗NV、基带、boot、主题、IMU算法或已有轨迹。

## 使用

在手机原有“G值 / GPS”设置页开启轨迹记录即可，无需新开关。
结束后关闭记录，再连接电脑读取 `/var/lib/obd-motion/tracks/`。
文件名为UTC时间，因此北京时间凌晨10月20日的记录可能以20261019开头。

同一行程会生成三份文件：

- `.csv`：原六列保留，新增 observed_systems、signal_systems、used_ids、used_systems、used_systems_complete、sv_report_available。
- `.gpx`：标准轨迹点和时间保持，扩展命名空间 `urn:mi4-obd:gnss:2` 保存同样的卫星摘要。
- **`.gnss.jsonl`**：每秒一条，记录原始QMI卫星明细、每星座颗数、有效信号颗数、参与解算的卫星ID、可确认的参与星座，以及GSV/GSA原始报文。**没有定位成功也会写入**，便于排查完全没有轨迹点的行程。

旧CSV/GPX不会被转换、补写或覆盖，仍没有历史星座信息。

## 字段解释，勿误报

- `observed_systems`：新鲜QMI卫星报告中包含的卫星数，不等于收到良好信号，也不等于用于定位。
- `signal_systems`：以上卫星中SNR>0的数量，不是精度承诺。
- `used_ids`：成功有效定位报告的可选 satellites_used TLV。若未提供，就明确标未知。
- `used_systems`：把used_ids与同时段QMI卫星明细做唯一ID匹配得到。compass/bds统一记为beidou。ID重复或缺少星座明细时不猜测，保留unresolved_used_ids，used_systems_complete=false。
- 空字典不表示星座关闭。看sv_report_available/used_ids_available/used_systems_complete区分未知和确实无报告项。
- 卫星、参与解算列表和NMEA报文均只接受3秒以内的信息，避免旧北斗报告一直被算成当前接收。
- 不通过GP/GN一个前缀猜整个定位方案。GN是混合talker，原始报文保留待分析。
- `.gnss.jsonl`只额外记录GSV/GSA，不采集含坐标的原始GGA/RMC。轨迹坐标仍留在原CSV/GPX，不上传网络。
- 原有总256MiB/单行程64MiB上限保留，新日志也计入容量。达到上限停止，不自动删旧行程。

## 代码、验证和备份

PC目录 `[LOCAL-PATH]`。
运行目录 `/usr/local/lib/obd-motion/`：

```
mi4_gnss.py          c4eeb6b9fb0621d4ad48caaae008b73edc5376b43afda0239fc5a30d302e7c0d
mi4_motiond.py       74b740ef1529e3000e4f4e90a11cb56dd2db369deadac66c6e3acb7d4871cb8e
mi4_satellite_log.py 9c55bb12df4a3920e5fb7554179abed63bc2dbff5f1f7a2e5edf6d5ce93bcc00
```

备份 `/root/mi4-satellite-recording-before-20261020-rBTIe5/` 保存原有两文件。
部署包 satellite-recording-20261020.tar.gz，SHA256 `83c265716f71af3b332aadb369a942991a1732a3a16eda0fe7d8204ceaf2ec0a`。
安装器 install_satellite_recording.sh 有前版本hash、未录制检查、编译/单测、备份和异常回滚，当前版本不能直接重复安装。

桌面相关21项测试通过，手机独立11项通过。测试均使用临时目录，没有把模拟北斗数据写到真实行程。

另外执行全目录unittest discover共127项：1失败、5错误、2跳过，**不是全量通过**。
失败项位于未修改的开机视频测试（preset_source mock签名、frames_shown初始化、实机脚本在桌面运行的路径检查）和SkyGauge测试（桌面缺dbus_fast、配对等待超时）。本轮未修改这些模块，也没有完整前版本基线，不能仅凭本次运行断言它们一定是历史故障；没有扩大范围修复这些问题。卫星记录相关测试与真实手机录制验证独立通过。

真实设备验证：`verify_satellite_recording.py`通过现有MotionClient开启6秒记录再恢复关闭，无假定位注入，生成
`20261019T163901Z-2887511852855.{csv,gpx,gnss.jsonl}`。
6条卫星快照，末条searching、sv_report_available=false、NMEA3条，GPX XML可解析、CSV新列正常。
这是一段**录制链路验证**，不是北斗搜星成功证据；日志 satellite-recording-verify-20261020.log。

部署后mi4-motion、obd-gauge-kiosk均active，IMU ready已验证。当前录制关闭，等待用户正常使用。

## 北斗开启任务仍未完成

已知基带EFS gnss_config值是07000000，但尚未核实与这版固件匹配的NV位定义；本次没有改它。
QMI0x88是测量报告配置，GPS/BDS/混合三组都返回失败，不能当北斗开关。详细过程见BEIDOU-CHECK-20261020.md。
下一次真实使用的新日志能提供星座证据，旧轨迹不能补出这些信息。
