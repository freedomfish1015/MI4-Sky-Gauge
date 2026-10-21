# Sky Gauge 横屏开机图：已刷写，首次重启视觉验收通过

## 随后单独隐藏 lk2nd 版本文字

用户提供新照片后，发现正常开机仍由 lk2nd 画出板型和版本两行文字。已按新请求最小修改其正常画面函数（4字节ARM返回指令+镜像ID更新），boot现为 `edf91d38f7cd87b5a59480ac5b0f00acb79a71aaa5f16577047959e47e4b035d`；**本文件原1852dd...为此前刷Sky图标时的历史boot SHA，不再是当前值**。Linux尾部、Sky Gauge aboot和logo全部未变。详见 `LK2ND-HIDE-FOOTER-20261020.md`。随后已实际重启，用户确认 **“文字消失，视频和仪表正常”**，系统服务正常、日志约59FPS。

## 首次重启验证（2026-10-20 23:29–23:30，Asia/Shanghai）

用户明确要求“开始重启验证”后，先确认 USB online=1、电压3.723801V、21%，aboot/logo SHA均仍为本次新值，再执行 `sync; sudo systemctl --no-block reboot`。没有再次修改分区。

用户明确确认：**“横屏图标、视频和仪表都正常”**。因此新原厂 aboot 已经在真实设备上完成本轮普通启动，最早 Sky Gauge 图标和横屏方向通过视觉验收。

系统串口 COM10 已恢复，uptime从42分钟归零；kiosk与motion服务均 active、NRestarts=0。启动日志23:30:17确认 `BOOT_HANDOFF_TO_GAUGE same_window=1 warm=1 static=1`，KMS为1080×1920@60Hz；刚进入仪表日志约56.1FPS。详见 `sky-logo-prereboot-20261020.log`、`sky-logo-reboot-command-20261020.log`、`sky-logo-after-reboot-20261020.log`。

这次仅为电脑发起的正常重启，不等于已测试拔线完全关机再插线的冷启动，也没有测试新 aboot 下原厂 Fastboot 或 EDL 救援。早期启动日志出现 BLE adapter 尚未就绪，不能把视觉验收泛化为所有蓝牙连接均已测试。没有为此更改原有蓝牙配置。

随后做启动稳定后复查时，COM10和相关USB设备已从电脑消失，原因未确认，未推断是故障或用户拔线；没有发出第二次重启/救援命令。用户此前的画面验收和系统成功返回证据有效，但此后蓝牙状态未取得。最新文档目前只保存在电脑，尚未同步回手机。

下面“尚未重启”的文字是写入后、首次验证前的历史状态。

## 已持久写入（用户明确要求“先刷吧”之后）

用户已了解低电量及 EDL 未验证风险，明确要求先刷。复查 USB online=1、约3.72V、22%；安装器仍要求在线供电、电压≥3.65V、SOC≥15%，未跳过分区和旧哈希检查。

`flash_sky_logo_guarded.py --write-sky-logo` 已执行成功：先写 logo 全分区并逐字节读回，再写 aboot 中偏移 `0x48200` 的同一512字节扇区，整4MiB读回验证，确认**仅 `0x482ac…0x482b1` 六字节改变**。boot 全32MiB前后哈希均未变。

- 当前 aboot SHA256 **`362986d35fe58e55508615fc806483a4533e55f83fa9ab631ed1d7d9cb7c3f40`**。
- 当前 logo SHA256 **`47dbe469e9fcb84280f741161e1e76a67abe4b008d17f3f91bcea86fa7b173c5`**。
- boot SHA256仍为 **`1852dd1bda97b9bee008ccf46165db11c17e9b35dd40d18255a0c665157e8a1a`**。
- 新鲜备份目录（root，0700）**`/home/umeko/desktop-offline/backups/sky-logo-flash-before-0au581zy/`**：aboot.img、logo.img、aboot-sky-expected.img、before.json、success.json，均写入fsync并校验。
- 日志 **`sky-logo-flash-verified-20261020.log`**。
- **尚未重启；未观察到真实开机图、方向或新 aboot 下 Fastboot 功能。不能宣称整机启动已验证。** 未停止或重启仪表、GPS、蓝牙等现有服务。

