# mi4-sky（小米4 Linux OBD 仪表）：最新交接

> 最新渠道：用户确认当前设备使用正常，已整理 `2026.10.21-stable` 为 **已验证机型的系统稳定渠道**。公开目录 `[LOCAL-PATH]`；镜像SHA `15dff2755937a7e137f4d3e7badf0ed1aabef3073f21791c2782c6b4a36f20ba`。boot/rootfs与R2完全一致，未再刷手机。安装器3修正空参数跨行解析并新增只读诊断，20项离线测试通过；本轮经用户授权只读重启检测后仪表active/蓝牙Powered yes。**原厂boot大小仍为空，Windows安装流程仍测试且可能拒绝，不能宣传通用一键稳定。** 详见 `[LOCAL-PATH]`。

> 2026-10-21 最新发布镜像为 **2026.10.21-candidate-r2**。已合入充电模式跨重启蓝牙状态恢复，以及用户明确要求的 **首次启动自动兔子修复，无额外机主确认**。仅匹配已验证旧Sky aboot才修改4字节；已知原厂/已修复不写，未知版本跳过，USB/SOC50%/3.8V供电保护保留。公开目录 `[LOCAL-PATH]`，独立镜像SHA `3f8004029d2c575df3ee6bb0a3b87faf3d760d4ce380f46c04ea116cdf1fa133`，R2安装器最低版本2；R1已归档。详细证据、哈希和未解决的原厂Fastboot参数兼容问题见 `[LOCAL-PATH]`。**仍未执行清空安装验收，不是通用稳定版。** 以下R1发布说明及哈希仅为历史记录。

> 2026-10-21最新原厂Fastboot画面修复：用户明确授权当前18%直接刷后，只修改aboot偏移0x2467c的4字节（同一512B扇区写入）；当前aboot SHA **d9ed7759fd8ed89cdd4351d582e45428316ab7ac6788bca4a45444c8b3dd5d49**。boot724783.../logo47dbe...不变。新鲜备份`backups/fastboot-rabbit-before-3t6hc569/`。用户已确认FASTBOOT兔子；Windows USB/fastboot product查询通过，未做flash/erase测试。从Fastboot正常reboot后，用户明确确认 **“Sky Gauge、仪表和触摸都正常”**，本轮正常启动验收通过；未做拔线冷启动按键入口实测。**另发现原厂不报告version-bootloader、partition-size:boot，现有Windows候选安装器会拒绝，应单独适配，不能宣称已可自动全量安装或直接删检查。** 详见`fastboot-screen-recovery-20261021/README.md`；旧aboot362986...现为历史值，旧logo回退脚本不再匹配，禁止绕过哈希。

> 最新安装包任务（2026-10-21）：新增独立 Windows 安装器及可替换 `.mi4sky` 单文件镜像包，均在 `[LOCAL-PATH]`。当前为 **candidate，未执行真实全量flash、未验证新机首启**。只支持已确认的 Mi4 LTE/JDI/mxt640t profile；只从原厂兔子 Fastboot 写 userdata+完整boot，不允许lk2nd偏移模式。10项离线安装器测试、实际包校验、ext4检查及ARMhf chroot冒烟通过；没有清空/重启原机。镜像包SHA `6df0bfd8c28422a4109bb09594d0cb4a33768960d30bc47945ffb34ea75aa29a`，约754MiB。干净镜像不带原机配对/轨迹/Wi-Fi/主表MAC，Sky首次需绑定本机主表。完整说明见 `mi4-sky-installer/DEVELOPER-HANDOFF.md` 和 `release/安装与使用说明.md`；源tar/私有导出日志/失败64KiB残片禁止当交付包。**这次仅在电脑副本中修改通用初始化，未覆盖手机现有APP/boot。**

> 最新设置页品牌更新（2026-10-21）：标题改为 `MI4 Sky Gauge`，设置页头像使用用户提供的 sklogo.png；当前 settings SHA **2a4de0c6d491b5d62ec456bee2d1a40fda0f7fd6490c00c658ebf0813e96ed43**。仅新增独立图片与设置页绘制，原主仪表插画、开机画面、记录逻辑及接口不变。5 项测试通过，热重载恢复，备份 `/home/umeko/desktop-offline/backups/mi4-sky-settings-brand-before-3oh0n_3g`。源码与预览见 `settings-branding-20261021/`。下面 74406f... 是品牌更新前版本，勿强行绕过哈希覆盖现有设置。

