# 开机直入视频、设置关机按钮（2026-10-19，进行中）

## 需求/当前结论

用户实拍：上电约5秒出现内核文字，静态NERV首帧约30秒，然后白屏，最后才播放视频。目标为直接视频→完整播完→仪表；另加设置页一键关机。

- **一键关机已安装**：设置页右上角红色“关机”，直接安全关机，无额外确认或20秒等待。触摸实机点击尚待用户确认，软件链路和权限测试已过。
- **早期内核文字尚未隐藏**。所有已安装修改仅在rootfs，本轮boot分区未写，SHA仍`5715032761b50157ea495d5dfb3d71b2b6de300f00ce7681f48f154dd9f67653`。
- 用户中途真实拔线重开机后，新的第一阶段时间线：视频首帧从37.0秒提前到21.35秒，完整EOS42.94秒，43.2秒同窗口切仪表。不能声称已达到“无等待、无文字”。
- 之后又提前了音频服务、延迟加载Pango字体栈；仪表已运行正常，但这一最后优化还没有新的冷启动采样。

## 启动根因证据

原始开机：kernel4.899s，rootfs28.230s；静态幕布8.66s；mi4-audio-init17.73–20.27s；user@1000直到32.85s；kiosk32.91s；视频37.03s。

原kiosk显式等待systemd-user-sessions、bluetooth、user@1000及电源服务，用户会话又等NetworkManager。音频实际上20秒已就绪，视频却在37秒才开始。

原视频前1秒FFmpeg YAVG约27–28（暗），不是整屏白色。因此用户白屏不是源视频的开场白帧。窗口初始化前后增加背光门控，最终是否完全消除白闪仍待视觉确认。

## 已安装启动修改

1. `/usr/local/lib/obd-gauge/boot_video.py`：
   - BacklightGuard在SDL/KMS初始化前保存准确亮度并设0，完整ARGB首帧上传并present后恢复原值。
   - `/run/obd-gauge/boot-brightness`用于异常kill后的ExecStopPost恢复；不改WLED驱动，不修改硬件增益。
   - scoped GST_PLUGIN_PATH，支持启动时直接`alsasink device=hw:0,0`，仍强制S16LE/48k/stereo、播放器volume=.5。
   - appsink processing-deadline=0。**实机视频仍361帧约21秒，约17fps；此项没有解决速度，不要误报30fps。**
2. `/usr/local/lib/obd-gauge/launch_boot_video.py`：启动ALSA模式不等桌面Pulse；EOS后释放PCM，已有用户管理器时启动正常PipeWire/WirePlumber；保持同窗口接管和完整音视频EOS。
3. **完整替换systemd单元**，不靠清空After的drop-in：
   - `/etc/systemd/system/obd-gauge-kiosk.service`来自`obd-gauge-kiosk.early.service`，DefaultDependencies=no，只等remount、udev-trigger、curtain及音频，不等网络/user@1000/电源UI。
   - `/etc/systemd/system/mi4-audio-init.service`来自`mi4-audio-init.early.service`，最后版只等remount；内部`/usr/local/bin/mi4-audio-init.sh`完全不改，仍按vreg-boost等待→干净重载→路由→MCLK顺序。
   - `/etc/systemd/system/obd-power.service`来自`obd-power.parallel.service`，只移除Before=kiosk，让电源服务并行，仍enabled且策略不变。
   - 旧kiosk drop-ins `50-obd-boot-video.conf`、`60-obd-power.conf`移到`.disabled.early-20261019`；首次尝试80-dropin也移到disabled。
   - **依赖列表不能靠After=空行从drop-in移除。** 第一轮读回After仍含旧依赖，故改完整unit。以后必须看`systemctl show ... -p After`，不能仅看编辑后的文件。
4. scoped GStreamer ALSA插件：`/usr/local/lib/obd-gauge/gstreamer/libgstalsa.so`。仅提取插件，不全局安装deb。
   - TUNA包`gstreamer1.0-alsa_1.24.2-1ubuntu0.5_armhf.deb` SHA`afc2c40715cd59cc9d8ad66268ad26a072cbe2f4d5c39dc026c36f062a39cf68`，匹配手机apt元数据。
   - .so SHA`4e1f4a137f01aef590cb656272f125ce65c2ab935fd6718a4f67407d01be8388`。
