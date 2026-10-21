# 2026-10-21：取消开机视频，直接启动仪表（已部署并重启实测）

> 最新光标修复已永久保存，正常重启后参数生效；完整boot SHA为724783b32b5b09dd53245ec42277df4ef3b85cd1da7560ced1c0caaa92da8d2b，内核等硬件payload未变。详见`CURSOR-PERSISTED-20261021.md`。无动画启动继续保留，普通重启首帧19.53秒。下面“尚待处理/未写boot”只描述早先无动画阶段。

> 用户已确认无动画直接进入仪表、无白闪或文字。后续补充早期光标仍闪，已做rootfs光标默认关闭和BMS提前初始化；重启首帧19.50秒，收益有限，早期光标视频仍需继续处理。详见`FAST-STARTUP-CURSOR-20261021.md`。下文关于Wants被清空的配置意图也以该文件的实际依赖更正为准。

## 用户意图和当前结论

用户明确要求取消开机动画以缩短开机时间。原先“必须播完视频再进仪表”的要求已被本次请求取代。

已跳过 NERV 视频、GStreamer 解码、音频就绪等待和视频 warmup/join；保留已刷好的 Sky Gauge 静态引导图和隐藏 lk2nd 文字补丁。**没有删视频素材/解码包，没有刷写 boot/aboot/logo，也没有删除蓝牙、GNSS、音频等硬件固件。** 基础驱动不是单靠删除动画就能省略的。

正常重启后串口自动返回，首帧标记与当前MainPID一致、NRestarts=0，1080×1920原生1:1输出、稳定约59FPS。仪表进程maps中的libgst匹配数为0。motion、BLE转发、bluetooth和充电模式守护服务仍active，充电模式phase=normal，亮度恢复901。

## 实测时间（均以Linux内核启动为零点，不是从插线开始计时）

旧版日志 `no-animation-startup-inspect-20261021.log`：

- BOOT_VIDEO_FIRST_FRAME：20.115秒。
- 视频完整播放约12.03秒，EOS：32.146秒。
- 仪表KMS接管：32.521秒；旧版未单独记录仪表实际首帧，因此这是近似对比基准。
- systemd-analyze：kernel5.202s + userspace16.772s =21.974s。此数不是仪表首帧时间。

新版真实重启日志 `direct-gauge-reboot-20261021.log`：

- DIRECT_GAUGE_START：uptime13.81秒。
- DIRECT_GAUGE_FIRST_FRAME：**uptime19.79秒**；本进程耗时5.982秒。
- 23.14秒后约58.9–59.4FPS；首个FPS统计窗口包含初始化，37.3FPS不是稳定帧率。
- systemd-analyze：kernel4.036s + userspace15.631s =19.667s。
- 相对旧版仪表接管时间约缩短12.7秒。不能据此承诺“接通电源19.8秒”，原厂引导/lk2nd仍在Linux计时之前。
- 首次热重载首帧3.879秒，不能把热重载耗时当冷启动总时长。

仅执行了系统正常reboot，**尚未完成拔线关机→插线冷启动的人工计时；视觉反馈正在等待用户**。取消动画不能消除全部前置约20秒的系统初始化。

## 实现和部署位置

- `/usr/local/lib/obd-gauge/launch_gauge_direct.py`：标准库启动器，直接调用手机现有gauge_sdl.main，不导入boot_video/launch_boot_video/GStreamer、不等待声音或OBD连接。
- 只在启动器内将Screen替换为局部子类；接管KMS前暂时背光归零，成功present首个仪表帧后恢复原亮度。持久/run标记和ExecStopPost处理被杀/失败后的恢复。不会每帧覆写用户亮度。
- `/run/obd-gauge/direct-gauge.ready`：pid、Linux uptime、进程elapsed；诊断写失败不会让仪表崩溃。
- `/usr/local/lib/obd-gauge/quiet_boot_direct.py`：只压低printk并隐藏tty1光标，不等待fb0、不重绘NERV第一帧、不改KD/VT/KMS，尽量保留已有静态引导图。
- `/etc/systemd/system/obd-gauge-kiosk.service.d/90-direct-gauge.conf`：替换ExecStart/ExecStopPost，取消仪表对user@1000/audio-init的显式Wants，只保留蓝牙/静态文字处理依赖。**mi4-audio-init本来已独立enabled，本轮未禁用音频修复。**
- `/etc/systemd/system/obd-boot-curtain.service.d/90-direct-quiet.conf`：原curtain单位改为上述纯文字处理，不再读8MB视频首帧资源。
- **obd-early-video-check.timer已disable并停止**。旧检查器会在100秒检查视频EOS，若不停止会误回退无动画系统。没有删除旧脚本、timer文件、视频或原单位。
- `mi4-bms-fixed.service`的启动前依赖仍保留；不能为了省1秒破坏电量修复。