> 最新任务（2026-10-21）：手机仪表端统一命名 **mi4-sky**，不要与 ESP32 SkyGauge 主表混淆。G值/GPS 设置标签现已换为 LOG 数据传输；单个配套小程序内扫码二维码、mi4-sky 热点、只读文件接口和 RaceChrono CSV v3 按需导出均已部署。用户明确选择 CSV v3 供电脑/其他分析软件使用，不是导回 RaceChrono App。32 项测试通过；实机转换 4,772 条 / 528,538 字节 / 3.130 秒，原 LOG SHA 不变。小程序无 AppID，仍为未发布草稿，按用户要求先做手机端。当前 settings SHA **74406f4bce2646cb30f1a2a128fc9fe05a0594ff54520923ad99ce4f4c815664**，下面 f621/38eff 等为历史状态。没有改 boot、硬件修复、G 值算法或采样记录器。完整细节和回退备份见 [MI4-SKY-LOG-HANDOFF-20261021.md]([LOCAL-PATH])。PC 根目录 APP 有未部署的调试待机改动，禁止整体覆盖手机。

> 最新用户任务（2026-10-21）：已从G值/GPS设置页删除“自动回中·无需归零”按钮及其点击响应，只改已部署gauge_settings.py，自动回中算法保持不变。当前settings SHA为 **f621921c024b6cf0d92d26ab6a289d82a0376307b6a1914ca8c236f6a905142b**，下面38eff8...为历史值，不要绕过旧安装器哈希覆盖新UI。热重载首帧PID854/uptime311.58，未重启；主APP/运动显示/采样daemon/自动回中算法哈希均未变。备份`/home/umeko/desktop-offline/backups/remove-autocenter-ui-before-8db350ck`，文件与5项测试见`g-ui-remove-auto-center-20261021/`。用户已切换到本任务，未继续开机测试。

> 最新补充（2026-10-21）：补画版普通重启视频931207...确认Logo覆盖了中间等待，但仍3次黑屏；最后约2.6s与launcher主动背光0→恢复完全对应。已进一步只更新launcher为60583c...4c71，创建SDL前保持原亮度，保留异常恢复；热测成功、用户确认没有白闪，并已按授权正常重启等待新录像。单文件备份`/home/umeko/desktop-offline/backups/keep-logo-light-before-u51i6cl2`。**没有宣称完整开机无黑屏，前两段引导/内核交接尚未修改。** 当前精确回退顺序及日志见`CONTINUOUS-LOGO-20261021.md`末尾，优先于下面684e...launcher值。

> 2026-10-21最新：用户确认25秒录像是新录像，不能据文件名当旧文件。有限8秒测试确认rootfs Logo确实稳定可见，只在回仪表时闪黑。现已部署“被清屏时补画，SDL接管前退出”版，仅替换rootfs4个启动文件；BMS单位/驱动及boot/aboot/logo/APP不改。热测成功，备份`/home/umeko/desktop-offline/backups/continuous-logo-before-d5aa7qfc`。已按用户“准备录像，可以重启”正常重启，完整视觉结果待回报，**未宣称解决**。见`CONTINUOUS-LOGO-20261021.md`，优先于以下已回退实验状态；下面旧rollback_logo_hold脚本不再匹配当前SHA，不要强行执行。

> 2026-10-21最新视觉实测：用户明确报告开机闪黑3次。rootfs分段Logo没有解决；随后提前创建单一SDL窗口也仍闪黑3次（Logo14.98s、首帧18.69s，NRestarts=0），**本轮优化未成功，不能标记完成**。单窗口实验已精确回退到上一版rootfs静态Logo方案，BMS原Before=kiosk恢复，boot/aboot/logo及APP完全未写。实验与回退见`EARLY-LOGO-EXPERIMENT-20261021.md`；下一步等待用户完整开机录像，确定每次黑屏的时刻，不要盲目再次改引导。优先于下面“完整重启待观察”的历史描述。

> 最新静态Logo衔接（2026-10-21）：rootfs早期native Sky图+SDL同窗口Logo等待已部署，热重载和13项手机测试通过，**完整重启视觉检查尚待用户准备**。未改boot/initramfs，最早内核交接可能仍短黑；详见`LOGO-HOLD-20261021.md`。当前root launcher SHA为98b696...c6ae、curtain基础单位为31af5d...a81c，不再是旧c6a85.../5b552...。仪表主代码和设置未覆盖，永久隐藏光标仍保留。