5. `gauge_sdl.py`：`load_drawing()`延迟Pango/GLib字体导入到仪表构建；启动视频只导入Screen，不先加载整个字体栈。原生1080p/增量刷新不变。

## 一键关机

- gauge_settings右上96×44按钮，点击有效、横滑无效；失败时显示服务不可用。
- PowerClient新增固定`shutdown`请求；root SO_PEERCRED校验仍在，RPC仍无任意命令。
- 根服务新增manual关机，执行同一`systemctl --no-block poweroff`，不要求拔线、不等待20秒。reason=manual，界面显示“正在安全关机”。已提交关机为终态，不重复发命令；失败保留可见错误。
- 拔线20秒、保持开机、重插取消、传感器未知/卡死UI不盲目关机均保留。
- 手机root服务代码a479…；仪表最新e97d…；设置a83d…；客户端b031…（完整hash看部署日志）。
- 回退仅按钮：`sudo /usr/local/sbin/rollback-obd-manual-off`。注意该脚本会恢复懒加载前的仪表，也去掉手动关机RPC，但保留原拔线倒计时和启动单元。

## 回退/恢复

- 启动回退：`sudo /usr/local/sbin/rollback-obd-early-video`，还原两播放器模块、原kiosk/audio/power单元及旧50/60dropins；若仪表恰是e97d版本，还原到保留关机按钮的6547版本。
- root备份：`/usr/local/lib/obd-gauge/before-early-20261019/`，普通仪表备份`/home/umeko/desktop-offline/gauge_sdl.before-lazy-20261019.py`。
- 永久boot guard：`obd-early-video-check.timer`，OnBootSec=100s，检查本次完整EOS和kiosk active；失败回退上述rootfs启动配置。第一次完整单元冷启动已正常通过。
- 三个transient安装guard通过软件检查后均已停止，不会稍后无故回滚。
- 本机仍可COM10串口登录umeko；password1234（不要向日志回显）。USB receiver已持久放在desktop-offline，重启后可`cp .../usb-receive.py /tmp/usb-receive.py`恢复传输。

## 隐藏早期内核文字：准备了RAM-only单项实验，尚未启动

禁止重用10月18日失败的`quiet_boot.py --write`，它仍禁用。那次移除了console=tty0并加多个参数，黑屏后已恢复。

新实验只在已核对的真实备份中**保留全部原参数和两个console，追加唯一loglevel=0**。不加quiet、不取消控制台、不改kernel/DTB/initramfs/lk2nd。使用临时`fastboot boot`，不执行flash。

- 构建脚本`make_loglevel_ramtest.py`只有普通文件输入输出，没有任何写块设备/刷机API。
- 产物`boot-mi4-loglevel0-RAMTEST-20261019.img`，Linux-only（去掉前512KiB lk2nd），16338944字节。
- SHA`eaf69d66d1e88acf7fad90cfcc8dacc35e870b7cfed50cede612c925f2a76ec4`；对应JSON清单明确RAM ONLY。
- kernel/DTB/initramfs全部字节一致，仅Linux header 512字节cmdline字段改变；2项专门测试通过。
- 下一步请用户进入**lk2nd Fastboot文字界面**，先只读getvar确认阶段/序列，然后考虑`fastboot boot <RAMTEST>`。不要用厂家兔子直接跳过lk2nd测这个镜像，不要flash试验文件。
- RAM启动失败时长按电源回到原持久镜像；若成功也先观察完整开机、串口/proc/cmdline、硬件/电源/音频/触摸，不能将字节校验当成功。

## 日志/测试

`boot-delay-timeline-20261019.log`、`boot-audio-kms-timeline-20261019.log`、`early-video-v2-install-20261019.log`、`early-video-v2-eos-20261019.log`、`early-video-coldboot-20261019.log`、`manual-off-active-20261019.log`、`lazy-boot-active-20261019.log`。

最终全套56项全部通过，含Screen不预加载Pango、RAM-only边界/保留参数2项。新设置预览`settings-manual-off-preview/settings-0.png`。

