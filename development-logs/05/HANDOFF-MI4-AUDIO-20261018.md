# 小米 4 内置声卡交接（2026-10-18，用户要求暂停修改并换模型）

> **后续新增高优先级问题：待机/息屏后黑屏，按键无法恢复，用户需强制重启。**
> 已只读取证，尚未修复。先看第13节；应优先解决显示/唤醒稳定性，再完善日常音频。
> 手机已由用户重新启动，当前无声卡、音频叠加未加载；第3节是成功测试结束时的历史状态。

## 0. 先读这段：当前真实结果

**内置扬声器已经实际发声，用户亲耳确认“听到了持续蜂鸣”。**

成功实验是 rc7 驱动的临时最高正常音量模式：660 Hz 连续 20 秒，
48 kHz / 单声道 / S16_LE，波形峰值 3000（约 -20.8 dBFS）。
模拟增益寄存器 `0x1e0=0x04`，数字增益 `0x2e7=0x00`（0 dB）。
保留过流和削波保护，没有使用 +40 dB 数字过放大。

**但尚未完成日常音频接入，不能称“整个声卡已经完全修好”。**

- 成功的只是直接 ALSA `hw:0,0` -> ADSP/Q6 -> SLIMbus -> Taiko -> 内置扬声器。
- 测试结束后已重新加载 rc7 默认低档，`mi4_speaker_test_max=N`。
- 默认低档仍是此前听不到的设置，不要误以为成功设置已经永久保留。
- 当前系统 PipeWire 仍只有“虚拟输出”，不是可供应用使用的真实扬声器输出。
- 声卡设备树叠加仍是临时加载，重启会失效；没有安装声卡开机服务。
- 录音、耳机、听筒、麦克风、通话、长期播放、休眠恢复尚未验证。

用户最后要求：**先记录全部发现和后续操作，额度不足，要换模型。**
因此停止进一步手机修改；接手模型先阅读本文，再继续。

## 1. 设备、系统和用户约束

- 机型：小米 MI 4LTE / cancro / MSM8974 / Adreno 330 / ARM32。
- 手机左上角有 mi 标志。当前中文 Ubuntu 24.04.5 手机式界面，非 MIUI。
- 已有触控、背光、GPU 加速等历史修复；不要破坏。
- 电池由其他 agent 修复；**不要改电量曲线、充电参数、OCV 或电池驱动**。
- 用户确认新音频内核下界面、触控、左右背光均正常。
- 所有 GitHub 文件下载必须走国内快速镜像，不能直接下载 GitHub 原站文件。
- 无需重刷 rootfs、清空数据或刷完整系统；当前可用模块热替换迭代。
- 原系统网易云二维码登录曾被 8821 风控阻止，与声卡问题无关，不要读账号 cookie。

## 2. 文件位置和运行环境

Windows 当前工作区：

`[LOCAL-PATH]`

本轮全部声卡资料：

`[LOCAL-PATH]`

Windows 串口/传输工具：

- `[LOCAL-PATH]`
- `[LOCAL-PATH]`
- `[LOCAL-PATH]`

WSL 发行版 `Mi4Build`，root 用户：

- 原工程：`/root/mi4-clean`
- 原内核：`/root/mi4-clean/kernels/msm8974`
- 原内核输出：`/root/mi4-clean/build/kernel`
- **音频隔离源码：`/root/mi4-audio-work/linux`**
- **音频实际编译输出：`/root/mi4-audio-work/build`**
- 工具链 `arm-linux-gnueabi-gcc` 13.3。
- 必须先通读 `/root/mi4-clean/AGENTS.md`。已建立 WSL 增量构建流程，不要重跑
  `docker_build.sh`，它会删除工作/输出目录，可能毁掉现有资料。
- 隔离源码复制了原工作树的脏修改。不要 reset、checkout、commit 或覆盖原 WLED/触控补丁。
- 隔离源码的 `.git` 指向已不适用的子模块位置，`git diff --check` 会报 not a git repository；
  已通过实际模块编译，补丁用专门导出脚本生成。
- Windows 有 rg，WSL 没有 rg，WSL 文本搜索用 grep。

## 3. 成功测试结束时的状态（后来用户重启；当前状态看第13节）

- `uname -r`: **6.15.11-mi4-audio1**。
- 已安装和加载的 codec：**mi4-spk-rc7-volume-test**。
- `/sys/module/wcd9320/parameters/mi4_speaker_test_max`: **N**。
- ALSA card0：`Mi4Taiko` / `Mi4-Taiko`；PCM00-00：`MultiMedia1 Playback`。
- 机器驱动：`snd_soc_lumia1520_q6`，版本 `mi4-q6-link-order1`。
- 运行时叠加：`mi4_audio_overlay` 已加载，固件 `mi4-audio-output-prepare.dtbo`。
- 测试完成后：speaker PA=0x6f（bit7 OFF），RX bias=0，RX7 clock=0；
  supply_owned=0 / clock_owned=0 / supply_hw_enabled=0；stream allocated=0 / up=0。
- MCLK helper：applied=0，divider factor0 restored，hardware enabled=0，GPIO15 function0。
- WirePlumber 已恢复 ACTIVE。
- 无播放进程在跑，无持续蜂鸣，无开机自动播放/声卡初始化服务。
- 当前串口 COM10。曾离线，重新插线后恢复；手机期间重启过，需要重新加载临时叠加。
- USB 拔插通常不会丢掉叠加，**重启才会**。不要把二者混淆。