安装器 `install_direct_gauge_20261021.py` 使用精确源文件SHA保护、payload清单、备份、首帧PID校验和异常回退。备份：

`/home/umeko/desktop-offline/backups/direct-gauge-before-202zyn9e/`

包含旧kiosk/curtain/video-check单位、timer状态、原app哈希和installed清单。

## 文件SHA256

- launch_gauge_direct.py：c6a85d6923df84102db8b89db7ada7f18ae23638bb6d3f86efe787a2a087de37
- quiet_boot_direct.py：412ccefce9410a17c75d330937c3abcf185b266e84f0fb692bad4e0917a1ba52
- 90-direct-gauge.conf：1fa9f1d0eb50e30ea2253da69bd06746f2428bf4839ea82246e60cf8da118434
- 90-direct-quiet.conf：71944056b72418ae2a038d858eeec12b617bcb4d65afc350897e8b9fe48ce923

手机现有gauge_sdl.py仍a541e6c5...1dfc；settings仍38eff83d...1e77（含充电按钮）。**电脑根目录gauge_sdl.py/settings.py有此前未部署修改，本次未拿它们覆盖手机。** 实际settings源在电脑`charge-mode-deploy-20261021/gauge_settings.py`。

## 测试和已知边界

- 新增`test_direct_gauge.py`八项通过，手机也八项通过：首帧前保持暗、成功present恢复一次、异常恢复、进程被杀后标记恢复、原0亮度保持、零媒体依赖、正确调用现有main、systemd命令重置。
- 与test_boot_curtain合跑11项通过。
- 额外跑旧视频回归时test_boot_video中三项旧mock不适配原有视频/warmup接口（lambda未接收preset_source、裸__new__缺frames_shown等）失败。没有修改这些历史视频代码或通过篡改断言掩盖；新直接启动链不使用它们。test_boot_warmup布线检查通过。
- 直接启动早于蓝牙完成，首次可能提示No powered Bluetooth adapters；后续自动重试，最终bluetooth active。本轮现场缺少AI Passport上游，DeviceNotFound是预期，**没有宣称重新验收真实OBD/Sky连接**。
- 保留所有电量、WLED、触摸、音频、G值、GNSS协议和关机/充电模式逻辑。未以删modem固件或禁用电池校正换启动速度。

## 安全回退

最后同步文档时COM10从电脑消失（此前重启已成功、仪表已持续正常运行），原因未确认；没有因此触发强制重启或刷机。**本文、更新后的交接索引、回退脚本当前只在电脑保存，未成功同步手机**。执行下面回退前，先把电脑`rollback_direct_gauge_20261021.py`通过既有USB文件工具传到手机同名位置。无动画启动器、两个覆盖配置和安装器均已成功部署并真实重启，不受文档同步中断影响。

USB串口COM10，umeko/sudo1234。仅在确认需要恢复视频时执行：

`sudo python3 /home/umeko/desktop-offline/rollback_direct_gauge_20261021.py`

脚本先校验本轮两个drop-in精确SHA，停止仪表，只删除这两个精确覆盖文件，daemon-reload，恢复旧视频入口，enable旧视频timer供**下次开机**检查，再启动仪表。原视频文件和单位都保留。不立刻启动旧timer，以免它在视频未播完时执行故障回退。不触碰分区或应用主文件。

新版本已不依赖充电模式保存的boot-video.done标记；旧标记保留无害。进入充电模式/恢复仍由原mi4-charge-mode.service执行，本轮未重新验证实体电源键退出。