安装器有失败回退：若图片写入失败则恢复图片；若 aboot 写入/读回失败则恢复原512字节扇区并全分区比较，随后恢复图片。首轮尝试仅在写入前的设备尺寸 ioctl 处退出（armhf 的 BLKGETSIZE64 编码不同），没有任何写入；已修正为按原生 sizeof(size_t) 编码，重跑全部检查成功。电脑6项写入/拒绝并发/损坏素材/范围保护测试，以及8项真实ARM离线测试通过。

### 回退（必须在用户要求回退时执行，不要自动调用）

Linux 正常时，在当前目录执行：

`sudo python3 /home/umeko/desktop-offline/restore_sky_logo_guarded.py --restore-original-mi`

该脚本严格要求当前 aboot/logo 为本次新 SHA、备份为原 SHA；只恢复同一512字节扇区和原空 logo，并再次验证 boot 未变。拒绝覆盖后续其他 agent 改动；不自动重启。脚本已准备并部署，**未执行**。

若 Linux 无法启动，电脑原 aboot 有效备份为 `mi4-aboot-sky-original-verified.img`（SHA ff7bd7...c1212）。恢复必须区分原厂 Fastboot 与 lk2nd：原厂画面可能已变成 Sky Gauge，不能只凭兔子判断。先用 USB 枚举和 getvar 核对再制定恢复命令。若根本进不了原厂 Fastboot，EDL 仍未实测，不能用下载到的 UNVERIFIED programmer 直接盲刷，也不要擦 GPT、userdata、modemst 或套用整套官方ROM覆盖当前Linux。

下面为历史准备记录，其中“尚未刷写/未放行”仅指用户“先刷吧”之前。

## 最新状态（用户回复“接受”之后）

用户已明确接受原厂 aboot 修改风险；继续研究与准备，不代表省略电量、精确字节范围和救援条件检查。

已生成可重复构建的离线候选：

- `mi4-aboot-sky-CANDIDATE-NOT-FLASHED.img`，4194304 字节，SHA256 `362986d35fe58e55508615fc806483a4533e55f83fa9ab631ed1d7d9cb7c3f40`。
- 只改变文件偏移 `0x482ac…0x482b1` 的 **6 个 rodata 字节**，将 `splash\0` 变为 `logo\0\0\0`；没有改变 ARM 指令、MBN 头、代码/资源位置或镜像尺寸。
- `mi4-sky-logo-CANDIDATE-NOT-FLASHED.img`，8388608 字节，SHA256 `47dbe469e9fcb84280f741161e1e76a67abe4b008d17f3f91bcea86fa7b173c5`。
- 独立图片分区格式：512 字节 `SPLASH!!` 头，width=1080、height=1920，随后 RGB888 原始像素；余下分区补零。
- 图片按仪表同方向顺时针旋转 90°。imagegen 素材实际是 1672×941，ffmpeg 仅为 framebuffer 编码缩放至 1920×1080 后旋转；不是原生 1920×1080 矢量源图，不能称无插值素材。
- 构建脚本 `build_sky_logo_candidate.py`，清单 `mi4-sky-logo-candidate-manifest.json`。脚本不访问块设备、不连接手机。

### 真实 ARM 代码离线验证

`test_sky_aboot_emulation.py` 运行备份中的真实 ARM 代码（Unicorn 2.1.4，工具仅安装至本工程 `.sky-logo-tools`，经清华 PyPI 镜像）。真实执行分区名称查找、SPLASH!! 头检查、尺寸检查、正常开机/Factory Fastboot 绘制分支；eMMC I/O/分区偏移、printf、memcpy、显示硬件清屏/flush 用受控桩模拟。不是只验证自己写的解析器。