PipeWire / 用户空间读数：

- PipeWire 1.0.5，WirePlumber **0.4.17-1ubuntu4.1**。
- `wpctl status` 有 Built-in Audio device，但只有 `虚拟输出 / auto_null` sink。
- 默认 configured node 仍是 `auto_null`，测试用 `aplay -D hw:0,0` 绕过了它。
- `pactl` **未安装**。
- `alsa-utils` **1.2.9-1ubuntu5**。
- `alsa-ucm-conf` **未安装**；`/usr/share/alsa/ucm2/conf.d` 和 Qualcomm 目录不存在。
- apt 缓存候选 alsa-ucm-conf：`1.2.10-1ubuntu5.15`，TUNA Ubuntu ports noble-updates/main。
- `/usr/share/wireplumber/main.lua.d` 存在，因此应使用 **WirePlumber 0.4 Lua 配置**，
  不能直接套 0.5 的 wireplumber.conf.d 语法。

## 4. 已证实的底层路径

### 内核和引导保护

当前已刷音频内核；不是为了下次迭代再刷一次。

- 原电池修正版完整 boot（32 MiB）SHA256：
  `1071d6eb43c2dc87cd84b2048fedbd7ddd05db583e17a94da8bfe086231160f8`
- 原始 boot 手机备份：
  `/home/umeko/desktop-offline/boot-before-audio1-full.img`
- 原始 boot PC 文件位于上一级目录 `boot-now-ocvfix.img`。
- 音频内核刷入后完整 boot SHA（上次已验证值，不是本次重新读取）：
  `5715032761b50157ea495d5dfb3d71b2b6de300f00ce7681f48f154dd9f67653`
- boot 是 `/dev/disk/by-partlabel/boot` -> `/dev/mmcblk0p19`，32 MiB。
- 前 512 KiB lk2nd 没有改，SHA：
  `45a16cdeda912e255695b5491207b4fbb4740e28da3f11eb1d0d856e3d435767`
- Linux payload 从 +512 KiB 开始；`boot-mi4-audio1.img` 16338944 字节，SHA：
  `2863792b8b39bedaf654ff606ad329b8fe663151046689c488b939be920e420a`
- initrd 原样保留，SHA：
  `ed612c3515147cc4c53a734aff863c922b53f5ee8d8b726f85101c507425ba5b`
- boot DT 基于精确运行中的电池修正版 DT 提取；原属性逐一比对相同，只增加音频节点。
- 模块与内核匹配，`/lib/modules/6.15.11-mi4-audio1`；不要混旧 vermagic 模块。

有回退工具但不要无故执行：

`sudo python3 /home/umeko/desktop-offline/install_audio_kernel.py --rollback`

它校验现 boot 和备份，只恢复 +512 KiB 以后区域并读回校验。
当前用户确认 UI 正常且扬声器能响，无需回退或重刷。

### ADSP / SLIMbus / codec

- ADSP remoteproc2 RUNNING，加载已有 adsp.mdt/bxx；APR audio service 可用。
- 只读 ADSP probe 曾证实 GET_STATE READY，GET_VERSIONS 共11服务；APR 响应头24字节。
- SLIM_QMI_SERVER service0x301 / version1 / instance0 / node5 / port3。
- QCOM NGD 已完成 QMI/master capability/controller 注册。
- Taiko 控制函数 PGD `217:a0:1:0`，logical address **0xcb**。
- 接口函数 IFD `217:a0:0:0`，logical address **0xca**。
- 原始芯片识别 `[01 00 02 01 00]`，major0x0102/minor0x0001，Taiko2.0 路径。
- codec 核心初始化：0 -> 94 -> 95 个非零寄存器，canary0x320=e4。
- Reset TLMM GPIO63，IRQ TLMM72 LEVEL_HIGH；29路源遮罩，无 IRQ 风暴。
- 七路 codec supplies；speaker boost 使用已有 PM8941S4 / 5V，不另造电源提供者。
- MCLK 根据 cancro 原厂 DT：PM8941 GPIO15，9.6 MHz，19.2 MHz XO /2，
  divider base0x5b00，复用已有 RPM DIV_A_CLK1 id47。
- MCLK helper 只负责 divider/pinmux；真正 MCLK enable vote 由播放路径 clk API 获取/释放。
- GPIO15 MODE_CTL=25 表示输出、hardware function2（mainline func1 映射），不是电平强拉输出。

### 数字/模拟路由

`MultiMedia1/ASM7 -> ADM8 -> AFE SLIMBUS_0_RX 0x4000 -> PGD port16/channel144 -> RX1 -> RX7 MIX1 -> speaker PA`

- 单声道48k/16bit；IFD0x040=05（port配置），IFD0x180=01（多通道mask）。
- codec内部：RX7 MIX1 input1=RX1（0x38e=05），RX7 interpolator clock0x30f bit6，
  bias0x1a2 bit7，PA0x1df bit7；COMP0 关闭，采用 manual gain（0x1e0 bit2）。
- 生产路径通过 DAPM virtual gate 开始，默认 OFF，不会 probe 时自动开功放。
- PA ON 前先供电、MCLK、完整时钟切换、路由、RX7 reset/clock、gain；
  停止先关 PA，再 RX7/bias，然后恢复 RCO、释放 MCLK 和 boost 自己的 vote。

