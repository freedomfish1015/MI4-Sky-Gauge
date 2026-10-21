# GPS / LOG 行程联动

开始 GPS 记录后，仪表根据 motion daemon 的实际 recording / track 状态结束独立 LOG 文件，开启关联同一轨迹 basename 的行程 LOG。GPS 停止后 LOG 停止，不自动恢复独立记录。实时曲线保持更新，暂停曲线按钮仅冻结画面。

- 轨迹页与设置页的开始/停止入口都有效。
- 联动期间在 LOG 页点停止也会请求停止 GPS，收到 daemon 确认后一起停止。
- 独立 LOG 仍可在 GPS 停止时手动开启。
- GPS 无定位时仍记录车况/G 值，GPS 坐标为 null，不复用旧坐标。
- LOG 每条含 trip、UTC、单调时间及 GPS fix/UTC/经纬度/精度/速度；文件头 gps_track 指向原 CSV 名。GPS/CSV/GPX/.gnss.jsonl 保存机制不变，不合并成一种文件。
- 原 GPS 文件在 /var/lib/obd-motion/tracks；LOG 在 ~/.local/state/obd-gauge/telemetry。可由 trip 关联，样本率不同：LOG 10 Hz，GPS 按定位更新，重复位置不代表新定位。
- 原 LOG 存储轮转上限仍为 5 MiB × 8 文件，长行程可分文件；不是无限保存。历史轨迹不受 LOG 轮转影响。
- 应用重启后如 GPS 仍在记录，则新 LOG 分片继续关联原 trip；应用未运行期间不会补造 LOG。
- 短暂读不到 motion 状态不据此停止 LOG；GPS daemon 已明确停止才停止。操作失败不伪报成功。

本次只部署 gauge_settings.py / gauge_telemetry.py；不修改 boot、硬件驱动、GPS daemon、蓝牙转发或配置。安装器 install_trip_recording.py 校验部署前 SHA256 并备份，备份路径见安装输出。

验证：test_trip_recording、test_gauge_telemetry、test_gauge_tracks；手机测试用临时目录，不开启生产 GPS 或写生产遥测数据。物理操作待用户确认。

已部署：备份 /home/umeko/desktop-offline/backups/trip-recording-before-20261020-020610。手机新增 5 项测试通过，桌面相关 48 项测试通过（其中 1 项跳过）。仪表 active / NRestarts=0；蓝牙转发 active，未重启该服务。

部署后 SHA256：

- gauge_settings.py: 25aeed4b2c206fbe65c1d8fdd329ee80a017e4e00d8c6547757690652f05ab38
- gauge_telemetry.py: 05442c4b17601bedbed39ed7d779638d9cc30626e10b29aaf042c61ed25e58ea

回退：停止 obd-gauge-kiosk.service，恢复备份目录内两个同名文件，启动服务。保留 GPS 与 LOG 历史文件。