已向用户请求进入lk2nd Fastboot；目前没有执行fastboot boot/flash，等待用户确认入口状态。

用户反馈FASTBOOT兔子；只读查询确认`[DEVICE-SERIAL]`、product=MSM8974、version-bootloader为空，为厂商入口，未在此入口启动Linux试验镜像。已请求用户准备观察屏幕，下一步可由电脑`fastboot -s [DEVICE-SERIAL] reboot`，让用户仅在mi标志出现后按音量下，进入lk2nd再验证版本。

### 无需抓按键时机进入lk2nd的方法（已成功）

普通reboot后等mi标志再按音量下没有成功，用户无法抓到窗口。改为：**在厂家兔子界面提前一直按住音量下，电脑执行`fastboot -s [DEVICE-SERIAL] continue`**。主机返回Resuming boot OKAY，用户确认“进入了”；只读getvar product返回`lk2nd-msm8974`（version-bootloader仍为空，不能只靠版本字段识别）。这时松开按键。

随后只执行了`fastboot -s [DEVICE-SERIAL] boot boot-mi4-loglevel0-RAMTEST-20261019.img`：15956KB发送0.439s、Booting0.047s均OKAY。**这是RAM-only启动，不是刷写；实际启动结果仍待核对。**
# 2026-10-19 后续：视频前白屏修正，实机重播已确认

## 最新已验证：音画同步修复（实时12.04秒），冷启动待再测

用户报告音轨不同步。此前361帧全部显示却用约22秒播12.14秒媒体，说明“完整帧数/EOS”不能证明同步。修改 `boot_video.py` 的 appsink 为 `sync=true qos=true max-lateness=50000000 processing-deadline=0 max-buffers=1 drop=true enable-last-sample=false wait-on-eos=false`，以流水线时钟同步，禁止消费端积压旧画面；允许略过迟到画面而不是慢放，仍等待音视频全程EOS，半音量、背光保护、同窗口HUD保持不变。

官方行为依据：[URL REDACTED] （max-lateness/QoS），[URL REDACTED] （有限队列及drop）。

当前root模块SHA **`cb421b1549cd5554b93fab8026306b54d155f751a3db1b9aa0412190a7ef3e0f`**，备份 `/usr/local/lib/obd-gauge/boot_video.before-avsync-20261019.py`（前版93e7...）。部署 `install_avsync_video.sh` 后仅实机重播，未写boot分区。10项视频测试通过。用户明确确认“音画同步，结束后正常进入仪表”。日志 `avsync-replay-20261019.log`：205帧显示，末PTS12.0，实际12.04056秒，媒体duration12.13867秒，完整EOS，active/NRestarts0，同窗口切换。stats dropped=0仅为BaseSink计数，**不能解释成未丢帧**，appsink队列drop或上游QoS略过的帧不一定进入该统计；全361帧并非同步必要条件。

增加marker字段elapsed/duration/dropped便于后续确认，不能恢复旧drop=false设置。首次冷启动/拔插线仍需再验收并行启动时长与同步。下一次应直接让用户拔线关机/插线，不需再进Fastboot。

## 最新待验收：缩短约15秒视频前黑屏，声卡/播放器改为并行准备

顺序修正后用户反馈“黑屏了大概15秒才进入视频”。`quiet-order-coldboot-timing-20261019.log`：幕布5.641–7.411秒，声卡5.620–11.210秒，kiosk12.063秒才启动，SDL14.531秒，视频首帧16.015秒；EOS361帧完整38.530秒，同窗口HUD38.823秒。不能把所有黑屏当作故障，也不能承诺立即播放。

已部署 `install_parallel_boot_next.sh`：只从 kiosk unit 的 After 移除 `mi4-audio-init.service`，Wants 保留。播放器可以在udev/幕布完成后准备SDL，同时声卡初始化；launcher仍检查成功ready标记与PCM节点，最多8秒（随后故障静音降级原有策略），保持半音量/完整EOS/背光保护/硬件脚本不变。root备份 `/usr/local/lib/obd-gauge/kiosk.before-parallel-boot-20261019.service`。逐字比较拒绝任何其他unit差异，systemd-analyze verify通过，daemon-reload后After/Wants回读符合预期。只针对下次启动，未重启/未重播/未写boot分区。