## 5. 历次实验结论：不要重复走弯路

| 阶段 | 改动/观测 | 用户实际听感 |
|---|---|---|
| rc3 | analog0x44，digital0xf4=-12dB，三声低幅度660Hz | 无声 |
| rc4/rc5 | analog0x3c（倒置控件第一非静音档），digital仍-12dB | 无声 |
| rc5 | 加 live PGD/IFD 只读快照 | 播放时status/source=00，无观测到欠载/过流 |
| rc6 | 补原厂完整 RCO->MCLK 切换及反向恢复 | 用户仍确认无声 |
| **rc7 max** | **analog0x04，digital0dB，低幅度信号连续20秒** | **用户确认听到了持续蜂鸣** |

由此可以确认：扬声器硬件/当前组合的完整播放链路至少可工作，不能继续按“声卡完全不通”排查。
**但不能仅凭这一个实验认定此前只有模拟增益一个根因**：成功时模拟和数字增益同时改变，
没有做两变量分离；rc6时钟修正也仍然保留在rc7中。准确说是已找到实际可听的组合。

注意：下游 TLV `line_gain` 的 mute 标记只是控件元数据，不能独立证明某寄存器档物理静音。
不要再盲目提高到数字+40dB，用户请求的最高正常音量已经用0dB数字档实际验证。

rc5 live status：播放 IFD034=00/060=00；停止后034=01/060=04，对应 PORT_CLOSED，
不是“播放欠载”。OCP1eb=00。PA status1ec 曾读70，本次rc7早期快照读00；
这是原始状态值，未取得位定义，**不能单凭它判断是否出声**，用户已确认本次可听。
CDC_CLK_POWER_CTL0x314 写03但始终读00，历史读回不可验证，不能以此否定音频已经工作。

## 6. 已修的非增益问题（都在导出补丁里）

1. NGD 的 base 先于 platform_device_add 赋值，避免同步 probe/work 竞态。
2. 禁用 codec 寄存器 cache（REGCACHE_NONE），避免把 Lumia 默认缓存误当 Mi4 真实读值。
3. 机器兼容 xiaomi,cancro-taiko-sndcard，model Mi4-Taiko。
4. 机器 FE links 稳定排在 BE 前；runtime overlay 插入顺序反转曾导致缺 MM_DL/MM_UL
   widget / ENODEV，已正常注册，不是忽略错误。
5. IFD 重绑时 sdev 已 UP 不会再给回调；主动 reconciliation，避免 online=0。
6. runtime OF 下 MCLK helper 的 parent 是 platformbus 而非 PMIC设备；使用
   spmi_find_device_by_of_node 找真实 PMIC 的已有 regmap，绝不注册新 regmap/provider。
7. rc6 使用真实 cancro resmgr 停钟/切换/复位/延迟序列，先关闭 RCO 再 MCLK；
   播放时 RC_OSC_FREQ c6->46，BIAS_OSC_BG_CTL17->16，恢复后回c6/17。
8. rc7 max 仅显式模块参数启用、运行中只读；cleanup 关闭PA并恢复低寄存器档；
   测试 harness 随后重新加载默认 low 模块，将 max 参数恢复 N。

附带曾看到 GPU retire_submits 除零日志，未证明由音频引入；同原 GPU 源码，
用户确认界面正常。不要无依据改 GPU 或说“所有回归均通过”。

## 7. 最新文件、哈希和证据

当前源码模块文件：`wcd9320-mi4-spk-rc7.ko`

SHA256：`e319e39cc2de3e78e03a1b52480356e07010b32cc14dc8bf2d5b72102e7e4688`

`mi4-long-test.wav` SHA256：
`5d9edef735437553da93dc04dd42f9ae22409b2d3a5bfa0d11f8db2eab461adb`

当前导出 `mi4-audio1-kernel.patch` SHA256：
`06990bdd189665f2ba82b14a038073ae20db24750b3d5909b5682419089db72a`

`mi4-audio1-kernel.config` SHA256：
`eafa97e04c3437446f6cf67384339f1f71c9898c8401a3acfc34a3457bf3e9db`

核心日志：

- **speaker7-max-20s-test.log**：最高正常音量20秒播放、真实寄存器读回、结束恢复全部结果。
- speaker6-clock-test.log / speaker6-cleanup.log：完整时钟切换和恢复。
- speaker5-live-status.log：IFD端口状态和PA/OCP观察。
- audio1-card-linkfix-result2.log / audio1-pcm-silence-test.log：card/PCM注册、流操作成功。
- AUDIO1-BRINGUP.md：详细历史；末尾新增最新结果。历史 pending/无声段不要当最终结果。
- RESULT-20261018.md 是更早记录，不是最新交接。

旧 `mi4-audio1-speaker3-modules.tar.gz` 和 `mi4-audio1-modules.tar.gz` **不含最新rc7 codec**。
最终部署/打包前应增量 modules_install 并重打匹配包，或者明确另外安装rc7替换文件。

## 8. 原始参考资料与国内下载

`downstream-reference/`：

- `cancro-wcd9320.c`：LineageOS/android_kernel_xiaomi_cancro cm-14.1 / sound/soc/codecs/wcd9320.c。
- `cancro-wcd9xxx-resmgr.c`：同仓库 / sound/soc/codecs/wcd9xxx-resmgr.c。
- `cancro-wcd9320_registers.h`：同仓库 / include/linux/mfd/wcd9xxx/wcd9320_registers.h。
- `cancro-wcd9xxx-slimslave.c`：同仓库 / drivers/mfd/wcd9xxx-slimslave.c。
- `cancro-mixer_paths.xml`：LineageOS/android_device_xiaomi_cancro cm-14.1 / audio/mixer_paths.xml。
- `wcd9320.c`：hammerhead cm-11.0 对照。