> 当前最终启动状态（2026-10-21）：用户确认RAM隐藏光标测试通过并明确授权“保存”，已永久添加vt.global_cursor_default=0；只写Linux header一个512字节扇区，正常重启参数仍生效。当前boot完整SHA **724783b32b5b09dd53245ec42277df4ef3b85cd1da7560ced1c0caaa92da8d2b**，旧edf91...为历史值；kernel/DTB/ramdisk、lk2nd、aboot和logo未改。无动画启动保留，普通重启首帧19.53秒。新备份和精确回退见`CURSOR-PERSISTED-20261021.md`，优先于下面所有“光标待处理/未改boot”阶段说明。

> 同日第二轮：新增rootfs光标默认关闭与BMS提前初始化，重启首帧19.50秒，仍未显著缩短；用户启动视频显示早期底角光标仍需处理。详见`FAST-STARTUP-CURSOR-20261021.md`。目前再次USB断开，未擅自改写boot，禁止复用曾导致黑屏的旧quiet_boot写入方案。

> 2026-10-21 最新启动变更：用户已取消开机视频，现为 Sky Gauge 静态引导图后直接进入仪表；真实重启首帧为内核启动后19.79秒（此前约32.5秒），旧视频检查timer已停用。详见 `DIRECT-STARTUP-20261021.md`。设置充电模式见 `CHARGE-MODE-20261021.md`，启动图和文字隐藏分别见 `SKY-BOOT-LOGO-20261020.md`、`LK2ND-HIDE-FOOTER-20261020.md`。下面2026-10-19内容为历史阶段，不要按旧描述重新启用视频。

更新日期：2026-10-19（北京时间）。本文件优先于旧交接里的历史状态；旧文档保留为诊断证据，不能直接照旧版本重新安装。

## 1. 用户当前意图与已验收结果

设备是白色小米4 LTE，已运行原生Ubuntu Linux ARMhf，不是MIUI/Android容器。当前作为横屏触控OBD专用仪表使用。

当前已完成且用户实机确认：

- 设置顶部按钮缩小，扩大列表，PID列表改为上下滑动：用户答“布局和PID滑动都正常”。
- 清除仪表上的“REI AYANAMI/绫波丽/零号机/EVANGELION/OBD-II TELEMETRY/ENGINE SYSTEM”等装饰文字，只留必要数据标题、单位、刻度。
- 四个侧窗放大并移到四角，保留白色/冰蓝配色和绫波丽插画、中央六边形转速表；数据字体加大。
- 设置新增“窗口数据”：左边选四个位置之一，右边上下滑动选择数据类型，保存后右滑返回；标题、单位、数字同步变化。
- 用户答“布局合适，窗口数据切换正常”。

**用户明确要求“这些先不加入，先保持现在的主题不变”——指暂缓事件效果。不得擅自加入告警闪烁、事件换图、显隐、自动换主题。之后用户另行授权了上述文字清理/四角布局调整，这些已完成。**

上一个大方向是对齐最新ESP32固件功能，尤其原PID包和事件系统；目前只完成分阶段移植，不能宣称全部等价。事件核心可用但没有接入可见画面动作，用户暂缓此项。

## 2. 项目和事实源路径

| 项目 | 路径 |
|---|---|
| 手机Linux仪表主工程 | `[LOCAL-PATH]` |
| 新固件源码（不要改动其构建产物） | `[LOCAL-PATH]` |
| 新固件源码commit | `976106c7bce8421ba7aa689a61d79dce4e8e16df`，2026-10-18 |
| 用户另一任务下载的快照 | `[LOCAL-PATH]` |
| 下载说明 | 同目录`README.md` |
| 旧预编译包（不要当最新版刷） | 同目录`legacy-prebuilt-NOT-rebuild.zip` |
| 主题商店本地源码 | `[LOCAL-PATH]`（本次核对HEAD 7ac481f） |
| USB/fastboot辅助工具 | `[LOCAL-PATH]` |
| 原始开机视频（未修改） | `[LOCAL-PATH]` |