部署日志 `parallel-boot-next-install-20261019.log`。连接曾消失后恢复（设备已重启，新uptime<1min），当前仪表active。下一步用户拔线关机再插线，测实际首帧时间、白屏/文字是否重现以及声音是否正常；预计仅节省几秒，尚未测得收益。

## 最新：实拍定位内核错误日志；修正 quiet/loglevel 参数顺序，待用户冷启动验证

用户实拍 `8797360e62e67dca09ab0e8034679722.jpg` 显示内核 qcom_rpm / DT overlay 日志（1–5秒），不是lk2nd画面或仪表。插线冷启动串口确认旧参数已持久生效，ignore_loglevel=N，rootfs幕布5.669秒运行成功，因此先前漏判：仅loglevel=0时initramfs有独立输出，但加quiet后剩余内核输出来自**参数顺序**。

本机实际内核源码 `/root/mi4-audio-work/linux/init/main.c:237` 的 quiet_kernel 设置 console_loglevel=CONSOLE_LOGLEVEL_QUIET；246–263的loglevel early_param按命令行顺序解析。`loglevel=0 quiet` 被后面的quiet重新提高日志级别，显示错误。修正为 **`quiet loglevel=0`**，不删除控制台、不改变任何其他选项。

`persist_quiet_order_fix.py --write-order-fix` 已完成原始备份/当前32MiB精确SHA/设备号尺寸验证，备份 `/root/mi4-boot-before-quiet-orderfix-20261019.img`（SHA bd8c176f...672e523e），仅覆盖同一cmdline512字节，写后全分区逐字节验证。**当前持久boot全分区SHA `1852dd1bda97b9bee008ccf46165db11c17e9b35dd40d18255a0c665157e8a1a`**。最早原始备份SHA571503...仍保留。三项精确候选/拒绝覆盖/顺序修正测试通过。日志 `quiet-order-precheck-20261019.log` 和 `quiet-order-write-20261019.log`。未自动重启，下一步用户拔线关机再插线，观察是否消除全部文字，不能提前宣称已视觉通过。

## 最新持久状态：用户明确要求先刷此版，已保存（尚待拔插线冷启动拍照）

用户原话“你先把这一版刷入，我再重启，拍照给你看”。按该授权，使用 `persist_approved_quiet.py --write-approved`，仅修改真实 `/dev/mmcblk0p19` 中 Linux header cmdline 512字节，偏移524352。未通过 lk2nd flash，未替换内核/DTB/ramdisk/lk2nd，其余32MiB分区字节均验证完全不变。原分区SHA `5715032761b50157ea495d5dfb3d71b2b6de300f00ce7681f48f154dd9f67653`，修改后全分区SHA **`bd8c176facaf7508b7cc106242705b04792d882c9f83e6b58336b203672e523e`**，Linux子镜像SHA与已测试RAM候选 `04f496fd...26b5a8e` 精确相同。原cmdline仅追加` loglevel=0 quiet`。

修改前新备份 `/root/mi4-boot-before-quiet-approved-20261019.img`（root，独占创建，fsync+SHA验证），电脑旧备份 `boot-before-quiet-20261018.img` 仍是同一原始SHA，可用于厂家兔子原始分区恢复（**不能把完整32MiB原始备份经lk2nd flash boot写入**）。写入前验证by-partlabel解析到p19、179:19设备、实际32MiB、精确原SHA、候选SHA；写后整分区逐字节核对通过。日志 `quiet-persist-precheck-20261019.log` / `quiet-persist-write-20261019.log`。两项精确候选/拒绝覆盖其他修复单测通过。

**之前文中的“启动分区未写”仅描述当时历史；现在已按用户明确授权持久保存。** 本次未主动重启，等待用户拔线关机再插线拍照。白屏在RAM启动已确认消失，文字仍存在，绝不能宣称启动文字修复完成。

## 第二次 RAM 临时启动已执行（等待用户视觉验收）

### 同一 quiet 候选再次临时启动：用户确认“还有文字，但是没有白屏了”