基础参考 `lumia-mainline-main.tar.gz`（879KiB）：
SHA `1c4e6a0041a6a84537377bf31b0f4cc83bab88c32b7af8c204d34def26bcd281`。
解压于 `reference/lumia-1520-mainline-main`。这是移植基础，不是 Mi4 已出声的证据。

成功的镜像方式（Windows Invoke-WebRequest）：

`[URL REDACTED]>/<repo>/<branch>/<path>`

archive 曾用 ghfast.top；下载后验证尺寸/哈希和源代码内容，不执行镜像返回的未知脚本。

## 9. 连接、文件传输和重启恢复

以下是复用方法，不是要求接手后立刻播放。
COM10 只能单工具占用，**所有串口调用必须串行**。

```powershell
[System.IO.Ports.SerialPort]::GetPortNames()
& '[LOCAL-PATH] `
  -PortName COM10 -CommandText 'uname -r; cat /proc/asound/cards' -TimeoutSeconds 10
```

串口登录用户 umeko，手机已确认的默认本地密码1234（非网易云/路由器账号）。
helper 会自动尝试登录；开机慢时它固定700ms等待可能太短，出现“Shell not ready: ume”，
这不是设备坏了。读串口提示，用户名后等2秒，密码后等3秒即可；密码期间不打印原始回复。
sudo 的缓存会过期，执行 sudo -v 并在密码提示下授权；不要明文回显密码。

文件传输前手机须有 `/tmp/usb-receive.py`；重启会丢，需要把PC上的同名1285字节文件
base64复制回来。小于4KiB的串口命令安全，大文本/模块/音频一律用传输工具。

```powershell
& '[LOCAL-PATH] `
  -PortName COM10 `
  -Path '[LOCAL-PATH] `
  -RemoteName 'wcd9320-mi4-spk-rc7.ko'
```

远端文件自动到 `/home/umeko/desktop-offline/`，mode600，接收后SHA校验。
注意 PowerShell `.ps1` 成功并不一定重置 `$LASTEXITCODE`，上轮曾误读到旧值1；
应检查脚本异常、`$?` 和 `USB_RECEIVER_VERIFIED`，不要因旧 LASTEXITCODE 误判传输失败。

**如果手机重启、/proc/asound/cards 没卡：**

先验证 uname 等于6.15.11-mi4-audio1、sudo正常，然后检查叠加是否已经加载，避免重复插入。
本机已存在 `/lib/firmware/mi4-audio-output-prepare.dtbo` 和
`/home/umeko/desktop-offline/mi4_audio_overlay.ko`：

```bash
test -e /sys/module/mi4_audio_overlay || sudo -n insmod \
  /home/umeko/desktop-offline/mi4_audio_overlay.ko \
  firmware=mi4-audio-output-prepare.dtbo
sudo -n modprobe snd_soc_lumia1520_q6
cat /proc/asound/cards
```

不要卸载已被 codec/card 使用的叠加，不要为了恢复临时叠加重刷 boot。

## 10. 复现成功实验（仅在需要、用户准备好时）

手机最新脚本均已传输：

- replace_mi4_codec.sh：模块热替换，参数 `<模块basename> [low|max]`。
- test_mi4_speaker.sh：ALSA路由、MCLK divider、超时、EXIT清理；默认短音，参数
  mi4-long-test.wav 时25秒硬超时。
- **test_mi4_max_volume.sh**：加载rc7 max，停WP，20秒蜂鸣，EXIT重新加载rc7 low并恢复WP。

```bash
bash /home/umeko/desktop-offline/test_mi4_max_volume.sh
```

不建议单独加载 max 后忘记恢复。成功结束标志：

```
MAX_TEST_PARAMETER_AFTER_CLEANUP=N
applied=0
en_ctl=00 enabled=0
active
MAX_VOLUME_TEST_FINISHED
```

`LOW_VOLUME_PCM_COMPLETED` 是旧脚本固定标签，**不能拿它证明当时是低档**；
本次真正音量由 max 参数Y + live寄存器1e0=04/2e7=00证明。

## 11. 下一步怎么做（尚未实施，别当作已完成）

1. **先把这次发声结果告诉用户，别再反复排查“完全无音频”。**
2. 保留rc7已证实的时钟/路由/功放顺序。把可听增益组合做成正常播放配置；
   不要仅永久设置“测试max”参数来冒充完整音量控制。
3. 选择正常增益策略：建议codec保持0dB数字、不使用正增益，扬声器正常模拟档；
   用PipeWire软件音量控制日常0..100%，或增加正确的ALSA控件。
   如果实现ALSA控件，**不要让DAPM启动的硬编码写入覆盖用户音量**。
   真正静音应有可靠开关，不要仅猜TLV mute元数据。
4. 接上PipeWire输出：目前只有auto_null，`aplay hw`出声不代表音乐App能响。
   可研究 ALSA UCM2 自定义Mi4Taiko HiFi/Speaker profile（需要先安装alsa-ucm-conf基础文件），
   或WirePlumber0.4 profile/显式ALSA sink。一次只选一种清晰方案，备份现配置。
   单PCM、单声道48k，避免同时开多个hw:0,0；PipeWire应承担混音。
   普通立体声应用需正确下混到单声道；mono48k限制要写清。
5. MCLK divider/pinmux当前由测试脚本显式on；日常播放也必须有等价初始化，
   否则只配PipeWire sink也可能无声。不要把现有RPM provider替换成私造clock。
6. 启动持久化：当前boot DT sound disabled，通过显式OF叠加启用。
   可用窄范围systemd初始化服务，在现有内核/模块/firmware匹配校验后加载叠加和机器模块，
   等card出现、设置divider/pin，再允许用户音频服务；或审慎更新boot DT。
   **优先避免新一次刷boot**，不改电池/触控/背光。
7. 闲置管理：不播放时PCM suspend、PA/boost/MCLK owned votes释放；
   不能为了“保持有声音”让扬声器功放或5V boost整夜通电。
8. 用PipeWire正常播放短提示音，用户确认，再试手机音乐App及系统音量、静音。
   再测试息屏唤醒/暂停恢复，最后在用户方便时做一次重启持久化验证。
9. 收尾更新补丁/模块包和本文，明确哪些步骤已完成、哪些没测。

当前暂停点：**还没有写rc8、没有新建UCM、没有改WirePlumber配置、没有安装alsa-ucm-conf，
没有开机服务、没有设置真实默认sink、没有改系统App。**

## 12. 后续构建与导出（无需全量编译内核）

对源码的编辑使用 apply_patch，例如Windows可访问：

`//wsl.localhost/Mi4Build/root/mi4-audio-work/linux/drivers/slimbus/wcd9320-core.c`

