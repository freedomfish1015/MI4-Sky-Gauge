# 启动Logo补画版（2026-10-21，已视频验证；保持背光版冷启动待观察）

## 依据与边界

用户明确确认录像是新录像。录像约2.7s出现Logo，5.8s消失，23.5s进入仪表；绝大部分等待空档无界面。只读实机发现boot仍含vt.global_cursor_default=0，global_cursor_default/fbcon cursor_blink都是0；不能据录像同名反复认为用户发旧片，也不能据日志present成功当作面板必然可见。

`probe_logo_visibility_20261021.py`有限8秒暂停仪表、画同一rootfs Logo再恢复，用户确认“Logo基本一直可见，切回仪表时黑了一下”。debugfs确认Logo时scanout使用[fbcon] framebuffer83，仪表此前为python3 framebuffer87。原生绘制0.102s，热恢复仪表4.034s。说明资产和rootfs绘制能真正上屏，切回SDL仍有短黑；不是已经解决完整启动闪黑。

## 当前补画版机制

`sky_boot_curtain --hold-logo <existing-argb>`单进程先画一次，随后每100ms比较10行fb0数据，仅被覆盖时重画，而非每次写8MB。最长35秒自动退出；保持相同原生1080x1920图、位域/步长/边界检查，不改模式、不解绑控制台、不改变充电或电流。

当前curtain unit改Type=simple+RemainAfterExit，启动后立即允许其他系统任务进行，不等待35秒；原BMS Before=kiosk顺序完全保留。没有提前启动GPU/仪表，没有重试上一轮early_sdl实验。

为避免fbdev补画与本仪表SDL接管并发：root程序持有root-owned `/run/obd-gauge-logo.lock`文件，在同一个flock独占区内检查marker并执行绘制。`launch_gauge_direct.py`创建Screen前取得同一锁，写本人PID到`/run/obd-gauge/logo-handoff`再释放；此后root补画停止。root还检查debugfs其他userspace DRM master，遇到已存在的其他KMS客户端就退出。后一个检查不能宣称与所有第三方KMS进程原子互锁。

Logo仍只负责装饰；缺锁/marker不可写时launcher记录SKIPPED继续仪表，异常恢复背光。原有硬件配置、启动参数、无视频启动、应用代码保持原样。不能保证此版消除内核显示重新初始化的一瞬黑，目标先填住长等待空档。

## 安装与热测

`install_continuous_logo_20261021.py`安装前核对13个目标哈希（4个变更文件、kiosk/BMS单位、APP/settings、电量脚本/module以及boot/aboot/logo），核对payload，备份后替换4文件；失败自动恢复。热测真实ready PID、backlight>0、相关服务active、curtain PID已结束/exit0，所有不应修改的文件与分区SHA再次匹配。

备份：`/home/umeko/desktop-offline/backups/continuous-logo-before-d5aa7qfc`，root0700，包含before.json、installed.json及4个原文件。

- root curtain uptime1219.783绘制一次，1221.201退出，未与仪表持续竞争。
- 仪表PID1437，首帧1224.05，进程4.082s；这只是热测，不是冷启动耗时。
- 16项Python测试电脑/手机通过，9项C几何/清屏检测/短读失败检查通过。
- 测试故意制造缺Logo/缺Mock属性会打印FALLBACK，不是实际服务失败。

## 当前文件SHA（旧恢复脚本不能强行绕过哈希）

- `/usr/local/lib/obd-gauge/sky_boot_curtain`: `820b76b5f5dc4456ccf1dd66d23eb380cab65035e00e1a28aa5e40d9e58017b4`
- `/usr/local/lib/obd-gauge/launch_gauge_direct.py`: `684e910aecf32f533c4522eee1b1cc02902696a9e45401ae47bbf30f02a109b3`
- `/etc/systemd/system/obd-boot-curtain.service`: `bec7073d53ca7cdecd1c7810c3280331ed2a4735a8abd9996936a2112f213752`
- `/etc/systemd/system/obd-boot-curtain.service.d/99-sky-curtain.conf`: `4415036b16f7a584ce43c2973438894ccb1536c402a96e1611620f8458758ed5`
- boot完整仍`724783b32b5b09dd53245ec42277df4ef3b85cd1da7560ced1c0caaa92da8d2b`，本轮未打开块设备写入。
- 原资产仍b15992...201，APP a541e6...1dfc/settings38eff8...e77、BMS脚本66a08e...d0a6/moduleb0739e...632a，kiosk基础单位2de324...04ed、BMS单位660442...59不变。