8 项通过：精确6字节变化；原版找不到logo并回退136×128 mi图；候选读取完整像素且 framebuffer 末尾保护字节不变；坏图片、分区缺失、I/O错误、尺寸不符均回退；Fastboot 分支也能返回并读取新图片。

**副作用**：原厂 Fastboot 也调用同一 splash 加载器，改后可能显示 Sky Gauge 而不是兔子。离线测试仅验证绘图分支正常返回，不等于已验证实机 Fastboot USB 功能；后续必须按 USB getvar/product 判断模式，不能只问用户“是否看到兔子”。

这验证的是执行逻辑与边界，不是电源故障、SBL认证、eMMC可靠性或整机启动保证。原始 aboot 的 image_size=code_size=`0x20be54`，signature_size=0、certificate_size=0；这不是已实测通过修改后 SBL 引导的替代。

### 救援与电量仍未放行

只读清单 `sky-recovery-inventory-20261020.log`：真实机型 Xiaomi Mi4(cancro)，boot SHA 仍 `1852dd1bda97b9bee008ccf46165db11c17e9b35dd40d18255a0c665157e8a1a`，aboot/logo 均仍是原始 SHA。bk1 为 5242880 字节且头40字节全零，不能当作已验证的自动备用引导。

最后电压 **3.695571 V、22%，USB online=1**，比之前24%还在下降。已询问用户是否进入临时低功耗充电模式；尚未收到回答，**没有停止仪表、GPS或蓝牙**。正式写入前重新检测，优先先充足电，不在掉电状态修改引导。

通过国内 GitHub 镜像 ghfast.top 下载了 `mprg8974-cancro-UNVERIFIED.mbn`，来源 `bkerler/Loaders/xiaomi/mprg8974_cancro.mbn`，42544字节，SHA256 `59af2ddd2874159595ad454e62137c81da74edbabc446902ecc803cc1fcee7f4`。**只是名字匹配的研究候选，没有发送到手机运行、未核验芯片/PBL匹配、未完成 EDL 救援握手或回写测试**。不能因为有这个文件就宣称可救砖。

尚未提供/执行写分区安装器，没有重启或进入 EDL，没有改变 GPT/aboot/logo/boot。下一步：先充电；确认可用的救援路径与 USB 识别；之后才写图片并校验，再以最小范围修改 aboot 并全分区读回。不能直接用本清单中的候选当通用刷机文件。

下面保留早期调查记录；其中“待授权”仅指用户回复“接受”之前的历史。

## 用户目标

将最早显示的 mi 标志换成用户提供的 Sky Gauge 图标，按仪表横屏方向显示并高清化。现有 NERV 视频及视频到仪表的切换不变。

## 当前完成

- `skygauge-boot-logo-hd.png`：由内置 imagegen 以用户图片为编辑目标高清重制，黑底，左图形右字样，横屏居中。是 AI 重制，不是原品牌矢量源文件。
- 原始附件位于 `[LOCAL-PATH]`。
- 仅完成素材及只读调查，**没有写 logo、aboot、boot、GPT 等任何块设备，没有重启手机，没有修改现有仪表或视频。**

## 实机证据

`inspect_sky_boot_logo.py` 只读导出 logo 与 aboot，并 fsync、校验 SHA；备份目录：

`/home/umeko/desktop-offline/backups/sky-logo-before-9jewwy36/`

- logo → `/dev/mmcblk0p10`，8388608 字节，非零字节数 **0**。
- logo SHA256 `2daeb1f36095b44b318410b3f4e8b5d989dcc7bb023d1426c492dab0a3053e74`。
- aboot → `/dev/mmcblk0p7`，4194304 字节，SHA256 `ff7bd7e050e5e91a6f50e8e31025c911f4c2f8b2ec73d2e2b3ccbc247b1c1212`。
- 实机不存在名为 `splash` 的分区；GPT 名称为 `logo`。
- 导出时电压 3.720885V，容量 24%，USB online=1。将来写入前须重新检测，不能引用旧读数放行。