GitHub网页/API曾对`steveEcode/obd-theme-store`返回404，但用户Edge能打开；这不代表仓库不存在。后来找到了上面的新源码，本地源码已足够继续，不应反复要求用户重新下载。浏览器Computer Use曾因无法确定网址被安全机制停止，不能绕过。

到新固件仓库工作前必须完整读`AGENTS.md`、存在时读`AGENTS.local.md`。其中明确ELM查询必须单线程，不交错发送。新仓库与手机工程的运行环境不同，绝不能把ESP32的bin/分区表刷到手机。

## 3. 当前电脑文件SHA256

交接时已核对本地文件；本轮成功传输/安装时手机SHA相同。**交接时手机未连接，未再次读取手机现状；修改前请重新核对，防止覆盖其他AI的后续工作。**

| 文件（主工程内） | SHA256 |
|---|---|
| `gauge_sdl.py` | `80fbd9bfa4501c43c93818e4db2c7e7d09ff325c9a7c6515cef5ce7238d46ec1` |
| `gauge_settings.py` | `804d9f67e495acfc457ec4653993ef55200bc30ccdf6482ac0a7540aa3f6a8de` |
| `gauge_windows.py` | `e58ecef5f9a8aa76c0d1ac273f4ea0c7c9c5afbc2aa457b1bbca406f8b2f6e97` |
| `gauge_compat.py` | `7fdbf5a24ead234ac1adcf709f3142fc3b626d887d2e6148a53b994fb148e6df` |
| `gauge_compat_ble.py` | `20b206fb6607c008d21c6a95db8c738dae2c787eb15b5f086c3e0123b198dcf3` |
| `boot_video.py` | `cb421b1549cd5554b93fab8026306b54d155f751a3db1b9aa0412190a7ef3e0f` |
| `launch_boot_video.py` | `22ace6acfcef4cf47d773601c6de2bc564d57bcd1a575a72b12149aa4eb7f223` |
| `compat/build-armhf/libmi4compat.so` | `51f02401ee956a9d58c30755eb73b7d24a7ebc052cbca0ea2de6bbdc836660dc` |

手机主应用目录：`/home/umeko/desktop-offline`。主仪表的上述源文件和native库均在此目录及`compat/build-armhf/`。

root开机播放器目录：`/usr/local/lib/obd-gauge/`，其中`boot_video.py`和`launch_boot_video.py`以root目录版本为准。别只修改用户目录同名副本后误以为开机已更新。

## 4. 连接方法与安全边界

- 手机USB串口：**COM10**。ESP32模拟器：**COM6，不要误操作**。
- 交接时只发现COM6；需要用户重新连接手机才能做实机操作。不要对COM6运行手机命令。
- 手机用户：`umeko`；串口sudo凭据沿用用户现有设置，本文不保存明文密码，不在日志输出凭据。
- WSL构建发行版：`Mi4Build`。Windows上的D盘映射为`/mnt/d`。
- 串口辅助：`serial-command.ps1`，参数`-PortName COM10 -CommandText '...' -TimeoutSeconds 15`，必要时`-OutputPath`留日志。
- `serial-command`偶尔第一次登录缺提示符可重试一次；超时不保证远端命令已终止，不要立刻并发发送另一个串口命令。
- 别在串口命令里嵌套难以转义的PowerShell/bash引号；复杂命令用PowerShell单引号here-string。工具会回显base64命令，不能把密码放入CommandText。
- 文件发送：`send-usb-file.ps1 -PortName COM10 -Path <本地绝对路径> -RemoteName <ASCII名称>`，会SHA校验，接收至`/home/umeko/desktop-offline/`。
- 重启后需要：`cp /home/umeko/desktop-offline/usb-receive.py /tmp/usb-receive.py`。持久接收器已保存，不需重新开发传输协议。
- 旧串口长输出约15KiB可能截断，回传大文件用已有二进制传输助手/分块SHA校验，别通过长文本裸传。
- 遵守用户要求：需从GitHub下载的公开文件优先国内可用镜像，并核验原始SHA；私有内容/凭据不能交给未知代理。

## 5. 渲染与最新四角布局

