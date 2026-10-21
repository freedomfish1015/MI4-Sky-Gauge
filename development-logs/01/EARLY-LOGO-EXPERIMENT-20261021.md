# 2026-10-21 同一SDL窗口提前显示Logo：未解决闪黑，已回退

## 用户实测与结论

rootfs原方案和本轮单一窗口方案均被用户报告为开机黑屏3次。问题仍未解决，不能宣称Logo全程无缝。用户愿意拍完整启动录像，具体3次发生位置尚不确定。

原方案正常重启：curtain 5.440s开始、5.843s结束，app13.62s开始、SDL Logo17.76s、仪表19.82s，NRestarts=0。

本轮实验普通重启boot_id `63896a70-3149-4774-a1d6-496cf4ad9fa3`：kiosk进程252、系统启动5.458s派生，Python START7.02s、SDL cursor14.209s、native texture14.793s、Logo14.98s、BMS确认15.06s、首帧18.69s。NRestarts=0，不是仪表进程重启3次。不能把首次Logo的物理接通电源计时与Linuxuptime混为一谈。

## 实验机制（已撤销，不是当前部署）

从已部署手机Screen的匹配AST机械提取`early_sdl_screen.py`，只依赖ctypes/math/os；原PC主程序含其他未部署工作，不整体复制。Screen AST SHA `a23facf344a52702bf34b4f0b55974e03b6a9707037bc5f8da1b55503e7b99f5`。

`launch_gauge_early.py`先取得同一个原生1080x1920 SDL窗口，直接上传已有ARGB Logo，显示后等待BMS服务active、正确驱动绑定、电压和容量值正常，再导入现有APP并传`main(startup_screen=screen)`。复用现有窗口和渲染器，Logo不发布仪表ready；真实首帧才发布。没有视频、校准、GPU软件渲染或放大。C curtain改成--quiet-only，不写fb0。

仅临时去掉kiosk基础单位等待全局udev-trigger，去掉BMS单位Before=kiosk（保留全部BMS模块/local-fs前提、驱动算法和upower顺序）；由launcher就绪检查维持仪表运行前的BMS保护。

首次热部署因误要求renderD128读写权限而等待超时，安装器自动恢复上一版。实际umeko只有sudo/audio/video组，现有SDL使用card0，不需render节点权限。修正为检查card0及backlight读写，不扩大系统权限后，第二次热部署成功。

电脑19项单元测试通过，手机6项新测试通过；C原有6种几何检查通过。热启动Logo1088.86s、首帧1091.81s，单进程4.034s，不能当冷启动时间。第二次备份 `/home/umeko/desktop-offline/backups/early-logo-before-kqy0jejk/`，包含before.json及installed.json。

## 内核日志：待查，不可直接断言因果

普通重启14.226/14.267s存在`dsi_err_worker: status=c`。19.086s起GPU worker反复打印`Division by zero in kernel`，堆栈`retire_submits+0x3ec -> Ldiv0_64`。目前没有上一boot的kernel journal可比较，不能认定是本次实验引入，也不能认定就是3次黑屏的根因。实际仪表仍运行、约43~56fps，无进程重启。提前显示的收益不足且用户仍报告3次黑屏，所以保守撤销该实验的rootfs变更，等待视频定位。

## 当前已恢复的状态

已执行`rollback_early_logo_20261021.py /home/umeko/desktop-offline/backups/early-logo-before-kqy0jejk`，精确核对7个目标SHA和备份后恢复：

- kiosk基础单位SHA `2de324d0f3d3efd1f3a048de3ca25a2ea5b9caa982617a5b3f65df8aabb404ed`，原After=udev-trigger恢复。
- BMS基础单位SHA `6604420868ef3f3c7136a7f8650ecf0ce914605fe6b4311d3549b12833069a59`，Before=kiosk/upower恢复。
- native curtain SHA `ee4deddac1e366ca705ad852f97e0ef86232d372d3f0558e01115acc5c7e9693`，rootfs绘制Logo恢复。
- curtain 99-sky-curtain.conf SHA `0f76674072d77534ed37923764c19260d81a7ea558e8a8ff11001b8075da7b87`。
- 删除精确新增的lib early_sdl_screen.py、launch_gauge_early.py及kiosk99-early-logo.conf。上传到用户APP目录的开发副本、测试、安装器和备份仍保留，未被服务使用。
- 原`launch_gauge_direct.py` SHA98b696...c6ae原本未覆盖，继续使用。

没有修改boot、aboot、logo、内核、initramfs、APP主代码、设置、触控/音频/电量驱动。boot完整SHA仍应为724783...8d2b；本轮安装器曾在热测试后核对一致，回退不接触块设备。

日志：`early-logo-install-20261021.log`、`early-logo-normal-reboot-20261021.log`、`early-logo-kernel-handoff-20261021.log`、`early-logo-gpu-warnings-20261021.log`、`early-logo-rollback-20261021.log`。早期失败备份`early-logo-before-mt469uyg`没有installed.json，已自动回退，不要拿它当成功安装使用。

下一步：用户提供从重启/接通电源到仪表的完整录像，逐次标注黑屏前后显示内容与时长，再关联内核/根文件系统/SDL时间；不要继续反复完整重启或直接改写boot。若最终需要改内核显示交接，先保留当前完整镜像、精确验证OCV/WLED/音频并做内存启动测试，另行告知风险。
