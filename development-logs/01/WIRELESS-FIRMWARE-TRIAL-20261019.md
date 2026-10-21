# WCNSS Action RX 临时加载测试结果

## 范围与结论

用户回复“开始”后执行首轮临时实机测试，随后按“继续”又执行路由候选与负对照。候选固件均能启动，但尚未接收到 Action 或 SkyGauge ESP-NOW 遥测；不能作为已修复部署。

没有修改 boot、开机默认、SkyGauge 固件、NV 校准、电量、背光或音频。原固件和磁盘内原 wcn36xx.ko 未覆盖。

## 实测（手机日志 2026-10-19）

- 20:22:18 启动临时 systemd 服务 `mi4-wcn-fw-trial`。
- 独立目录 `/lib/firmware/mi4-action-rx-20261019` 内九个固件文件 SHA256 全部通过。
- 按 name `fb204000.remoteproc` 识别 WCNSS，只重启此协处理器。
- 临时 firmware 名 `mi4-action-rx-20261019/wcnss.mdt`，成功进入 running。
- 加载实验驱动，HAL broadcast 配置和 RX filter reset 均返回 0。
- 20:22:29–20:22:49 在信道 1 被动接收 20 秒。
- 用户态 1160 帧，全部 subtype 0x80（Beacon），Action 0、ESP-NOW/SkyGauge 0。
- 驱动入口计数：rx_total=1170，rx_beacon=1170，rx_action=0，rx_drop=0。
- 20:22:49 试验结束，ExecStopPost 开始恢复；20:22:51 报 `RESTORED wcnss.mdt running`。
- 服务 inactive/dead，Result=success（只表示测试及回退流程完成，不表示遥测接通）。

## 保护与回退

脚本 `trial_wireless_action_fw.sh` 由临时 systemd 服务运行，RuntimeMaxSec=100、TimeoutStopSec=30，ExecStopPost 无论正常结束/失败/超时都调用 restore。主脚本不覆盖固件原件。

回退流程删除 skymon0、关闭 wlan0、移除实验驱动和 btqcomsmd、停止 WCNSS、把 firmware 名改回 `wcnss.mdt` 后启动，恢复原驱动并启动 bluetooth 和 obd-gauge-kiosk。

若需要手动回退（必须通过手机串口 shell）：

```sh
sudo sh /home/umeko/desktop-offline/trial_wireless_action_fw.sh restore
```

候选及归档留存供分析，不会在下一次开机自动加载。备份位置与候选哈希详见 `WIRELESS-FIRMWARE-OFFLINE-20261019.md`。

## 后续研究，不应混为已完成

加载成功排除了这次候选被固件认证直接拒绝，但不能证明修改的扫描掩码实际作用于当前接收路径。单次过滤位修改不足；需继续离线检查 PROMISC/SCAN 分支、BSS 过滤及硬件是否确实应用目标掩码，并确认主机广播条件。不要据此判断手机硬件绝对不支持。

若后续收到帧，还需严格匹配已绑定 Wi-Fi MAC `[BT-ADDRESS]`、验证 V5/47 字节、实现数据失效与模式清理，才可以接入仪表。当前仅 BLE 绑定成功，ESP-NOW 接收未接通。Vgate 直连既有功能保持不变。

## 后续第二轮：Action 独立路由候选

反汇编发现 `0x0d2c1346` 子程序把接收配置 OR 上 `1<<19`，分别调用 `0x0d2c0bbc` 配置 subtype 5（Probe Response）和 8（Beacon）；`0x0d2c1368` 则配置 subtype 13（Action）和 8。后者仅在 system mode `1<<19` 的分支调用，不能把 HAL_SYS_MODE_PROMISC 枚举值 3 与此内部 mode 位混为一谈。

`build_wireless_action_route_candidate.py` 在首轮清除 Action 屏蔽位的基础上，把 `0x0d2c1354` 的 `movs r1,#5` 改为 `movs r1,#13`，用于判断同类路由配置是否足够。仅两个代码段字节改变，哈希同步；`test_wireless_action_route_candidate.py` 验证范围、元数据、其它段和原件不变、拒绝覆盖，1 项通过。

临时目录 `/lib/firmware/mi4-action-route-rx-20261019`；临时单元 `mi4-wcn-route-trial`；均不在开机启动。

- 20:25:51–20:26:11，信道 1，20 秒。
- 用户态 1158 帧全部 Beacon；SkyGauge 0。
- 驱动 rx_total=1167、rx_beacon=1167、rx_action=0、rx_drop=0。
- 20:26:13 自动恢复原固件 running，仪表与蓝牙 active。
- 用户确认 SkyGauge 通电、主机模式、靠近小米 4。

此结果说明“扫描表放行 + 替换一个 subtype 路由”仍不足，不证明所有过滤层已经处理，也不能直接宣称硬件不支持。

## 后续第三轮：Beacon 负对照（有意义的差异）

`build_wireless_beacon_control.py` 从原件生成单独候选，只把 `0x0d5311c0` 的 mask 从 `0xc77ffedf` 改为 `0xc77fffdf`，即设 bit8；不含 Action 路由指令修改。代码段只有偏移 `0x3081c1` 一个字节、一个 bit 改变，哈希同步。

临时目录 `/lib/firmware/mi4-beacon-control-20261019`；单元 `mi4-wcn-control-trial`。

- 20:28:04–20:28:24，同样信道 1、20 秒。
- 用户态 FRAME_COUNTS={}，驱动 rx_total/rx_beacon/rx_action/rx_drop 全为 0。
- 20:28:26 自动恢复原固件 running，仪表与蓝牙 active。

与前两轮持续收到约 1160 Beacon 的结果相比，这是支持“候选确实加载且该 mask 位影响 Beacon 接收”的强证据。不是旧文件未生效。仍不能仅凭一次负对照证明其它所有位含义，后续宜恢复基线重复对比。

## 反汇编解释修正与下一步

原离线文档把 table 的前两个 u32 顺序简称 low/high 不够准确：`0x0d2c0df8` 对 scan mode 读取 `[r6+4]` 写入第一个输出（r2），读取 `[r6]` 写入第二个输出（r3）；`0x0d2c0dbc` 的第一个寄存器会 OR `0xffff0000`，第二个不 OR。应按实际寄存器/调用参数追踪，不要继续沿用前一个 u32 必然是 regLo 的命名。对 Beacon bit8 的负对照仍有效。

另外，“Turn on Rx Monitor mode failed” 日志相关 `0x0d298c98` 经指针 `0x0d530764+60` 调到 `0x0d2a3e61`，后者打印 `coexWlanSendCommand_stub` 并返回 0；这条线索涉及共存命令桩，**不能直接把它当成完整 802.11 monitor 开关，更不应盲目调用**。

已读取本机 kernel 的 `drivers/remoteproc/qcom_wcnss.c` 和 `drivers/soc/qcom/mdt_loader.c`：加载函数传入 rproc->firmware，split-segment 名由完整 firmware 路径替换末尾扩展名构造，因此独立子目录方案会加载对应子目录分段，而非悄悄回到原 b06。

下一步重点是 Action subtype 的其它过滤/地址匹配/转发条件与实际内部 mode；不要无依据打开所有寄存器位、不要假造收到数据。所有原件仍保留，候选未持久启用。