- 原生像素：portrait表面1080×1920，逻辑landscape640×360，RS=3，旋转90°后显示1920×1080。不是先540p再放大。
- SDL2 KMSDRM + OpenGLES2呈现；Cairo CPU绘制。静态底图/字体预缓存，脏矩形只刷新改变区域。
- 双线程管线：SDL/事件泵在主线程，Cairo在worker，保持一个待交付帧；上传完成后才让worker改下一帧。
- 字体加载保持lazy。boot `VideoScreen`导入`Screen`不能顺带加载Pango，避免开机额外延迟。
- 四角卡片：W=156/H=112；X=(12,472)，Y=(24,224)。原来143×92，面积增约33%。
- 数字字号29→35，标题10→12，刻度字号也加大。中央转速表几何保持不变。
- `gauge_windows.py`维护12种标准数据及窗口绑定，支持当前原格式profile里的`veh.*`自定义信号。`gauge_sdl.Gauge.cards`是每实例绑定，**不要修改全局CARDS去做用户配置**。
- 标题/单位变更或profile变化时只重建一次static底图并强制全帧恢复；之后继续脏矩形。增大字体时必须同步检查`card_value_box`测得glyph边界，曾出现过数字消失的问题。
- 为修复低转速短弧起点圆帽的Cairo裁剪残留，arc_box在低于1000rpm附近覆盖整个短前缀；不能随意移除。
- 无有效数据为nan/`--`，不能默认0。`gear`不做平滑插值。没有加入事件变色/换图等新效果；原有静态温度/低电压着色逻辑保留。

**最新帧率（用户询问时的实际日志）**：最近约24秒12个采样平均46.6fps，40.3–56.8fps，最新47.7fps。不是锁60。不同窗口选项/动态更新情况会改变性能；当前CPU/GPU占用没有重新测量，不要引用早期“CPU16%”旧值作为现状。

## 6. 设置、窗口绑定和数据可用性

当前设置4个标签：PID数据包、蓝牙连接、屏幕亮度、窗口数据。

- 顶栏按钮30逻辑像素高，标签y42–70。
- PID列表y82–326，每行52；上下滑动+滚动条，拖动不误选，无下一页。
- BLE列表y122–310，每行44；扫描/连接/断开，列表独立滚动。
- “窗口数据”左边选四个位置，右边滚动数据列表；支持重复显示同一数据；右滑返回。
- 绑定存到`/home/umeko/.config/obd-gauge/settings.json`的`windows`，依次为左上、右上、左下、右下。默认电压、水温、油温、速度。
- 支持电压、水温、油温、速度、转速、档位、节气门、发动机负荷、进气温度、增压、油压、空燃比。
- “可选”不等于该车型/适配器一定支持。未知值显示--。用户已做过切换测试，**当前实际windows数组需连接后读取，不要用默认值覆盖用户选择**。
- `SettingsBleSource.read_signals()`输出完整原信号键的工程值或None。
- 旧standard/bmw-g-sim仍按旧的五基础值采集；仅窗口选择了额外标准类型时才增加0111、0104、010F、0144查询。空燃比按原Generic公式14.7/32768、8–22有效范围；不编造未知油压/增压/档位请求。
- 改窗口不重连BLE。切换数据包仍干净断旧连接再连新连接。窗口类型切换清理额外旧缓存，等新样本后显示。
- 新原包使用完整native状态机，按profile策略采集。主数据线程单在途请求，不能同时调用旧`BleElm327.command`。
- 上次重载日志profile=bmw-g-sim，地址4C:11:AE:30:FA:0A，用户自行切换而来；后续操作前重新读设置，不擅自切换车型。

## 7. 原固件PID/事件核心移植状态

详见`COMPAT-976106C-PHASE1-20261019.md`。重点：

- 17个原始`vehicles/catalog/*.vehicle.json`原样安装在`~/.config/obd-gauge/pid-profiles/`；加旧两个选项共19。
- 真正的规则引擎在`main/theme_engine/rules/tr_parse.c/tr_eval.c`；旧`app_event.c`只是跨任务消息，不是主题事件规则。
- 通过`compat/mi4_compat.c`复用原C模块，未用Python简化替代；含校验、RPN、默认继承、源回退、协议检测、多帧、CAN窗口等ELM状态机。
- `gauge_compat.py` ctypes句柄单owner，显式close，返回字符串sg_free；`gauge_compat_ble.py`有界接收队列，取消时stop_notify/disconnect/释放native。
- native校验保留原白名单，拒绝写入/清码/执行器命令；允许01/09/21/22读取。实车未知时不要自动激活车型。
- 原始37包/示例全部校验、17车型引擎golden通过；规则79步+185步通过、RPN605650检查、缓存6061843检查、原ELM引擎1994检查通过。此为测试，不是17车型实车认证。
- 最新整体Python回归**75项通过**。手机最新设置18项通过，其中真实SDL dummy输入一项未启用而跳过，其余离线测试通过。手机native桥此前9项通过。
- **事件暂缓**。若以后用户要求恢复，需先做原主题ZIP/sidecar/元素ID与SDL绘制层绑定、资源安全校验/基底恢复/动画预算；核心可调用不等于画面支持。
- 注意值域：Vehicle.snapshot返回工程值，而事件固件读取可能是`signal_store` delivered定点编码。接入规则前核对`contracts/signals.json`，避免电压/boost/AFR阈值错倍数。

