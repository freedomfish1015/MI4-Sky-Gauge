# 2026-10-21：第二轮启动优化与控制台光标（已安装、重启通过，早期光标仍待处理）

> 后续早期光标已通过单参数RAM测试且经用户授权永久保存，正常重启读回参数生效；见`CURSOR-PERSISTED-20261021.md`。当前完整boot SHA已变为724783b32b5b09dd53245ec42277df4ef3b85cd1da7560ced1c0caaa92da8d2b，仅Linux cmdline扇区改变，内核/DTB/ramdisk和lk2nd未变。下文“待处理/未写boot”为本文件当时阶段。

## 重启及用户视频后续证据

COM10已在本轮重启后返回，日志`fast-boot-after-reboot-20261021.log`：BMS从uptime6.461秒运行至10.715秒，成功；kiosk从12.373秒激活，实际进程12.89秒开始，首帧**19.50秒**，稳定58.9–59.4FPS、NRestarts=0。光标两个sysfs值均为0，电量92%、约4.218V。首帧只比上一轮19.79–20.09秒快约0.3–0.6秒，**不得宣称本轮显著提速或已达到15秒**。BMS提前后实际耗时增加至4.25秒，其他设备/进程资源竞争仍限制收益。

用户随后提供25.37秒HEVC视频`[LOCAL-PATH]`。已用ffmpeg按1FPS查看全流程，并对左下角按4FPS分段提取查看：约3–5秒Sky Gauge静态图、约6秒后黑屏、约24秒进入仪表；左下角早期有间歇亮点，当前rootfs运行后cursor=0不代表内核接管之前已隐藏。不是仪表阶段的SDL鼠标；精确来源仍需更早阶段验证，不应凭细小压缩亮点断言已定位到具体函数。查看产物位于`startup-video-review-20261021/`。

进一步只读分析：热缓存下headless cProfile总1.295秒，不能与冷启动GUI6.618秒直接对比；DRM设备没有可直接使用的systemd dev-dri-card0.device激活时间。尚未改动全局udev等待、CPU调频、音频、用户会话或驱动依赖。

继续读取时COM10再次消失（用户可能拔线拍摄，但原因未确认），因此没有继续改引导或连续重启。下一步需重新USB连接。若必须消除rootfs以前的光标，需评估只添加内核`vt.global_cursor_default=0`等更早方案，**不能照抄历史quiet_boot.py**：该旧脚本曾移除console=tty0并组合多参数，导致黑屏，写功能已禁用。先基于当前真实boot做单项内存测试，再讨论持久化；不要拿旧boot覆盖Sky/WLED/OCV/音频修复。

## 请求与此前已验收版本

用户已确认上一轮无动画版本从Sky Gauge静态图直接进入仪表，没有白闪或文字；随后补充仍能看到闪烁光标，要求继续提速。此前无动画首帧19.79秒，用户自己再次启动的日志首帧20.09秒，均为Linux uptime，不含原厂引导计时。

本轮**没有修改boot/aboot/logo、BMS驱动代码、仪表主代码或设置源码**。只新增rootfs启动顺序/光标配置，留有精确回退。

## 证据与修改

1. 系统原`global_cursor_default=1`，而fbcon/cursor_blink已经为0。只写DECTCEM隐藏当前光标，并未禁止后续VT状态重建时的默认光标。
   - 新`quiet_boot_fast.py`写`/sys/module/vt/parameters/global_cursor_default=0`、`/sys/class/graphics/fbcon/cursor_blink=0`。
   - 对tty1和活动tty0发`ESC[?25l`；保留原printk抑制。
   - 不解绑fbcon、不切换KD/VT、不重画fb0、不改内核参数或引导分区。
   - `95-fast-quiet.conf`只替换既有curtain单位的ExecStart，旧90-direct-quiet配置保留。
   - 安装后两个sysfs值均已读回0。**rootfs脚本运行前的内核/引导阶段仍可能出现光标，需用户实机观察，不能把读回0当全程视觉验收。**

2. `mi4-bms-fixed.service`原普通服务有默认After=basic.target/sysinit.target；本次检查实际启动于Linux12.37秒，完成13.65秒，阻挡kiosk。
   - 新`mi4-bms-fixed.service.d/90-bms-early.conf`设置DefaultDependencies=no，避开这两个隐式等待。
   - **保留原After=systemd-modules-load.service、local-fs.target，以及Before=obd-gauge-kiosk.service/upower.service。** 另保留/明确remount及shutdown顺序。
   - 原BMS脚本有等待native驱动/异常回退，未修改；未实时重载/重绑BMS，顺序调整下一次启动才生效。
   - 安装后读取After/Before确认：不再有basic/sysinit等待，modules-load/local-fs和Before=kiosk仍存在。

## 安装与验证状态

安装器`install_fast_boot_20261021.py`检查手机app/单位SHA、外部供电、电量>=20%、充电模式normal、文件不存在和payload清单。systemd-analyze verify无依赖环；安装前后读取三个分区全SHA一致（只读校验）。未重启仪表/重绑BMS，先仅restart光标抑制单位。

备份：`/home/umeko/desktop-offline/backups/fast-boot-before-1w72yfmr/`，含before.json和installed.json、原分区和源文件哈希。安装器输出`FAST_BOOT_INSTALLED; CURSOR_DEFAULT_OFF; BMS_INIT_UNCHANGED; NO_PARTITION_WRITES`。

测试：电脑13项（fast_boot+direct_gauge）和手机13项均通过；随后电脑加curtain合跑16项通过。测试故意模拟缺sysfs/tty的日志不是实际安装失败。

重启前93%、约4.22V，`/run/obd-motion/state.json`的recording=False。首次sudo -n reboot提示需密码，**没有发生重启**；随后在持久串口中sudo -v后成功发出reboot。COM10随后消失，正在等待启动返回及用户屏幕反馈，暂不能报告本轮加速秒数或视觉成功。

## 文件与SHA

- `/usr/local/lib/obd-gauge/quiet_boot_fast.py`：d247164171286c4500b0edf3710db51fcaa2acd3ffb2e2ed3798ef160e260fc4
- `/etc/systemd/system/obd-boot-curtain.service.d/95-fast-quiet.conf`：7d792b1e649dd473ce0a2e54a53e7256fa171977c7076a432cd670d11a853a6b
- `/etc/systemd/system/mi4-bms-fixed.service.d/90-bms-early.conf`：16d664d8bf90c91537a5bf70fcc89ff3245b123d7cadddb011f65f957cc2a0d2

电脑所有文件在`[LOCAL-PATH]`。

## 回退

`rollback_fast_boot_20261021.py`当前先保存在电脑；传到手机后以sudo执行。只校验并删除上述两个95-fast-quiet/90-bms-early覆盖文件，daemon-reload，恢复上一轮quiet单位，**保留无动画启动**。不修改app、不重绑实时BMS，正常BMS顺序下次启动恢复。新quiet脚本保留但不再调用，内核cursor默认0继续保留到本次关机，不影响使用。

如果手机未返回，先收集用户屏幕状态、USB枚举，不连续强制重启。不可因连接消失就盲刷整个boot或覆盖其他AI的硬件修复。

## 对上一轮文档的更正

`90-direct-gauge.conf`中的空Wants=没有从合并依赖中移除原单位Wants：本轮`systemctl show`仍列出user@1000.service、mi4-audio-init.service。上一轮文档“取消显式Wants”只反映配置意图，**实际依赖没有清空**；它们本身不在仪表After列表，移除动画的测量结果仍有效。本轮没有为了提速禁用音频或用户管理器。