增量编译约10秒（同一个build目录不要并发make）：

```bash
make -C /root/mi4-audio-work/linux O=/root/mi4-audio-work/build \
  ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- -j8 modules
```

拷出 `/root/mi4-audio-work/build/drivers/slimbus/wcd9320.ko`，
`arm-linux-gnueabi-strip --strip-debug` 到新命名的独立产物，记录sha，不覆盖旧版本证据。
用现成 replace 脚本替换时先停WirePlumber、关gate/route、恢复divider，
卸机器模块再卸codec，安装匹配版本，modprobe codec再机器模块。
**不能在PCM或功放工作时卸载codec，不能留下divider applied状态再卸clock helper。**

导出当前相对原脏树的补丁/config：

```bash
bash /mnt/d/小智-明日香/mi4-umeko-flash/audio-bringup/export_audio_patch.sh
```

完整模块包更新用独立modinst前缀（不要误删旧包）：

```bash
make -C /root/mi4-audio-work/linux O=/root/mi4-audio-work/build \
  ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- \
  INSTALL_MOD_PATH=/root/mi4-audio-work/modinst INSTALL_MOD_STRIP=1 modules_install
```

再仅打包lib/modules/6.15.11-mi4-audio1，排除build/source链接。
模块升级无需改zImage/ramdisk/boot；除非确有内核配置变动，不要重新刷机。

## 13. 后续新增：待机/息屏后黑屏，优先于音频完善

### 用户报告与当前状态

用户在交接后报告“手机会黑屏然后没有反应，只能重启”，并明确答复：

- 黑屏发生在**息屏或待机一段时间后**。
- 已手动重启，界面恢复。

本轮只进行日志/源码读取，没有再加载音频叠加、播放、修改电源策略或刷机。
当前启动时间2026-10-18约17:08:31 +08:00，kernel仍6.15.11-mi4-audio1，COM10可用。
`/proc/asound/cards` = no soundcards，`mi4_audio_overlay` 未加载；codec wcd9320模块仍在。
phoc PID504、phosh PID636在当前启动中运行（不要依赖PID，重新检查）。
`systemctl --user is-active phoc phosh`返回inactive不代表它们没运行：实际由其他会话启动。

### 已保存的日志

- `black-screen-after-idle-initial.log`：启动列表、当前kernel/uptime、初次检查。
- `black-screen-previous-boot-root.log`：sudo读取上一启动内核末220行和warning末60行。
- `black-screen-display-sleep-events.log`：DRM/GPU/休眠筛选、phoc日志、当前音频状态。
- `black-screen-tail-and-idle-settings.log`：显示超时之后用户空间仍活着的具体时间线。

这些文件由串口helper保存完整收到内容，终端展示可能截断且有ANSI高亮；以本地文件为准。
普通umeko没有journal内核权限，初次`journalctl -k`无记录是权限问题，不能解释为没日志。
sudo -v在本次已重新授权。`/sys/fs/pstore`不存在，不能依赖pstore提取上次panic。

### 证据与有边界的判断

上一启动ID：`68c8ccb7a9eb4d8d82d06223c00b9c73`，起始约16:57，黑屏后强制重启。

1. **GPU重复除零**：16:57:51、16:58:01/02/03、16:59:00等多次出现
   `Division by zero in kernel`，gpu-worker，调用栈：
   `Ldiv0_64 -> retire_submits+0x3ec/0x420 -> kthread_worker_fn`。
2. **显示控制器超时**：17:02:51，
   `msm_mdp fd900100.display-controller: pp done time out, lm=0`。