## 8. 开机视频、电源和静默启动

- 拔线显示20秒倒计时，保持开机按钮取消；重新插线也取消。超时正常poweroff；用户已验证重新插USB自动进入仪表。
- 一键关机按钮在设置右上。root电源服务固定白名单命令、SO_PEERCRED限root/umeko，不允许任意shell。
- 视频是原NERV片，保持半音量0.5，完整音视频EOS后同一SDL窗口交给仪表，不能为了快而提前跳过结尾。
- 音画同步已修复：appsink必须保留`sync=true qos=true max-lateness=50000000 processing-deadline=0 max-buffers=1 drop=true enable-last-sample=false wait-on-eos=false`。
- 之前坚持显示361帧导致12秒媒体用22秒播放，音画不同步。修后205帧实际12.04秒、媒体12.14秒，用户确认同步。丢掉迟到画面以保实时进度，不是截断视频。不能恢复旧drop=false。
- 白闪修复：BacklightGuard把亮度关至0，首个解码YUV帧连续present两次后恢复原亮度；构造/播放失败及ExecStopPost都有恢复路径。不要在ARGB占位帧后就提前恢复。
- 声卡ready标记`/run/mi4-audio-init/ready`，避免开机查询尚不存在的DBus；硬件音频init脚本没改。现kiosk与audio并行准备，仍存在约十几秒启动等待，尚非即时视频。
- `obd-boot-curtain.service`绘制NERV首帧、rootfs sysctl及ShowStatus抑制文字；没有解绑控制台/KD模式。

### 持久boot当前状态（非常重要）

真实boot `/dev/mmcblk0p19`，32MiB。前512KiB为lk2nd，Linux Android header在offset524288。

当前持久cmdline是原始参数后追加 **` quiet loglevel=0`**，两条console仍保留。顺序不能反：`loglevel=0 quiet`被内核后面的quiet提高日志级别，会显示照片里的qcom_rpm/DT overlay错误。

- 当前完整boot已验证SHA：**`1852dd1bda97b9bee008ccf46165db11c17e9b35dd40d18255a0c665157e8a1a`**。
- 最早完整原始backup：电脑`boot-before-quiet-20261018.img`，SHA **`5715032761b50157ea495d5dfb3d71b2b6de300f00ce7681f48f154dd9f67653`**。手机另有`/root/mi4-boot-before-quiet-approved-20261019.img`同SHA。
- 中间版本顺序错误的完整boot备份：`/root/mi4-boot-before-quiet-orderfix-20261019.img`，SHA `bd8c176facaf7508b7cc106242705b04792d882c9f83e6b58336b203672e523e`。
- 只改过Linux header cmdline偏移524352处512字节；写前新备份，写后整个32MiB逐字节核对，其余kernel/DTB/ramdisk/lk2nd不变。
- `persist_approved_quiet.py`与`persist_quiet_order_fix.py`已经执行完毕，**不要重跑**；它们有精确源SHA和拒绝已有备份限制。
- 旧`quiet_boot.py`会去掉console等，曾导致黑屏和USB失联，写功能已禁用，不能重启用。
- 不要盲刷旧镜像，否则会丢OCV/WLED/音频修复。只有新的备份/校验/用户授权方案才可改boot。

### 恢复Fastboot经验

Fastboot序列号5b628616。`getvar product`：兔子厂家模式MSM8974；lk2nd文字模式lk2nd-msm8974。version-bootloader空，不能靠它区分。

可靠进入法：用户先到兔子，持续按音量下，PC执行`fastboot -s [DEVICE-SERIAL] continue`，再getvar product确认lk2nd，用户松键后才boot临时镜像。不要反复让用户抓“mi亮起后按键”的时机。