精确回退：`sudo python3 /home/umeko/desktop-offline/install_continuous_logo_20261021.py --restore /home/umeko/desktop-offline/backups/continuous-logo-before-d5aa7qfc`。只在用户要求或本轮故障时执行；先严格核对当前4文件与备份，不整目录回退，不动引导或电量。

## 完整重启验证待完成

用户已回复“已准备录像，可以重启”，已执行普通reboot。应读取新boot的root补画次数/退出时刻、SDL release/Logo/仪表首帧时刻、NRestarts、供电和BMS状态，然后等用户报告实际长黑是否被填住。重启后的日志和用户验收应补到本文件，不能仅凭热测宣称三次闪黑解决。

日志：`probe-logo-visibility-20261021.log`、`continuous-logo-install-20261021.log`、`continuous-logo-hot-check-20261021.log`、`continuous-logo-reboot-command-20261021.log`。原early_sdl实验已撤销，不可与本版混淆。

## 补画版完整重启与新录像（已完成）

boot_id `3d0642a5-1baf-42ae-98ba-2f929a241d17`，curtain启动6.541s；只画一次，16.111s因交接退出，无新增被覆盖重画事件；kiosk PID454，NRestarts=0，13.64s Python启动，16.01s release，18.59s SDL Logo，20.56s首帧。电池73%、3.992V。日志`continuous-logo-normal-reboot-20261021.log`及`continuous-logo-full-reboot-details-20261021.log`。

用户新视频`931207b34cae26033d79ec91a8cdb07a.mp4`长27.2s、720x1280约29.96fps，旋转后逐帧核对：

- 首次Logo后约3.3~4.8s有一段黑屏，后又出现Logo。
- 约7.8~11.9s黑屏，之后rootfs Logo出现并持续约10秒。
- 约21.6~24.1s再次黑屏，再出现SDL Logo，约26s仪表出现。

以上是录像时间近似值，误差约0.5s，不能当kernel uptime。前两段从阶段判断属于更早的引导/内核显示交接，但尚未用全链路日志逐一证明。最后一段可与程序release16.01s至SDL Logo18.59s的约2.58s对应：BacklightGuard原本在创建窗口前主动写0，直到Logo两次present后才恢复，导致整个初始化期间看不到之前仍有的fbcon Logo。补画解决长等待覆盖，不等于3次短黑消失。

本次kernel日志仅查到17.823/17.875s的dsi_err_worker status=c，未在所查范围发现上一轮early_sdl实验反复Division by zero；不能把那个实验日志当成本版现象。

## 当前追加：不再在SDL初始化前主动熄背光（已部署，完整重启待结果）

仅修改root launcher：BacklightGuard.begin增加blank=True默认参数以保持旧调用兼容；DirectScreen调用blank=False。仍保存原亮度marker、异常/退出恢复与Logo首帧就绪机制。不动窗口库、GPU驱动、KMS模式、应用、BMS、引导分区。

当前launcher SHA **`60583c3f5e92e265e8c3a9b4f5ca69fb9b797805d8368cb6880f703d42134c71`**，上文684e...是上一轮补画初版，不再是当前值。其余3个补画启动文件SHA不变。

部署器`install_keep_logo_light_20261021.py`，本次payload staging `launch-gauge-keep-light.py`；备份 **`/home/umeko/desktop-offline/backups/keep-logo-light-before-u51i6cl2`**，只含原launcher684e...及installed.json。热测试PID1142，首帧uptime658.1、进程4.076s；17项PC单测通过。用户明确确认热切换“没有白闪，已准备录像，可以重启”，已再次正常重启。完整开机效果仍待新录像/反馈，不能宣称最后黑屏已经消除。

中间一次安装被USB供电online=0安全检查阻止，未写入任何目标。用户重新插稳后online=1、Charging，才实际部署。不要为通过检查去改充电驱动；这次没有改电量算法或阈值。

日志`keep-logo-light-install-20261021.log`、`keep-logo-light-reboot-command-20261021.log`。如需回退当前追加：

`sudo python3 /home/umeko/desktop-offline/install_keep_logo_light_20261021.py --restore /home/umeko/desktop-offline/backups/keep-logo-light-before-u51i6cl2`

它严格核对当前60583c...和备份684e...后只恢复launcher。若还需撤销整个补画版，**先**做上述单文件回退，再用上文continuous安装器--restore d5aa7qfc备份；不能直接绕过旧哈希守卫执行旧回退。boot仍724783...8d2b、其他硬件修复保留。
