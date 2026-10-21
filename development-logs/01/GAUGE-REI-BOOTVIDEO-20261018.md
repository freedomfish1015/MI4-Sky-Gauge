# 小米4：绫波丽主题与 NERV 视频衔接（2026-10-18）

## 范围与保护

- 用户选择自己的长发绫波丽插画，不采用先前生成的短发头像。
- 原图：`[LOCAL-PATH]`。
- 项目副本：`[LOCAL-PATH]`，SHA256 `7ac1d793049569492083745af6dc37ec69db2a6cc6c2428c96e232584f0aeb9c`。仅界面等比例缩放，未修改原图。
- 仪表、设置页统一白/冰蓝，深色读数、红色告警；人物左侧独立区域，不遮挡数据。
- 保持原生1080×1920纹理、横屏布局、双线程增量刷新、BLE连接、PID选择、亮度、触摸权限、鼠标隐藏。
- 未修改电池、声卡、背光、触控驱动、ESP32固件或 boot 分区。
- 本轮读回 `/dev/mmcblk0p19` SHA256仍为 `5715032761b50157ea495d5dfb3d71b2b6de300f00ce7681f48f154dd9f67653`。

## 绘制修复与验证

- `gauge_sdl.py`：新布局；人物静态缓存；转速文字缩小避免碰刻度。
- 新布局暴露 Cairo 长圆弧重新分段导致的增量边缘漂移；改为固定5度圆弧片段，脏区向前覆盖一个片段。保留局部刷新，避免回到全帧重绘。
- `gauge_settings.py`：共享配色和原图小头像，设置逻辑不变。
- WSL Mi4Build：`GAUGE_TEST_NATIVE_SDL=1 SDL_VIDEODRIVER=dummy SDL_RENDER_DRIVER=software python3 -m unittest test_gauge_sdl test_gauge_settings test_boot_video test_boot_curtain -q`，31项全部通过，含真实SDL软件纹理测试。
- 预览：`rei-dashboard-preview-v3.png`、`rei-settings-preview/`。

## 视频需求和实现

- 源视频 `[LOCAL-PATH]` 保持不变。
- 预旋转1080×1920 MJPEG+PCM：`nerv-startup-1080-mjpeg.avi`，SHA256 `3f78b62ee579ee42e515352a86f40fb1d8d5df75d8ffd562823ae2d0d2d8f8f2`。
- `boot_video.py`：GStreamer音视频EOS为正常完成条件，播放器音量0.5，不增加硬件增益。45秒仅是失败保护，不是假装播放完成的定时器。
- `launch_boot_video.py`：播放结束后复用同一 SDL/KMS window/renderer，最后一帧保留到仪表首帧完成，避免关闭窗口时露出控制台。
- `/run/obd-gauge/boot-video.done` 防止应用重启重复播放；真实重启后/run重建，重新播放。正常写complete，异常写failed并安全回仪表。
- 此前单独播放器CLI测试结束会关窗口，用户看到的控制台正是此空档；正式启动器不走关窗口路径。
- 视频实际旧测试为361帧完整EOS、约21秒墙钟时间（约17fps），不是30fps。仪表刷新率与视频解码帧率分开，不能混称。
- 早期rootfs幕布`boot_curtain.py`只写fb0和隐藏光标；manager ShowStatus=no、printk0只压制可见状态，保留日志。
- 不再尝试修改Android boot header隐藏最早期内核文字；此前导致黑屏，已恢复。最早期rootfs前文字是否仍可见需实际重启观察，不能以服务重启替代冷启动验收。

## 手机安装路径

- 用户程序和图片：`/home/umeko/desktop-offline/{gauge_sdl.py,gauge_settings.py,assets/rei-reference.png}`。
- 原版备份：同目录 `gauge_sdl.before-rei-20261018.py`（SHA27e29e…）与 `gauge_settings.before-rei-20261018.py`（SHAc85498…）。
- 视频模块：`/usr/local/lib/obd-gauge/{boot_video.py,boot_curtain.py,launch_boot_video.py,girepository/GstVideo-1.0.typelib}`。
- 视频/首帧：`/usr/local/share/obd-gauge/{nerv-startup-1080-mjpeg.avi,nerv-first-1080.argb,startup-1080.argb}`。
- 单元：`/etc/systemd/system/obd-boot-curtain.service`，kiosk drop-in `obd-gauge-kiosk.service.d/50-obd-boot-video.conf`。
- 状态隐藏：`/etc/systemd/system.conf.d/80-obd-boot-status.conf`、`/etc/sysctl.d/80-obd-console.conf`。
- 音频由原有mi4-audio-init + user@1000/PipeWire初始化，未改驱动。启动器最多等待8秒，音频不就绪时记录无声降级。

## 本轮部署与回退

- 之前120秒boot-video安装安全定时器在讨论主题期间触发，恢复旧仪表；没有造成手机故障。本轮按旧文件精确hash检查后重新启用，保留所有`.disabled.<时间戳>`配置备份。
- `install_rei_boot.sh` 校验原文件与新文件SHA，备份后原子替换，启用视频和幕布，设置240秒独立恢复保护。
- 恢复脚本 `/usr/local/sbin/rollback-rei-boot`（项目`rollback_rei_boot.sh`）仅对匹配本次部署hash的两个Python文件恢复备份，禁用视频/隐藏状态配置，重新启动旧仪表。
- 手动恢复：`sudo /usr/local/sbin/rollback-rei-boot`。不写boot、不清数据、不回滚硬件修复。
- 旧脚本`rollback-obd-boot-video`只识别旧视频候选hash；本轮请使用新的`rollback-rei-boot`。
- 安装日志`rei-install.log`，运行证据`rei-runtime-status.log`。本文件后续追加实际验收结果。

## 本轮已取得的运行结果

- 新主题已部署到手机，应用进程active/running，NRestarts=0。
- `/run/obd-gauge/boot-video.done`：`{"status":"complete","complete":true,"frames":361,"last_pts":12.0}`，完整视频EOS后进入新仪表。
- 日志多数采样59.2fps，另有一条47.3fps；不能承诺恒定60fps。
- 两个新Python文件、原图SHA均与电脑一致。
- 软件检查通过后已停止`obd-rei-install-guard.timer`，防止等待外观反馈时再次自动回滚。手动回退脚本保留。
- 当前只做服务重启，没有重启手机；全开机文字隐藏和用户视觉/触控验收仍待确认。