**厂家Fastboot flash boot是原始分区；lk2nd flash boot会加512KiB偏移。不能把完整32MiB原始备份通过lk2nd flash boot写入。**

## 9. 硬件修复不要覆盖

- 用户其他AI修复了OCV表数值大10倍的问题。现在boot备份含该修复，不能刷旧boot将它覆盖；修正SOC不等于已验证电池健康度。
- WLED左右亮度、亮度滑块、触控已由用户确认正常。
- 内置声卡wcd9320已接通；保留vreg-boost等待→干净codec重载→路由→MCLK时序。WirePlumber强制S16LE，UCM按Mi4-Taiko匹配。
- 不再加大硬件增益；此前已达正常硬件上限。视频减半用播放流音量，不改codec增益。
- 历史息屏/长待机黑屏/触控失效不应因当前演示正常就宣称已根治；若再现，分别查系统睡眠、触控和显示，不启用未经验证的睡眠策略。

## 10. 当前回退和备份（按层回退，别一键退回很旧状态）

最新窗口功能/四角布局回退：root执行`/usr/local/sbin/rollback-obd-window-data`，恢复用户目录：

- `gauge_sdl.py.before-window-data-20261019`（旧e97d…）
- `gauge_settings.py.before-window-data-20261019`（紧凑列表407a…）

回退后会丢本轮四角布局/窗口选择UI，但保留此前native PID、紧凑滑动设置；新windows配置键保留，由旧代码忽略。仅在有需要时用。

更早回退`rollback-obd-compact-settings`会恢复较大按钮/翻页PID；`rollback-obd-native-pid`更会移除native PID接入。不要误用。

本次`obd-window-data-guard.timer`、此前compact/native安装timer均已停止。不要新建自动回退timer后忘记停，导致用户测试期间被回退。

## 11. 验证、预览、日志

主机回归（WSL Mi4Build，Cairo/GI/SDL已可用）：

```sh
cd /mnt/d/小智-明日香/obd-linux
GAUGE_TEST_NATIVE_SDL=1 SDL_VIDEODRIVER=dummy SDL_RENDER_DRIVER=software python3 -m unittest test_gauge_compat test_gauge_settings test_gauge_sdl test_gauge_power test_boot_video test_boot_curtain test_loglevel_ramtest test_persist_approved_quiet test_quiet_order_fix -q
```

75项全部通过；此命令只跑测试，持久boot脚本只被测试候选函数，不会被写入。

最新预览：`corner-layout-preview.png`、`window-data-preview/settings-3.png`；已目视检查。生成法：

```sh
python3 gauge_sdl.py --export corner-layout-preview.png --flat
python3 test_gauge_settings.py --export window-data-preview
```

关键日志：

- `window-data-install-tests-20261019.log`：手机新文件SHA、18项设置测试结果。
- `window-data-live-20261019.log`：服务active、NRestarts0，profile=bmw-g-sim，原生1080p。
- `compact-settings-arm-tests-20261019.log` / `compact-settings-live-20261019.log`。
- `native-pid-install-and-arm-tests-20261019.log` / `compat-arm-smoke-20261019.log`。
- `avsync-replay-20261019.log`：12.04秒音画同步EOS。
- `quiet-order-write-20261019.log`：最新boot顺序修正和整分区校验。

其他详细记录：`GAUGE-STARTUP-MANUALOFF-20261019.md`、`COMPAT-976106C-PHASE1-20261019.md`、`SETTINGS-COMPACT-SCROLL-20261019.md`。旧文档中的“未刷boot”“等待视觉确认”等只描述当时，当前以本文件和用户最新确认优先。

## 12. 接手建议

用户目前请求的是交接，没有授权新一轮改主题或事件效果。先读本文件，不要自动刷机/重启/切PID/加事件。

如用户后续要求优化性能，先连接手机读取当前windows/profile和新一轮FPS/CPU采样，区分静态设置页、频繁数字变化及多窗显示RPM造成的脏区开销；保持原生1080p、清晰字体和既有硬件修复，不擅自退回540p或删除用户已验收功能。

如用户后续要求继续完整固件对齐，再按新版源码契约逐项做功能矩阵和验收，不能把“17个包解析通过”“事件核心测试通过”当作全部功能或实车兼容完成。