3. **超时以后系统仍运行**：nm-applet持续写日志到17:05:23，17:05:11有USB/NCM会话重启，
   17:05:20、22、23、25、27仍有systemd-logind的`Power key pressed short`。
   因此不能把这次症状直接解释成“整机当场死机”；显示/唤醒/DRM链路更值得优先调查。
   但没有黑屏当时的串口进程栈，仍不能断定精确卡点。
4. GPU除零在16:59:21加载音频叠加之前就发生，所以不能简单归咎于20秒蜂鸣或PA开关。
   **仍不能据此排除整个新内核、配置/时钟等全局变化的影响。**
5. `msm_gpu.c` 与原脏源的对应文件cmp逐字节相同，未做GPU源码改动。
   这只证明源码一致，不证明旧内核没有这个bug，不证明它是黑屏唯一根因。
6. 读取当前策略：`/sys/power/mem_sleep`为`[s2idle]`，state=`freeze mem`；
   gsettings sleep-inactive-battery-type=`nothing`，timeout900，desktop idle-delay300。
   当前自动电池休眠已是nothing，**不要盲目再用“禁用深度休眠”当成确定修复**。
   idle blank、手动电源键息屏、显示runtime PM仍需分别检查。
7. 目前未见证据证明是电池没电导致；不要修改其他agent的电池修复。

### 已做的只读源码定位（没有改文件）

`arm-linux-gnueabi-addr2line -i -e /root/mi4-audio-work/build/vmlinux -f 0xc071f38c`：

- arch/arm/include/asm/div64.h:38 (`__div64_32`)
- drivers/gpu/drm/msm/msm_gpu.c:676 (`retire_submit` inline)
- drivers/gpu/drm/msm/msm_gpu.c:730 (`retire_submits`)

对应代码是GPU提交统计：

```c
elapsed = (stats->alwayson_end - stats->alwayson_start) * 10000;
do_div(elapsed, 192);
cycles = stats->cpcycles_end - stats->cpcycles_start;
if (elapsed) {
    clock = cycles * 1000;
    do_div(clock, elapsed);  /* addr2line落在这里；不要只加if(elapsed)——已有 */
}
```

后续可以调查ARM32 do_div分母宽度/转换、异常统计计数；这只是进一步分析线索，
尚未证明怎样修、也没编译任何GPU补丁。

显示timeout源在：
`drivers/gpu/drm/msm/disp/mdp5/mdp5_crtc.c:1224-1228`，
`wait_for_completion_timeout(pp_completion, 50ms)`等待超时。
不要直接延长超时当修复，也不要未经复现就改背光驱动。

### 建议接手后的顺序

1. 先问用户是否方便保留一次黑屏现场，连接USB，不要一黑屏就立即强制重启。
2. 黑屏时尝试串口，记录uptime、phoc线程/阻塞栈、DRM状态、内核新日志、按键事件；
   区分仅面板不亮、compositor卡住、GPU/MDP fence等待和整机无响应。
3. 用读到的实际会话方式定位phoc/phosh，不要因user unit inactive误杀整套界面。
4. 若需要“临时不自动息屏”的规避，先征求用户同意，保存原设置，明确这不是根治、
   会增加耗电；当前还没有更改任何gsettings或sleep target。
5. 任何显示服务重启、GPU热重置、内核更新或回退均应另行说明影响和取得所需授权，
   不要在只读诊断阶段擅自执行。保留音频rc7成功产物和原boot备份。
6. 稳定性修复验证后，再回到第11节的普通应用音频接入。

## 14. 接手后第二轮：黑屏排查结论 + 日常音频已接通（2026-10-18 17:4x）

### 黑屏排查结论（先读，别再怀疑音频链路）

- 本次启动**未加载音频叠加**（`/proc/asound/cards` = no soundcards），
  但 `17:12:15 pp done time out, lm=0` 照样出现 → 叠加模块不是必要条件。
- `fault-kernel-20261018.log`（00:40）与 `settings-blackout-diagnostic.log`（10:06）
  在**刷音频内核（15:35）之前**就已有大量同一条 `pp done time out, lm=0`；
  `fault-kernel` 那次明确发生在 suspend 流程内
  （Freezing user space processes → Restarting tasks）。
  → **pp timeout 是既有问题，不是音频内核引入的**。
- GPU `retire_submits` 除零只出现在 audio 相关日志，旧日志未见；
  但它比黑屏早约 5 分钟，且 ARM32 上仅打印警告返回 0，未证明是黑屏根因。
- 本轮观察到 `dpms=Off` 后可自行恢复到 `On`，屏幕未卡死，**黑屏尚未复现**。
- 下一步建议：保留一次黑屏现场，黑屏时抓 uptime / phoc 阻塞栈 / DRM 状态 /
  新内核日志，区分「面板不亮 / compositor 卡住 / MDP fence 等待」三种情况。

### 已完成：日常应用可以出声

1. **恢复声卡**（重启后叠加会丢，需重新加载）：
   ```
   test -e /sys/module/mi4_audio_overlay || sudo insmod \
     /home/umeko/desktop-offline/mi4_audio_overlay.ko \
     firmware=mi4-audio-output-prepare.dtbo
   sudo modprobe snd_soc_lumia1520_q6
   ```
   得到 `card 0: Mi4Taiko [Mi4-Taiko]`。已加载模块 sha256 与第 7 节 rc7 记录一致
   （`e319e39cc2de3e78e03a1b52480356e07010b32cc14dc8bf2d5b72102e7e4688`）。