通过兔子按住音量下 + continue 再次确认为 lk2nd 后，用户松键，临时启动同一 SHA 候选。`quiet-ram-retest-20261019.log` 确认 quiet/loglevel=0 生效、首帧17.434秒、361帧完整EOS38.888秒、39.153秒同窗口仪表、active/NRestarts0。**视觉结论：白屏消失，但文字仍在，因此静默启动未完成，候选未持久写入。** 下步须实际文字照片，区分 lk2nd 留屏/内核或init脚本，不能继续仅凭参数生效推定隐藏成功。

用户在兔子模式持续按音量下，PC `fastboot continue` 后 `getvar product` 为 `lk2nd-msm8974`；用户松键后以 `fastboot boot boot-mi4-quiet-RAMTEST-20261019.img` 成功启动。串口确认原始 cmdline 加 `loglevel=0 quiet` 生效，两条 console 保留。首帧17.294秒，完整361帧/PTS12.0，EOS39.521秒，39.798秒同窗口切换仪表。音频启用、音量0.50，未再出现早期 DBus 就绪循环；kiosk active/NRestarts=0，仪表约55–59fps。启动分区未写入。仍须用户确认本次视频前文字、白屏、提前仪表是否消失；日志不能替代视觉验收，也尚未验证持久冷启动。

- 用户澄清：文字、白屏以及提前露出的仪表主题都发生在视频之前。
- `loglevel=0` RAM 试启动能进入系统，但仍有文字/白屏，未通过视觉验收，未持久刷写。最新串口读到原始 cmdline（用户已再次正常启动），不能声称仍处于 RAM 测试内核。
- 从 SHA 校验过的真实 32MiB 备份只读解析实际 7,453,097 字节 gzip initramfs（`inspect_current_initramfs.py`）：`init` 在非 quiet 时调用 `log_begin_msg`，直接输出不受内核 loglevel 管理；未发现仪表图片或自定义 splash 资源。
- `VideoScreen` 原来 ARGB 首帧后立即恢复背光，随后才切换 YUV。现保持背光关闭至首个解码 YUV 帧连续 present 两次后恢复原亮度，构造失败、播放失败/结束、ExecStopPost 均保留恢复路径。
- ALSA 就绪改为 `/run/mi4-audio-init/ready` + PCM 节点，不再询问早期尚未启动的系统 DBus。audio unit 使用 RuntimeDirectory + 成功 ExecStartPost 标记；原声卡初始化脚本不变。当前已成功初始化服务的标记手动补齐，未重载 codec。
- 部署 `install_prevideo_fix.sh`，备份在 `/usr/local/lib/obd-gauge/*before-prevideo-20261019*`。
- 新文件 SHA：boot_video.py `93e7c5e8013394af154b5a74974788fef37874c76765d38928e637d57870ecaf`，launcher `22ace6acfcef4cf47d773601c6de2bc564d57bcd1a575a72b12149aa4eb7f223`，audio unit `201883ecf023796b2300ede912f5712078ddc9d750ce7a8995f7f085ddb449cf`。
- 58 项测试通过。实机只重播未重启：用户确认“无白屏或仪表提前出现，声音和切换正常”。日志完整 361 帧，PTS 12.0，实际播放 20.75 秒（17.4fps，尚非正常30fps）；背光恢复1720，服务active，NRestarts=0。不得把重播验收等同冷启动验收。
- 第二个未执行 RAM 候选：`boot-mi4-quiet-RAMTEST-20261019.img`，16,338,944 字节，SHA `04f496fd4a673b6d5eaa1c7c57f27b88366183cb3e7626d2bb3799e8826b5a8e`。仅原始 cmdline 追加 `loglevel=0 quiet`，保留两条 console，内核/DTB/ramdisk 完全不变。生成器 `make_quiet_ramtest.py`，manifest 同名 json。只能在确认为 lk2nd-msm8974 后 fastboot boot 临时测试，**尚未执行，更未刷入分区**。
- 待做：用户进入兔子后持续按音量下，PC fastboot continue 进入 lk2nd，getvar product 验证后测试新 RAM 候选。冷启动仍须用户确认文字/白屏/提前仪表都消失，不能直接刷写。

