# 小米4外部电源联动（2026-10-18）

## 用户需求

1. 真正关机后接入充电线自动开机。
2. 已开机时拔线立即显示20秒倒计时，未按“保持开机”则安全关机。

## 已实现并启用

- `gauge_power_service.py`：root独立服务，100ms轮询真实`smbb-usbin/online`及`smbb-dcin/online`。任一个为1表示有外部电源；两个都明确为0才表示断线；传感器缺失/异常绝不当成断线。
- 只在观察到“有电→断电”边沿后计时。电池供电开机本身不弹20秒窗口。
- 使用单调时钟20秒，界面显示20、19…1、0；重插立即取消，点保持开机取消并保持到下一次接线/拔线。
- 到期前重新读取真实硬件状态，并确认UI最近3秒有心跳，才调用唯一固定命令`/usr/bin/systemctl --no-block poweroff`，不使用强制断电。
- 界面/视频未就绪或UI卡死时暂停在waiting_ui；恢复后重新给足20秒，避免看不到弹窗、无法点按钮时盲目关机。
- `gauge_power.py`：普通用户的Unix socket客户端及触摸模态框。模态框吞掉触摸，避免误操作下面的PID/亮度/连接；关闭后全帧恢复原页面，无残影。
- 只接受heartbeat/keep_on两个RPC，核验SO_PEERCRED UID；没有任意命令、任意路径写入或宽泛sudo权限。
- 插拔线与电池SOC/充电动画无关。没有写PMIC充电寄存器，没有更改现有电池、背光、音频、触控修复或boot分区。

## 手机路径

- `/usr/local/lib/obd-power/gauge_power_service.py` root拥有。
- `/etc/systemd/system/obd-power.service`，enabled/active。
- `/etc/systemd/system/obd-gauge-kiosk.service.d/60-obd-power.conf`让仪表依赖电源服务。
- `/home/umeko/desktop-offline/{gauge_sdl.py,gauge_power.py}`。
- 状态`/run/obd-power/state.json`，控制socket`/run/obd-power/control.sock`，root:umeko目录0750、文件0640、socket0660。
- 回退：`sudo /usr/local/sbin/rollback-obd-power`。仅禁用电源服务和本轮仪表修改，保留六边形HUD、开机视频及硬件修复。
- 原仪表备份`gauge_sdl.before-power-policy-20261018.py`，SHA256 `d22a56e167520eb36634265ffd04038a14b3b12d152531950b3ee7eaaf448679`。

## 验证

- 48项测试通过：含20秒边界、保持开机、重插、未知传感器、UI卡死、到期重插竞态、只发送一次固定安全关机命令、命令失败可见、socket UID/操作白名单、弹窗缓存及完整恢复、既有34项HUD/设置/视频测试。
- 实机先用`--dry-run --supply-root /run/obd-power-fixture`演示，未实际关机。完整倒计时后日志`DRY_RUN_POWEROFF_NO_ACTION`。
- 用户确认弹窗及倒计时正常；第二轮用户在1秒时点击“保持开机”，root状态变为held、仪表恢复，证据`power-policy-touch-confirmed.log`。
- 演示覆盖配置已移到`/run/systemd/system/obd-power.service.d/90-dryrun.conf.disabled`，不再生效。真实服务ExecStart无dry-run/fixture参数，读真实sysfs；online=true/idle，NRestarts=0。
- 仪表实机采样约57–59fps；电源服务内存峰值约5MB，演示期间约4秒CPU时间，不是每帧重画窗口。
- 安装中曾USB短断，用户确认仍显示仪表；重新连接后uptime未重置，两个服务active，未发生手机重启。安装安全guard已取消。
- `activate_power_policy.sh`曾在停止已被回收的transient timer时报告not-loaded；真实服务当时已经成功启用。脚本已修正为仅在timer active时停止，最终配置另外读回确认。

## 文件校验

- gauge_sdl.py：`96124e9282c947718061e271a13d5bc0e8a23f27fe33cc4214bd508fc2897dc4`
- gauge_power.py：`cbd3f9a5c4ae07fdba85813f14e6e4dd553d00535a92bd09ba4596192274730c`
- 根服务最终版：`a1329c50140c7b869fdeeb77fa6e51b07d4d1af0ca6ff86a3581676a3806d648`

## 关机插线开机：2026-10-19已实机验收通过

软件在真正关机后不运行，不能用Linux用户服务伪装设置此功能。当前PM8941 pwrkey驱动含SYS_POWER_OFF→PS_HOLD SHUTDOWN配置，msm-restart驱动已绑定fc4ab000.restart；lk2nd版本`22.0-next-4a1e26e4-20260419-dirty`。

本轮未更改引导链，没有执行未知fastboot OEM命令。实测手机现有引导链已支持关机后接线直接进入Linux，无须再改引导程序。

只读参考：[Linux PM8941电源键驱动](https://github.com/torvalds/linux/blob/master/drivers/input/misc/pm8941-pwrkey.c)、[lk2nd项目](https://github.com/msm8916-mainline/lk2nd)。实际代码检查使用本机WSL `/root/mi4-audio-work/linux/drivers/input/misc/pm8941-pwrkey.c`、`drivers/power/reset/{qcom-pon.c,msm-poweroff.c}`。

2026-10-19用户按要求实际拔USB、不点按钮，等20秒并再等10秒，然后插线且不按电源，确认：**“自动关机，插线后自动进入仪表”**。

接线后00:07读取系统：uptime约2分钟，obd-power和obd-gauge-kiosk均active/running、NRestarts=0；电源服务enabled，状态online=true/idle；本次新开机视频也完整EOS（361帧、last_pts=12.0、complete=true）。证据`power-policy-physical-verified-20261019.log`。

需求完成。不要为了已工作的插线开机再写启动分区或PMIC寄存器。