2. **增益固化**：不再依赖临时 test 参数。
   `/etc/modprobe.d/mi4-audio.conf` → `options wcd9320 mi4_speaker_test_max=1`
   即 rc7 验证可听的组合（模拟 `0x1e0=0x04` + 数字 `0x2e7=0x00`）。
   计划的 rc8（把该组合写成播放默认、去掉参数依赖）**尚未编译**：
   WSL 源码在 Windows 端只读（9P 挂载对 root 属主文件不能覆盖或删除）。
   补丁脚本与备份已留：`apply_rc8_gain.py`、`wcd9320-core.c.rc7-backup`，
   放行 wsl.exe 后按第 12 节增量编译即可。
3. **UCM2 配置**：新增 `/usr/share/alsa/ucm2/conf.d/Mi4-Taiko/Mi4Taiko.conf` 与
   `/usr/share/alsa/ucm2/Qualcomm/mi4-cancro/HiFi.conf`，已装 `alsa-ucm-conf`。
   **关键纠正**：UCM 按 **ALSA card driver = `Mi4-Taiko`** 匹配，
   不是 platform driver 名 `wcd9320-lumia-q6`，也不是 card id `Mi4Taiko`。
   `EnableSequence` 内自动建立路由（SLIMBUS_0_RX mixer + Mi4 Speaker Gate）。
4. **PipeWire 已接通**：`wpctl status` 出现
   `Built-in Audio Internal speaker` 并成为默认 sink，虚拟输出消失。
   实测 `aplay -D default` 与 `pw-play` 走 PipeWire 播放成功，
   `mi4_speaker_state` 显示 supply/clock owned、SLIM port16 channel144 UP。
5. **开机持久化**：`/usr/local/bin/mi4-audio-init.sh` +
   `/etc/systemd/system/mi4-audio-init.service`（已 enable，幂等 rc=0），
   负责叠加、机器驱动与 MCLK divider（UCM 无法操作 sysfs，必须由脚本设置）。

### 重要发现：ALSA 设备被独占，直连路径会被挡住

`hw:0,0` 不支持多进程共享（未配置 dmix）。**PipeWire 一旦打开它，其他程序就进不去**：
`test_mi4_speaker.sh` 在 PipeWire 运行时会失败于
`tee: .../mclk_div_test: 设备或资源忙`，divider 拿不到，脚本直接退出、不出声。
因此：

- 判断"扬声器等响不响"时，**必须先停 PipeWire 再用 hw:0,0 验证**，
  否则会把"被挡住"误判成"声卡没修好"。
- 日常使用只走 PipeWire 一条路即可，不要再同时用 `aplay -D hw:0,0`。
- 若将来确实需要两路并存，需要给 ALSA 配 dmix/plug 复用，尚未做。

### 「播放了却没声音」的真正原因：ALSA 路由没打开

关键证据（播放进行中读寄存器，而不是播放结束后读）：

| | 无声时（PipeWire 在播，pid 存活） | 有声时（同一文件、同一音量） |
|---|---|---|
| `supply_owned` | **0** | 1 |
| `reg[0x1df]` PA | **6f**（bit7=0，PA OFF） | ef（bit7=1，PA ON） |
| `reg[0x1e0]` 模拟增益 | **3c**（低档） | 04（最高正常档） |
| `reg[0x2e7]` 数字增益 | **f4**（-12 dB） | 00（0 dB） |
| `reg[0x30f]` RX7 时钟 | **00**（关） | 40（开） |

即：PCM 在 RUNNING、数据在灌，但 **DAPM 扬声器路径根本没上电**。

原因：`Mi4 Speaker Gate Switch` 与 `SLIMBUS_0_RX Audio Mixer MultiMedia1`
这两条 ALSA 路由没有打开。UCM verb 未生效（`alsaucm -c hw:0 get _verb`
报 No such file or directory），EnableSequence 没跑，gate 保持 probe 时的
默认 OFF，于是功放不供电，PipeWire 往死胡同里灌数据。

**用 amixer 把两条路由都设为 1 之后，同一份 PipeWire 播放立刻出声**，
寄存器变为上表右列。已 `alsactl store` 存入 `/var/lib/alsa/asound.state`，
并把这四条初始化写进 `mi4-audio-init.sh`（含等待 card0 出现、设路由、开 divider）。

**排查方法论**：
- 不要在播放结束后读 `mi4_speaker_state`，那时 cleanup 已把寄存器复位成
  3c/f4，会让人误判"增益档没生效"。
- 也不要把 `dev_info` 里那句 "100 percent / 0 dB digital gain, PA ON" 当证据，
  它只在 PRE_PMU 真正执行时才打印；无声时根本不会出现。

### 重启后发现的第二个问题：vreg-boost 时序

第一次重启（17:55）后，服务显示 `success`，card、两条路由、divider 全部正常，
但播放无声。播放中读寄存器：

```
supply_owned=0
supply_hw_enabled=-19      ← -ENODEV
reg[0x1df]=6f             ← PA OFF
reg[0x1e0]=00
```

dmesg 0.84 s 处：

```
qcom-rpm-proc remoteproc: Failed to create device link (0x180)
  with supplier vreg-boost for .../regulators-1
```

即 codec 在 RPM `vreg-boost` 可用之前就 probe，`devm_regulator_get()` 返回
`-ENODEV`，驱动**把该错误缓存住、之后不再重试**。所以 card / 路由 / 增益看起来
全对，实际功放永远不上电。系统稳定后 `modprobe -r` + `modprobe` 重载 codec
立刻恢复（`supply_owned=1`、`supply_hw_enabled=1`、PA=`ef`、analog=`04`）。