## 原厂 aboot 离线反汇编证据

经校验的电脑备份：`mi4-aboot-sky-original-verified.img`（同上述 SHA）。压缩备份 `mi4-aboot-sky-verified-20261020.img.gz`（SHA `60dca850eb11a46961666432659ffe294ee17ef8f88eac38fdcc64d1072d6b0e`）。

MBN payload 从文件偏移40开始，加载地址 `0x0f000000`，地址换算 base=`0x0effffd8`。

- 图片加载函数 `0x0f021190`，`0x0f021198` 将 PC 相对地址还原为字符串 `splash`（文件偏移 `0x482ac`）。
- `0x0f02119c` 调用 `0x0f008f74`，即分区名称查找函数。
- 查找函数遍历分区名，比较长度再 memcmp，**没有 splash→logo 名称别名转换**。
- 加载器先读512字节头，校验 `SPLASH!!`，再比较图片宽/高与 fb 配置，读取像素数据。不能直接使用现代小米 LOGO/BMP 工具的格式。
- 因原厂加载器查找 splash，而实际只有空 logo，单纯把 PNG/BMP 写 logo **不能证明会替换最早 mi**。现有 mi 极可能是内置备用图片。需要继续定位显示调用点/内置图片后，才可制定可靠补丁。

## 风险边界与下一步

此处不是通常的 Linux boot.img 修改。要替换最早原厂 mi，现有证据指向必须修改原厂 aboot 的资源或加载逻辑（或改 GPT，但不建议后者）。**aboot 提供原厂兔子 Fastboot，损坏或签名校验失败可能连 Fastboot 都无法进入**。没有确认可用 EDL 恢复路径，不得自行改写 aboot 或 GPT。

下一步需要向用户明确说明上述更高风险并取得授权；若用户不接受，只能做 lk2nd/Linux 阶段的替代画面，不能宣称最早 mi 已被替换。若授权继续，先研究 aboot 签名/校验及恢复条件，生成离线候选、精确资源边界和保守回退计划，不能直接写入此文中的分析文件。

## 文件传输注意

原有原始二进制导出工具本轮两次超时，留下 `mi4-aboot-sky-inspect-20261020.img`（0字节）及 `mi4-aboot-sky-verified-20261020.img`（部分数据）；**这些不是有效备份，不可用于恢复**。

最终通过 `sky_snapshot_export.py` + `receive_sky_snapshot.ps1` 完成 ASCII Base64 分块，每块2048原始字节，逐块 SHA256，支持按偏移重试，最后验证完整压缩文件 SHA。解压后再次验证原 aboot SHA。

## imagegen 提示词（内置模式）

Edit target: the attached Sky Gauge logo. Create a high-definition faithful boot splash asset, landscape 1920 x 1080, pure black #000000 canvas. Center the original logo lockup horizontally and vertically, occupying about 60% of canvas width and 27% of height: the exact white circular speedometer/G mark on the left, and text exactly 'Sky Gauge' in bold clean sans-serif on the right. Preserve the exact geometry and proportions of the reference white symbol; preserve reference white 'Sky' and light gray 'Gauge' typography. Eliminate the small source's compression/pixelated edges, faithfully redraw at high resolution. Source dark rectangular background and black rounded square merge seamlessly into pure black canvas. No additional text, no decorations, no gradients, no 3D, no glow, no mockup. Logo and text read upright in this landscape asset; phone framebuffer rotation will be done later by boot splash packaging.

提示词目标尺寸不是工具实际输出尺寸的证明；打包前须读取实际素材尺寸，按手机 framebuffer 方向封装。尚未封装或刷入。