**修复**：`mi4-audio-init.sh` 改为

1. 先只加载 DT overlay；
2. 等 `vreg-boost` 至少有一个消费者（`num_users > 0`，最长 90 秒）；
3. **干净卸载再重载** codec，使 `systemctl restart mi4-audio-init`
   在任何时候都能修复坏 probe，不必重启整机；
4. 等 card → 设两条路由 → 开 divider。

验证：手动重载后播放正常；`systemctl restart mi4-audio-init` 返回 `success`，
card / 路由 / sink 均保持，播放中 `supply_owned=1`、`supply_hw_enabled=1`。
**开机时序本身仍需下一次重启确认。**

### 第三个问题（也是最隐蔽的）：PipeWire 协商 S24_LE，codec 只吃 S16_LE

现象：同一首《欢乐颂》，
`aplay -D hw:0,0` **有声**，`pw-play`（PipeWire）**无声**；
而 PipeWire 播放时寄存器与 rc7 成功值**逐项完全一致**
（`supply_owned=1`、`0x1a2=80`、`0x1df=ef`、`0x1e0=04`、`0x2e7=00`、`0x30f=40`、
`0x38e=05`、`ifd[0x040]=05`、`ifd[0x180]=01`），`0x1eb=00` 无过流。

根因：播放中读 `hw_params`，PipeWire 协商的是 **S24_LE**：

```
access: MMAP_INTERLEAVED
format: S24_LE        ← 关键
channels: 1
rate: 48000
```

而 rc7 验证成功、以及 `aplay` 默认使用的都是 **S16_LE**。
WCD9320 这条 speaker 路径对 S24 数据的处理不正确，
所以**寄存器全绿也完全听不到**，极易误判成"硬件坏了"。

修复：`~/.config/wireplumber/main.lua.d/51-mi4-format.lua`
（本机是 WirePlumber 0.4，用 Lua 规则，不是 0.5 的 `wireplumber.conf.d`），
对该 sink 强制：

```lua
["audio.format"]   = "S16LE"
["audio.rate"]     = "48000"
["audio.channels"] = 1
```

重启 `wireplumber` 后 `hw_params` 变为 `S16_LE`，**同一份文件立刻有声，用户确认听到**。
`wpctl inspect` 也确认节点属性 `audio.format = "S16LE"`。

**排查口诀（重要）**：
PipeWire 无声但 `hw:` 有声 → **先看 `hw_params` 的 format 和 rate**，
不要只盯着 codec 寄存器。寄存器全对也可能只是"参数正确但没有有效音频数据"。

### 重启验证通过（2026-10-18 18:15）

用户重启后（uptime 1 min）核对，**未做任何手动干预**：

- `mi4-audio-init.service` = `active` / **success**
- `card 0: Mi4Taiko` 自动出现
- 两条 ALSA 路由均为 `on`
- divider `applied=1 factor=2`
- `~/.config/wireplumber/main.lua.d/51-mi4-format.lua` 仍在并被加载

重启后**首次**用 PipeWire 播放（`pw-play mi4-long-test.wav`）：

```
hw_params:  format = S16_LE, channels = 1, rate = 48000
codec:      supply_owned=1  supply_hw_enabled=1
            reg[0x1df]=ef  reg[0x1e0]=04  reg[0x2e7]=00
```

用户确认**听到声音**。

→ 三个问题（ALSA 路由未开、vreg-boost 时序、PipeWire S24_LE）均已随重启**自动恢复**，
内置扬声器的日常播放链路（普通应用经 PipeWire）可用。

### 响度结论（2026-10-18 18:17）：已到硬件极限，用户接受现状

| 项目 | 当前值 | 说明 |
|---|---|---|
| 模拟增益 `0x1e0` | `0x04` | 倒置量程 0..8 的顶格，**已是最大** |
| 数字增益 `0x2e7` | `0x00` | 0 dB，再往上即过放大 |
| amixer 音量控件 | **一个都没有** | 没有中间档可调 |
| PipeWire 音量 | 1.00 | 软件已满 |

关键点：**之前觉得"很轻"是测试音的问题，不是声卡的问题**。
`mi4-long-test.wav` 峰值仅 3000（-20.8 dBFS），是 rc7 为安全使用的低幅度信号；
换成正常音乐电平（峰值 25251，-2.3 dBFS）重测后，用户确认响度可接受并接受现状。

**不要为了更响去改模拟/数字增益档**：0x04 + 0dB 已是验证过的最高正常组合，
继续加大只会削波失真。若将来仍嫌小，只能软件放大（>100% 会失真）或改硬件。

### 尚未验证（不要当成已完成）

- 耳机 / 听筒 / 麦克风 / 通话、长期播放、息屏唤醒后的音频。
- 系统音量滑杆与静音键的联动（`wpctl set-volume` 已能改音量，但未与 UI 对照）。
- rc8 仍未编译（WSL 源码 Windows 端只读），当前靠 modprobe.d 参数等效实现。
- 重启持久化：还没有真正重启验证过开机服务。
- 耳机 / 听筒 / 麦克风 / 通话、长期播放、息屏唤醒后的音频。
- 立体声下混到单声道 48 kHz 的实际表现、系统音量与静音联动。
